#ifndef NPU_QUANT_RUNNER_H
#define NPU_QUANT_RUNNER_H

#include "FastJpegQuantizer.h"
#include <vector>
#include <string>

namespace aicodec {

struct CameraFrameMetadata {
    float isoNormalized;       // e.g. ISO 50~3200 normalized to [0.0, 1.0]
    float exposureNormalized;  // exposure time normalized
    float meanLuma;            // average brightness [0.0, 1.0]
    float faceRoiPresent;      // 1.0 if face detected, else 0.0
};

class NpuQuantRunner {
public:
    NpuQuantRunner() = default;
    ~NpuQuantRunner();

    /**
     * Initializes the NPU runtime (Samsung ENN / Android NNAPI / TFLite INT8 delegate).
     */
    bool init(const std::string& modelPath);

    /**
     * Fast Y-Plane Subsampling & Inference.
     * Takes < 0.15ms total on Samsung Galaxy NPU.
     *
     * @param yPlanePtr Direct pointer to the 12MP Y-Plane (e.g. from AHardwareBuffer/dmabuf).
     * @param width 12MP image width (e.g. 4000).
     * @param height 12MP image height (e.g. 3000).
     * @param yStride Row stride in bytes.
     * @param metadata Camera exposure / ISO metadata.
     * @param outParams Output predicted Q-tables and dead-zone thresholds.
     */
    bool predictOptimalQuantParams(const uint8_t* yPlanePtr,
                                   int width,
                                   int height,
                                   int yStride,
                                   const CameraFrameMetadata& metadata,
                                   QuantizationMatrices* outParams);

private:
    void* mInterpreter = nullptr;
    void* mModel = nullptr;
    void* mNpuDelegate = nullptr;
    std::vector<uint8_t> mThumbBuffer; // 256 x 192 bytes
};

} // namespace aicodec

#endif // NPU_QUANT_RUNNER_H
