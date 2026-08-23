#ifndef FAST_JPEG_QUANTIZER_H
#define FAST_JPEG_QUANTIZER_H

#include <cstdint>
#include <cstddef>

#if defined(__ARM_NEON) || defined(__ARM_NEON__)
#include <arm_neon.h>
#endif

namespace aicodec {

// 8x8 DCT Block Dimensions
constexpr int BLOCK_SIZE = 8;
constexpr int BLOCK_AREA = 64;

struct QuantizationMatrices {
    uint8_t qLuma[64];
    uint8_t qChroma[64];
    int16_t deadZoneThresholdLuma;   // Adaptive dead-zone noise threshold
    int16_t deadZoneThresholdChroma;
};

class FastJpegQuantizer {
public:
    FastJpegQuantizer() = default;
    ~FastJpegQuantizer() = default;

    /**
     * Initializes fixed-point reciprocal multipliers for 8x8 Quantization Tables.
     */
    void updateQuantTables(const QuantizationMatrices& tables);

    /**
     * Quantizes an 8x8 DCT block using ARM NEON SIMD with Dead-Zone Noise Suppression.
     * @param inDctCoeffs 64 int16_t DCT coefficients.
     * @param outQuantCoeffs 64 int16_t quantized output coefficients.
     * @param isChroma True if chrominance block.
     */
    void quantizeBlockSIMD(const int16_t* inDctCoeffs, int16_t* outQuantCoeffs, bool isChroma);

    /**
     * Fast 1-Pass Dynamic Huffman Table (DHT) Frequency Histogram Accumulator.
     * Samples 1 out of every 16 blocks (6.25% sampling) across 12MP for ultra-fast DHT generation (<0.1ms).
     */
    static void accumulateSampledHistogram(const int16_t* quantizedCoeffsArray, 
                                           size_t totalBlocks, 
                                           uint32_t* outFreqDc, 
                                           uint32_t* outFreqAc);

private:
    int16_t mMultLuma[64];
    int16_t mMultChroma[64];
    int16_t mDeadZoneLuma;
    int16_t mDeadZoneChroma;
    int mShiftLuma = 15;
    int mShiftChroma = 15;
};

} // namespace aicodec

#endif // FAST_JPEG_QUANTIZER_H
