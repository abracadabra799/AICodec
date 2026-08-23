# Samsung Galaxy Camera Real-Time AI JPEG Compression Solution Plan
**Target**: 12MP Image Encoding $\le 5\text{ms}$ | **Visual Quality**: Perceptual Lossless (PSNR-HVS / LPIPS) | **Platform**: Samsung Galaxy (Exynos / Snapdragon)

---

## 1. Executive Summary & Problem Formulation

### 1.1 Goals & Constraints
1. **Resolution**: 12 Megapixels ($4000 \times 3000$) YUV420 buffer ($18\text{ MB}$).
2. **Latency Budget**: Total execution $\le 5\text{ms}$ per 12MP frame in real-time camera capture pipeline.
3. **Format Compatibility**: 100% ISO/IEC 10918-1 Standard JPEG (JFIF) bitstream (readable by standard decoders, web browsers, social media, gallery).
4. **Compression Gain**: $20\% \sim 35\%$ file size reduction at equivalent or superior perceptual quality compared to existing heuristic DQT logic.
5. **Power & Thermal**: Sub-millisecond NPU duty cycle, zero CPU/bus memory contention.

---

## 2. System Architecture & End-to-End Workflow

```
[ Camera HAL / 12MP YUV420 dmabuf Buffer ]
                    │
                    ├─► [ Step 1: NPU Micro-QuantNet (<0.15ms) ]
                    │     - Inputs: 256x192 Stride Subsampled Luma + Camera Metadata (ISO, Exp, ROI)
                    │     - Outputs: Optimal 8x8 Q_Y, Q_C & Dead-Zone Noise Thresholds
                    │
                    ├─► [ Step 2: 1/16 Stride Fast-DHT (<0.10ms) ]
                    │     - Samples 6.25% of 8x8 blocks across 12MP
                    │     - Generates optimal Dynamic Huffman Table in a single pass
                    │
                    ├─► [ Step 3: 4-Core Parallel SIMD SW Encoding (~3.30ms) ]
                    │     - ARM NEON Forward DCT
                    │     - NEON SIMD Dead-Zone Quantization (eliminates non-perceptible high-frequency noise)
                    │     - Restart Marker (DRI / RST0~RST7) Lock-Free Multi-Threading (Cortex-X + Gold cores)
                    │
                    └─► [ Step 4: Bitstream Assembly (<0.05ms) ]
                          - Output standard JFIF file (25~35% size reduction)
                          - Total Latency: ~3.60ms (well within 5ms budget)
```

---

## 3. Micro-QuantNet: Model Architecture & Rate-Distortion Training

### 3.1 Neural Network Design
* **Backbone**: 4-Stage Depthwise-Separable ConvNet ($3\times 3$, Stride 2)
* **Metadata Fusion**: Linear projection of $[ \text{ISO}_{\text{norm}}, \text{Exp}_{\text{norm}}, \text{MeanBrightness}, \text{FaceFlag} ]$
* **Regression Head**: Outputs $128$ multipliers ($64$ for Luminance $Q_Y$, $64$ for Chrominance $Q_C$) applied to standard base Q-tables.
* **Footprint**: $<35\text{k}$ parameters ($\sim 35\text{KB}$ in INT8).
* **Latency**: $0.12\text{ms} \sim 0.15\text{ms}$ on Samsung NPU (ENN SDK) / Qualcomm Hexagon.

### 3.2 Loss Function (Differentiable JPEG R-D Optimization)
$$\mathcal{L}_{\text{total}} = \mathcal{L}_{\text{perceptual}}(\hat{I}, I) + \lambda \cdot \mathcal{L}_{\text{rate}}(Q_Y, Q_C)$$
* $\mathcal{L}_{\text{perceptual}} = \mathcal{L}_{\text{L1}} + \alpha \mathcal{L}_{\text{MS-SSIM/LPIPS}}$
* $\mathcal{L}_{\text{rate}} = \mathbb{E}[\log_2(1 + |C_{\text{quantized}}|)]$ (Surrogate for Huffman bitstream length)
* $\lambda$: Lagrange multiplier tuned for target bitrates.

---

## 4. SW Codec Enhancements (Native C++ Implementation)

1. **ARM NEON SIMD Dead-Zone Quantization**:
   * Uses `vabsq_s16`, `vcgtq_s16`, and `vandq_u16` to mask out high-frequency sensor noise below human JND thresholds during quantization multiplication.
   * Zero added execution cycles in the inner SIMD loop.
2. **1-Pass Sampling Fast-DHT**:
   * Eliminates the 1.5ms penalty of 2-pass Huffman table scans by accumulating histograms over a $1/16$ strided block subset in $<0.08\text{ms}$.
3. **Restart Marker (`DRI`) Lock-Free Striping**:
   * Divides the 12MP image (188 MCU rows) into 4 independent bands across Cortex-X and Cortex-A cores without inter-thread mutex locks.

---

## 5. Verification & Benchmark Plan (A/B Testing vs Existing In-House DQT)

### 5.1 Dataset Stratification (1,000+ Test Images)
* **Night / High-ISO ($\text{ISO} \ge 1600$)**: Evaluates noise suppression vs shadow detail retention.
* **Portraits / Skin Tone**: Evaluates facial texture preservation, hair detail, and background compression.
* **Foliage & Fine Text**: Evaluates high-frequency contrast, ringing artifacts, and edge sharpness.
* **Flat Surfaces / Gradients (Sky, Walls)**: Evaluates color banding (blocking) suppression.

### 5.2 Evaluation Metrics
* **BD-Rate (Bjøntegaard Delta Rate)**: Percentage of file size reduction at equivalent perceptual quality.
* **LPIPS (Learned Perceptual Image Patch Similarity)**: $\le 0.02$ (Indistinguishable by human vision).
* **PSNR-HVS-M**: $\ge 42\text{ dB}$.
* **Butteraugli Score (Google Perceptual Distortion Metric)**: $< 1.0$ (Strictly below human perception threshold).
* **Encoding Latency**: Total time in milliseconds on Galaxy S24/S25 device ($< 5\text{ms}$).

---

## 6. Implementation Roadmap

| Phase | Milestone | Deliverables | Estimated Duration |
| :--- | :--- | :--- | :--- |
| **Phase 1** | **Algorithm & PyTorch Training** | - Differentiable JPEG loss & MicroQuantNet training<br>- BD-Rate curve validation | Weeks 1 - 2 |
| **Phase 2** | **INT8 Quantization & NPU Porting** | - ONNX $\rightarrow$ TFLite INT8 conversion<br>- Samsung ENN / NPU execution verification (<0.2ms) | Weeks 3 - 4 |
| **Phase 3** | **In-House SW Codec Integration** | - NEON Dead-Zone quantization & Fast-DHT integration<br>- Multi-threaded Restart Marker pipeline | Weeks 5 - 6 |
| **Phase 4** | **Galaxy Device On-Device Tuning & QA** | - A/B benchmark against existing in-house DQT<br>- Thermal / Battery profiling & final sign-off | Weeks 7 - 8 |
