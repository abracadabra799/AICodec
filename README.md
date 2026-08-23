# AICodec: Real-Time 6-Stage AI JPEG Compression Solution for Samsung Galaxy

[![Target Platform](https://img.shields.io/badge/Platform-Samsung%20Galaxy%20Android-blue.svg)](https://developer.samsung.com)
[![Target Latency](https://img.shields.io/badge/Latency-%3C5ms%20%40%2012MP-green.svg)]()
[![Standard Compliance](https://img.shields.io/badge/Format-Standard%20JPEG%20(ISO%2FIEC%2010918--1)-orange.svg)]()

A high-performance, real-time **6-Stage End-to-End AI-assisted JPEG compression solution** designed for the **Samsung Galaxy Camera real-time photo capture pipeline**.

---

## 📊 Performance & Specification Matrix

| Parameter | Target Requirement | Implementation Method |
| :--- | :--- | :--- |
| **Image Resolution** | 12 Megapixels ($4000 \times 3000$) | YUV420 Planar / NV12 ($18\text{ MB}$ Buffer) |
| **Encoding Latency** | **$\approx 3.60\text{ms}$** (Max Budget: $\le 5.0\text{ms}$) | AI NPU $0.15\text{ms}$ + 4-Core NEON $3.30\text{ms}$ + Assembly $0.05\text{ms}$ |
| **Compression Gain** | **$20\% \sim 35\%$ File Size Reduction** | Multi-Layer Quantization (DQT + Dead-Zone RDO) + Fast-DHT |
| **Visual Quality** | **Perceptual Lossless** | PSNR-HVS $\ge 42\text{ dB}$, LPIPS $\le 0.02$, Butteraugli $< 1.0$ |
| **Standard Compliance** | **100% ISO/IEC 10918-1 JPEG Syntax** | Standard JFIF Bitstream (Universal Viewer/SNS Compatibility) |

---

## ⚡ 6-Stage Pipeline Breakdown Table

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

| Stage | Process Name | Execution Unit | Latency | Compression Gain | Core Innovation |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **1** | **Spatial Noise Shaping** | NPU / DSP | `< 0.20ms` | `+5% ~ 10%` | Flattens non-perceptible sensor noise in flat/shadow regions |
| **2** | **Global DQT (Micro-QuantNet)** | Samsung NPU | `< 0.15ms` | `+12% ~ 18%` | Human CSF-guided non-linear 64 frequency coefficient regression |
| **3** | **Block-Adaptive Dead-Zone RDO** | ARM NEON | `~ 1.20ms` | `+10% ~ 15%` | Non-salient block dead-zone masking & Fast-EOB truncation |
| **4** | **Semantic Chroma Switching** | CPU Native | `< 0.05ms` | `+3% ~ 5%` | Document 4:4:4 vs General 4:2:0 dynamic switching |
| **5** | **1-Pass Sampling Fast-DHT** | CPU Native | `< 0.10ms` | `+5% ~ 8%` | Builds image-specific Huffman trees in 0.08ms without 2-pass lag |
| **6** | **DRI 4-Core Parallel Stride** | 4-Core CPU | `~ 2.00ms` | `3x Speedup` | Restart Marker-based lock-free memory striping |
| **★** | **Total Pipeline Synergy** | **NPU + 4-Core** | **$\approx 3.60\text{ms}$** | **25% ~ 35% Total** | **~30% Safety Margin under 5.0ms Budget** |

---

## 📁 Repository Structure Table

| Directory / File Path | Description & Role |
| :--- | :--- |
| **[`docs/PROJECT_PLAN.md`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/docs/PROJECT_PLAN.md)** | **[English Plan]** Full technical specifications, formulas, resource tables, and milestones |
| **[`docs/PROJECT_PLAN_KR.md`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/docs/PROJECT_PLAN_KR.md)** | **[Korean Plan]** System spec table, 6-stage pipeline table, hardware allocation table, A/B matrix |
| **[`ai_training/micro_quant_net.py`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/ai_training/micro_quant_net.py)** | **[AI Model]** MicroQuantNet PyTorch architecture (<35k params, INT8 $\sim 35\text{KB}$) |
| **[`ai_training/diff_jpeg.py`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/ai_training/diff_jpeg.py)** | **[JPEG Simulator]** Differentiable 2D DCT / STE Quantization / Rate estimation module |
| **[`ai_training/train_micro_quant_net.py`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/ai_training/train_micro_quant_net.py)** | **[Training Script]** End-to-end Rate-Distortion training script (L1/LPIPS + Rate penalty) |
| **[`ai_training/export_tflite.py`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/ai_training/export_tflite.py)** | **[NPU Deployment]** ONNX $\rightarrow$ TFLite INT8 quantization pipeline |
| **[`native/FastJpegQuantizer.h`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/native/FastJpegQuantizer.h)** / [`.cpp`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/native/FastJpegQuantizer.cpp) | **[C++ SW Codec]** ARM NEON Dead-Zone Quantization & 1/16 Stride Fast-DHT builder |
| **[`native/NpuQuantRunner.h`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/native/NpuQuantRunner.h)** | **[Native NPU Interface]** 12MP Y-Plane Zero-Copy Stride Subsampling & NPU Inference C++ class |

---

## 🛠️ Quick Start

### 1. Training MicroQuantNet (Python / PyTorch)
```bash
cd ai_training
pip install -r requirements.txt
python train_micro_quant_net.py --epochs 20 --batch_size 16 --rate_weight 0.08
python export_tflite.py
```

### 2. Native C++ Codec Integration
```cpp
#include "FastJpegQuantizer.h"
#include "NpuQuantRunner.h"

// 1. Initialize NPU runner
aicodec::NpuQuantRunner npuRunner;
npuRunner.init("/vendor/etc/models/micro_quant_net_int8.tflite");

// 2. Predict dynamic Q-Tables (<0.15ms)
aicodec::QuantizationMatrices quantParams;
npuRunner.predictOptimalQuantParams(yPlanePtr, 4000, 3000, yStride, meta, &quantParams);

// 3. Apply to Fast SW Codec
aicodec::FastJpegQuantizer quantizer;
quantizer.updateQuantTables(quantParams);
```
