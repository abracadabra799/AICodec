# Samsung Galaxy Real-Time 6-Stage AI JPEG Compression Solution Plan

---

## 1. System Specifications & Constraint Summary

| Parameter | Target Requirement | Technical Solution |
| :--- | :--- | :--- |
| **Image Resolution** | 12 Megapixels ($4000 \times 3000$) | YUV420 Planar / NV12 ($18\text{ MB}$ Buffer) |
| **Latency Budget** | **$\le 5.0\text{ms}$** (Real-Time Camera Pipeline) | AI Inference $\le 0.15\text{ms}$ + 4-Core NEON SW Encode $\le 3.45\text{ms}$ |
| **Compression Target** | **$20\% \sim 35\%$ File Size Reduction** | Multi-Layer Quantization (DQT + Dead-Zone RDO) + Fast-DHT |
| **Visual Quality** | **Perceptual Lossless** | PSNR-HVS $\ge 42\text{ dB}$, LPIPS $\le 0.02$, Butteraugli $< 1.0$ |
| **Standard Compliance** | **100% ISO/IEC 10918-1 JPEG Syntax** | Standard JFIF Bitstream (Universal Compatibility) |
| **Power & Thermals** | Minimal Thermal Throttling | INT8 NPU Inference + `dmabuf` Zero-Copy Memory Pipeline |

---

## 2. 6-Stage End-to-End Pipeline Breakdown Table

```
[ Camera HAL / 12MP YUV420 dmabuf ]
   │
   ├─► [Stage 1] Spatial AI Noise Shaping (<0.20ms)
   ├─► [Stage 2] Global Frequency AI DQT Prediction (<0.15ms)
   ├─► [Stage 3] Block-Adaptive Dead-Zone RDO (~1.20ms)
   ├─► [Stage 4] Semantic Chroma Mode Dynamic Switching (<0.05ms)
   ├─► [Stage 5] 1-Pass Sampling Dynamic Huffman (DHT) (<0.10ms)
   └─► [Stage 6] 4-Core Restart Marker (`DRI`) Parallel SW Encode (~2.00ms)
```

| Stage | Process Name | Execution Unit | Input / Output | Latency | Compression Gain | Core Innovation |
| :---: | :--- | :---: | :--- | :---: | :---: | :--- |
| **1** | **Spatial Noise Shaping** | NPU / DSP | **In**: 12MP YUV<br>**Out**: Conditioned YUV | `< 0.20ms` | `+5% ~ 10%` | Flattens non-perceptible sensor noise in flat/shadow regions |
| **2** | **Global DQT (Micro-QuantNet)** | Samsung NPU | **In**: 256x192 + Meta<br>**Out**: 64B $Q_Y, Q_C$ | `< 0.15ms` | `+12% ~ 18%` | Human CSF-guided non-linear 64 frequency coefficient regression |
| **3** | **Block-Adaptive Dead-Zone RDO** | ARM NEON | **In**: 8x8 DCT coeffs<br>**Out**: Quantized coeffs | `~ 1.20ms` | `+10% ~ 15%` | Non-salient block dead-zone masking & Fast-EOB truncation |
| **4** | **Semantic Chroma Switching** | CPU Native | **In**: Scene Tag<br>**Out**: Subsampling mode | `< 0.05ms` | `+3% ~ 5%` | Document 4:4:4 vs General 4:2:0 dynamic switching |
| **5** | **1-Pass Sampling Fast-DHT** | CPU Native | **In**: 1/16 Histogram<br>**Out**: Custom DHT | `< 0.10ms` | `+5% ~ 8%` | Builds image-specific Huffman trees in 0.08ms without 2-pass lag |
| **6** | **DRI 4-Core Parallel Stride** | 4-Core CPU | **In**: 4 MCU bands<br>**Out**: Standard JFIF | `~ 2.00ms` | `3x Speedup` | Restart Marker-based lock-free memory striping |
| **★** | **Total Pipeline Synergy** | **NPU + 4-Core** | **12MP YUV $\rightarrow$ JPEG** | **$\approx 3.60\text{ms}$** | **25% ~ 35% Total** | **~30% Safety Margin under 5.0ms Budget** |

---

## 3. Heuristic DQT vs Proposed 6-Stage AI Solution Comparison Table

| Evaluation Aspect | Existing Heuristic DQT | Proposed 6-Stage Solution (`AICodec`) |
| :--- | :--- | :--- |
| **Quantization Mechanism** | Static/Linear single table per image | **AI Global DQT + Block-Adaptive Dead-Zone RDO** |
| **Sensor Noise Handling** | High-frequency noise wastes AC bitstream bits | **Spatial AI Noise Shaping flattens noise before DCT** |
| **Huffman Coding** | Generic 1992 static tables (Annex K) | **1/16 Stride Fast 1-Pass Dynamic Huffman (DHT)** |
| **Rate-Distortion Optimization** | None (Basic division & rounding) | **Fast-EOB early termination (Saves 10~20 bits/block)** |
| **Multi-Threading Model** | Possible mutex lock overhead | **Restart Marker (`DRI`) 100% Lock-Free Parallelism** |
| **File Size (Same Quality)** | Baseline ($100\%$) | **$65\% \sim 75\%$ ($25\% \sim 35\%$ File Size Reduction)** |
| **Execution Latency (12MP)** | $\approx 4.5\text{ms} \sim 6.0\text{ms}$ | **$\approx 3.60\text{ms}$ (Strictly under 5.0ms)** |

---

## 4. Hardware Resource Allocation & Scheduling Table

| Core / Accelerator | Assigned Workload | Optimization Technique | Latency |
| :--- | :--- | :--- | :---: |
| **Samsung NPU** | Micro-QuantNet Inference | INT8 Quantized, Zero-Copy Stride Memory Binding | `0.15ms` |
| **Cortex-X4 (Prime)** | MCU Row 0 ~ 46 + DHT Generation | NEON SIMD + Sampling Fast-DHT | `3.30ms` |
| **Cortex-A720 #1 (Gold)** | MCU Row 47 ~ 93 Encoding | NEON SIMD Dead-Zone Quantization | `3.20ms` |
| **Cortex-A720 #2 (Gold)** | MCU Row 94 ~ 140 Encoding | NEON SIMD Dead-Zone Quantization | `3.20ms` |
| **Cortex-A720 #3 (Gold)** | MCU Row 141 ~ 187 Encoding | NEON SIMD Dead-Zone Quantization | `3.20ms` |
| **Main Thread** | JFIF Header Assembly & Packaging | $O(1)$ Pointer Linking (Minimal `memcpy`) | `0.05ms` |

---

## 5. Verification & Benchmark Matrix

### 5.1 Stratified Test Dataset (1,000+ Images)

| Scene Category | Key Characteristics | Primary Verification Focus | Target Metric |
| :--- | :--- | :--- | :--- |
| **High-ISO Night** | $\text{ISO} \ge 1600$, Shadow noise | Noise reduction vs shadow detail preservation | PSNR-HVS $\ge 40\text{ dB}$ |
| **Portraits / Selfies** | Skin tones, eyes, fine hair | Facial texture retention, background bokeh compression | LPIPS $\le 0.015$ |
| **Landscapes / Nature** | Foliage, grass, fine texture | Leaf detail preservation, edge ringing suppression | MS-SSIM $\ge 0.985$ |
| **Documents / Text** | Receipts, signs, character edges | Character legibility, chroma bleeding prevention | Butteraugli $< 0.8$ |
| **Gradients (Sky/Walls)** | Uniform color regions | Color banding (blocking) artifact prevention | PSNR $\ge 44\text{ dB}$ |

### 5.2 Objective Metric Thresholds

| Metric | Description | Target Threshold |
| :--- | :--- | :--- |
| **BD-Rate (Size Reduction)** | Bitrate reduction at equivalent perceptual visual quality | **$\ge 25.0\%$ Reduction** |
| **LPIPS** | Deep perceptual visual distance metric | **$\le 0.020$** (Humanly indistinguishable) |
| **PSNR-HVS-M** | Human Visual System & Masking PSNR | **$\ge 42.0\text{ dB}$** |
| **Butteraugli Score** | Google visual distortion perception threshold | **$< 1.0$** (Strictly below human perception threshold) |
| **End-to-End Latency** | 12MP YUV input to standard JPEG completion | **$\le 4.5\text{ms}$** (Safety margin below 5.0ms) |

---

## 6. Implementation Roadmap & Milestone Schedule

| Phase | Duration | Core Tasks | Deliverables | Success Criteria |
| :---: | :---: | :--- | :--- | :--- |
| **Phase 1** | Weeks 1-2 | PyTorch MicroQuantNet & Differentiable JPEG | `micro_quant_net.pth`, R-D loss | BD-Rate gain $\ge 20\%$ |
| **Phase 2** | Weeks 3-4 | ONNX $\rightarrow$ TFLite INT8 & NPU Porting | `micro_quant_net_int8.tflite`, C++ Runner | NPU Latency $\le 0.15\text{ms}$ |
| **Phase 3** | Weeks 5-6 | SW Codec Integration (NEON Dead-Zone & DHT) | `FastJpegQuantizer.cpp`, DRI pipeline | 4-Core SW Latency $\le 3.45\text{ms}$ |
| **Phase 4** | Weeks 7-8 | On-Device A/B Benchmark (1,000 images) & QA | Final Benchmark Report, Release Binary | 12MP $\le 5\text{ms}$, 25~35% Size Gain |
