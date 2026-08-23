# AICodec: 삼성 갤럭시 카메라를 위한 실시간 6단계 AI JPEG 압축 최적화 솔루션

[![Target Platform](https://img.shields.io/badge/Platform-Samsung%20Galaxy%20Android-blue.svg)](https://developer.samsung.com)
[![Target Latency](https://img.shields.io/badge/Latency-%3C5ms%20%40%2012MP-green.svg)]()
[![Standard Compliance](https://img.shields.io/badge/Format-Standard%20JPEG%20(ISO%2FIEC%2010918--1)-orange.svg)]()

삼성 갤럭시 스마트폰의 실시간 사진 촬영 파이프라인을 위해 설계된 **6단계 엔드투엔드 AI JPEG 압축 최적화 솔루션**입니다.

---

## 📊 핵심 성능 및 사양 요약표

| 항목 | 목표치 / 규격 | 달성 방식 |
| :--- | :--- | :--- |
| **처리 해상도** | 12 Megapixels ($4000 \times 3000$) | YUV420 Planar / NV12 ($18\text{ MB}$ 버퍼) |
| **인코딩 레이턴시** | **$\approx 3.60\text{ms}$** (상한 예산: $\le 5.0\text{ms}$) | AI NPU $0.15\text{ms}$ + 4코어 NEON $3.30\text{ms}$ + 조립 $0.05\text{ms}$ |
| **용량 절감률** | **기존 대비 $20\% \sim 35\%$ 절감** | 다계층 양자화(DQT + Dead-Zone RDO) 및 Fast-DHT 적용 |
| **화질 보존율** | **시각적 무손실 (Perceptual Lossless)** | PSNR-HVS $\ge 42\text{ dB}$, LPIPS $\le 0.02$, Butteraugli $< 1.0$ |
| **표준 호환성** | **100% ISO/IEC 10918-1 JPEG 준수** | 일반 JFIF 비트스트림 출력 (모든 뷰어/SNS 완벽 호환) |

---

## ⚡ 6단계 엔드투엔드 파이프라인 상세표

```
[ Camera HAL / 12MP YUV420 dmabuf ]
   │
   ├─► [1단계] 공간 도메인 AI Noise Shaping (<0.20ms)
   ├─► [2단계] 전역 주파수 AI DQT 예측 (<0.15ms)
   ├─► [3단계] 블록 단위 적응형 Dead-Zone RDO (~1.20ms)
   ├─► [4단계] 시맨틱 Chroma 모드 동적 전환 (<0.05ms)
   ├─► [5단계] 1-Pass 샘플링 Dynamic Huffman (DHT) (<0.10ms)
   └─► [6단계] 4코어 Restart Marker (`DRI`) 병렬 인코딩 (~2.00ms)
```

| 단계 | 처리 단계명 | 실행 하드웨어 | 소요 시간 | 압축 기여도 | 핵심 최적화 기법 |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **1** | **공간 도메인 노이즈 쉐이핑** | NPU / DSP | `< 0.20ms` | `+5% ~ 10%` | 센서 고주파 노이즈를 DCT 기저함수와 상쇄 정돈 |
| **2** | **전역 DQT 예측 (Micro-QuantNet)** | Samsung NPU | `< 0.15ms` | `+12% ~ 18%` | 인간 시각 감도(CSF) 기반 64개 주파수 가중치 회귀 |
| **3** | **블록 단위 적응형 Dead-Zone RDO** | ARM NEON | `~ 1.20ms` | `+10% ~ 15%` | 평탄 영역 불감대 마스킹 & Fast-EOB 조기 절단 |
| **4** | **시맨틱 Chroma 모드 전환** | CPU Native | `< 0.05ms` | `+3% ~ 5%` | 문서/텍스트 4:4:4 vs 일반 4:2:0 자동 스위칭 |
| **5** | **1-Pass 샘플링 Fast-DHT** | CPU Native | `< 0.10ms` | `+5% ~ 8%` | 2-Pass 스캔 없이 0.08ms 만에 맞춤형 허프만 트리 생성 |
| **6** | **DRI 기반 4코어 병렬 결합** | 4-Core CPU | `~ 2.00ms` | `속도 3배↑` | Restart Marker 기반 락-프리 메모리 스트라이핑 |
| **★** | **전체 파이프라인 종합** | **NPU + 4-Core** | **$\approx 3.60\text{ms}$** | **총 25%~35%** | **목표 5ms 대비 약 30% 마진 확보** |

---

## 📁 저장소 구조

| 디렉토리 / 파일 경로 | 내용 및 역할 |
| :--- | :--- |
| **[`docs/PROJECT_PLAN_KR.md`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/docs/PROJECT_PLAN_KR.md)** | **[한글 계획서]** 시스템 사양표, 6단계 파이프라인표, 하드웨어 할당표, A/B 테스트 매트릭스 |
| **[`docs/PROJECT_PLAN.md`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/docs/PROJECT_PLAN.md)** | **[영문 계획서]** 상세 기술 명세서 및 수식, 로드맵 일정표 |
| **[`ai_training/micro_quant_net.py`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/ai_training/micro_quant_net.py)** | **[AI 모델]** MicroQuantNet PyTorch 아키텍처 (<35k 파라미터, INT8 $\sim 35\text{KB}$) |
| **[`ai_training/diff_jpeg.py`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/ai_training/diff_jpeg.py)** | **[JPEG 시뮬레이터]** 미분 가능한 2D DCT / STE 양자화 / Rate 추정 모듈 |
| **[`ai_training/train_micro_quant_net.py`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/ai_training/train_micro_quant_net.py)** | **[학습 스크립트]** L1/LPIPS 화질 손실 + Rate 비트율 페널티 학습기 |
| **[`ai_training/export_tflite.py`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/ai_training/export_tflite.py)** | **[배포 변환]** ONNX $\rightarrow$ Samsung NPU용 INT8 TFLite 모델 변환기 |
| **[`native/FastJpegQuantizer.h`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/native/FastJpegQuantizer.h)** / [`.cpp`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/native/FastJpegQuantizer.cpp) | **[C++ SW 코덱]** ARM NEON Dead-Zone 양자화 및 1/16 Fast-DHT 히스토그램 생성기 |
| **[`native/NpuQuantRunner.h`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/native/NpuQuantRunner.h)** | **[Native NPU 연동]** 12MP Y-Plane Zero-Copy 스트라이드 샘플링 및 NPU 추론 (<0.15ms) C++ 클래스 |

---

## 🛠️ 빠른 시작 가이드 (Quick Start)

### 1. MicroQuantNet 학습 (Python / PyTorch)
```bash
cd ai_training
pip install -r requirements.txt
python train_micro_quant_net.py --epochs 20 --batch_size 16 --rate_weight 0.08
python export_tflite.py
```

### 2. 자체 SW 코덱 C++ 연동
```cpp
#include "FastJpegQuantizer.h"
#include "NpuQuantRunner.h"

// 1. NPU 추론 러너 초기화
aicodec::NpuQuantRunner npuRunner;
npuRunner.init("/vendor/etc/models/micro_quant_net_int8.tflite");

// 2. 최적 양자화 파라미터 예측 (<0.15ms)
aicodec::QuantizationMatrices quantParams;
npuRunner.predictOptimalQuantParams(yPlanePtr, 4000, 3000, yStride, meta, &quantParams);

// 3. 자체 SW 코덱 양자화기에 적용
aicodec::FastJpegQuantizer quantizer;
quantizer.updateQuantTables(quantParams);
```
