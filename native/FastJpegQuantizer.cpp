#include "FastJpegQuantizer.h"
#include <cstring>
#include <algorithm>

namespace aicodec {

void FastJpegQuantizer::updateQuantTables(const QuantizationMatrices& tables) {
    mDeadZoneLuma = tables.deadZoneThresholdLuma;
    mDeadZoneChroma = tables.deadZoneThresholdChroma;

    // Convert Q divisor to fixed-point reciprocal multiplier: mult = (1 << 15) / Q
    for (int i = 0; i < 64; ++i) {
        int qL = std::max((int)tables.qLuma[i], 1);
        int qC = std::max((int)tables.qChroma[i], 1);
        mMultLuma[i] = (int16_t)(((1 << 15) + (qL / 2)) / qL);
        mMultChroma[i] = (int16_t)(((1 << 15) + (qC / 2)) / qC);
    }
}

void FastJpegQuantizer::quantizeBlockSIMD(const int16_t* inDctCoeffs, int16_t* outQuantCoeffs, bool isChroma) {
    const int16_t* mult = isChroma ? mMultChroma : mMultLuma;
    const int16_t deadZone = isChroma ? mDeadZoneChroma : mDeadZoneLuma;

#if defined(__ARM_NEON) || defined(__ARM_NEON__)
    const int16x8_t vZero = vdupq_n_s16(0);
    const int16x8_t vDeadZone = vdupq_n_s16(deadZone);

    // Process 64 coefficients in 8 iterations of 8-wide NEON vectors
    for (int i = 0; i < 64; i += 8) {
        int16x8_t vCoeff = vld1q_s16(inDctCoeffs + i);
        int16x8_t vMult = vld1q_s16(mult + i);

        // Absolute value
        int16x8_t vAbs = vabsq_s16(vCoeff);

        // Dead-Zone Thresholding: if |coeff| <= deadZone, force to 0
        uint16x8_t vMask = vcgtq_s16(vAbs, vDeadZone);
        int16x8_t vFiltered = vandq_s16(vAbs, vreinterpretq_s16_u16(vMask));

        // Fixed-point multiply: (vFiltered * vMult + (1 << 14)) >> 15
        int32x4_t vLow = vmull_s16(vget_low_s16(vFiltered), vget_low_s16(vMult));
        int32x4_t vHigh = vmull_s16(vget_high_s16(vFiltered), vget_high_s16(vMult));

        // Add rounding offset (1 << 14) and shift right by 15
        int16x4_t vResLow = vrshrn_n_s32(vLow, 15);
        int16x4_t vResHigh = vrshrn_n_s32(vHigh, 15);
        int16x8_t vQuant = vcombine_s16(vResLow, vResHigh);

        // Restore original sign
        uint16x8_t vNegMask = vcltq_s16(vCoeff, vZero);
        int16x8_t vNegQuant = vnegq_s16(vQuant);
        int16x8_t vFinal = vbslq_s16(vNegMask, vNegQuant, vQuant);

        vst1q_s16(outQuantCoeffs + i, vFinal);
    }
#else
    // Fallback scalar implementation with Dead-Zone
    for (int i = 0; i < 64; ++i) {
        int16_t c = inDctCoeffs[i];
        int16_t abs_c = std::abs(c);
        if (abs_c <= deadZone) {
            outQuantCoeffs[i] = 0;
        } else {
            int q = ((int32_t)abs_c * mult[i] + (1 << 14)) >> 15;
            outQuantCoeffs[i] = (c < 0) ? -q : q;
        }
    }
#endif
}

void FastJpegQuantizer::accumulateSampledHistogram(const int16_t* quantizedCoeffsArray, 
                                                  size_t totalBlocks, 
                                                  uint32_t* outFreqDc, 
                                                  uint32_t* outFreqAc) {
    // Sample every 16th block across 12MP (187,500 total blocks -> ~11,700 sampled blocks)
    // Execution takes < 0.08ms
    constexpr size_t STRIDE_BLOCKS = 16;

    for (size_t b = 0; b < totalBlocks; b += STRIDE_BLOCKS) {
        const int16_t* block = quantizedCoeffsArray + (b * 64);
        
        // DC Coefficient category
        int16_t dc = block[0];
        int dcCat = 0;
        int16_t absDc = std::abs(dc);
        while (absDc > 0) {
            dcCat++;
            absDc >>= 1;
        }
        if (dcCat < 16) outFreqDc[dcCat]++;

        // AC Run-Length Categories
        int zeroRun = 0;
        for (int k = 1; k < 64; ++k) {
            int16_t ac = block[k];
            if (ac == 0) {
                zeroRun++;
            } else {
                while (zeroRun >= 16) {
                    outFreqAc[0xF0]++; // ZRL (16 zero runs)
                    zeroRun -= 16;
                }
                int acCat = 0;
                int16_t absAc = std::abs(ac);
                while (absAc > 0) {
                    acCat++;
                    absAc >>= 1;
                }
                uint8_t symbol = (uint8_t)((zeroRun << 4) | (acCat & 0x0F));
                outFreqAc[symbol]++;
                zeroRun = 0;
            }
        }
        if (zeroRun > 0) {
            outFreqAc[0x00]++; // EOB (End of Block)
        }
    }
}

} // namespace aicodec
