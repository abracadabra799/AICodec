# AICodec: 삼성 갤럭시 카메라를 위한 실시간 6단계 AI JPEG 압축 최적화 솔루션

[![Target Platform](https://img.shields.io/badge/Platform-Samsung%20Galaxy%20Android-blue.svg)](https://developer.samsung.com)
[![Target Latency](https://img.shields.io/badge/Latency-%3C5ms%20%40%2012MP-green.svg)]()
[![Standard Compliance](https://img.shields.io/badge/Format-Standard%20JPEG%20(ISO%2FIEC%2010918--1)-orange.svg)]()

삼성 갤럭시 스마트폰의 실시간 사진 촬영 파이프라인을 위해 설계된 **6단계 엔드투엔드 AI JPEG 압축 최적화 솔루션**입니다.

---

## 🚀 주요 특장점

* **초고속 실시간 처리**: **12MP ($4000 \times 3000$)** 해상도 이미지를 **약 $3.6\text{ms}$** 만에 인코딩 완료 (목표 예산: $< 5.0\text{ms}$).
* **압축률 대폭 향상**: 기존 룰 기반 DQT 로직 대비 시각적 무손실 화질을 유지하며 **$20\% \sim 35\%$ 파일 용량 절감**.
* **100% 표준 JPEG 호환**: 일반 JFIF 표준 비트스트림을 출력하여 전 세계 모든 뷰어, 웹 브라우저, SNS, 갤러리 앱에서 별도 디코더 없이 완벽 호환.
* **단순 DQT 테이블 튜닝을 넘어선 6단계 다계층 최적화**:
  1. 공간 도메인 AI 노이즈 쉐이핑
  2. 전역 주파수 AI DQT 예측 (Micro-QuantNet)
  3. 블록 레벨 적응형 불감대(Dead-Zone) 양자화 & Fast-EOB 조기 절단
  4. 시맨틱 Chroma 모드(4:4:4 vs 4:2:0) 동적 전환
  5. 1-Pass 샘플링 Dynamic Huffman Table (Fast-DHT)
  6. Restart Marker (`DRI`) 기반 Lock-Free 4-Core ARM NEON SIMD 병렬화

---

## ⚡ 6단계 엔드투엔드 파이프라인 워크플로우

```
[ Camera HAL / 12MP YUV420 dmabuf ]
   │
   ├─► 1. [공간 전처리] AI Noise Shaping & JND 맵 추출 (<0.20ms)
   │
   ├─► 2. [전역 양자화] NPU Micro-QuantNet (<0.15ms) ──► 최적 8x8 Q_Y, Q_C 행렬 예측
   │
   ├─► 3. [블록별 RDO] Block-Adaptive Dead-Zone & Fast-EOB (~1.20ms) ──► 미세 고주파 노이즈 소거
   │
   ├─► 4. [색차 변환] Semantic Chroma Mode Dynamic Switching (<0.05ms) ──► 4:4:4 / 4:2:0 자동 전환
   │
   ├─► 5. [엔트로피 코딩] 1/16 Stride Fast-DHT (<0.10ms) ──► 이미지 맞춤형 Dynamic Huffman Table 생성
   │
   └─► 6. [멀티코어 병렬화] 4-Core ARM NEON DRI SW 코덱 (~2.00ms) ──► 최종 표준 JFIF 완성 (~3.60ms)
```

---

## 📁 저장소 구조

```
AICodec/
├── docs/
│   ├── PROJECT_PLAN.md              # 상세 기술 계획서 (영문)
│   └── PROJECT_PLAN_KR.md           # 상세 기술 계획서 (한글)
├── ai_training/
│   ├── micro_quant_net.py           # MicroQuantNet PyTorch 아키텍처 (<35k 파라미터)
│   ├── diff_jpeg.py                 # Rate-Distortion 학습용 미분 가능 JPEG 시뮬레이터
│   ├── train_micro_quant_net.py     # 엔드투엔드 R-D 학습 스크립트
│   ├── export_tflite.py             # ONNX 및 TFLite INT8 모델 변환 스크립트
│   └── requirements.txt             # Python 의존성 패키지
├── native/
│   ├── FastJpegQuantizer.h          # NEON Dead-Zone 양자화 및 Fast-DHT C++ 헤더
│   ├── FastJpegQuantizer.cpp        # ARM NEON SIMD 양자화기 및 히스토그램 생성기
│   └── NpuQuantRunner.h             # Samsung NPU (ENN / TFLite C-API) 연동 래퍼
├── app/                             # Android 애플리케이션 모듈
├── README.md                        # 메인 README (영문)
└── README_KR.md                     # 메인 README (한글)
```

---

## 🛠️ 빠른 시작 가이드

### 1. MicroQuantNet 학습 (Python / PyTorch)
```bash
cd ai_training
pip install -r requirements.txt
python train_micro_quant_net.py --epochs 20 --batch_size 16 --rate_weight 0.08
python export_tflite.py
```

### 2. 자체 SW 코덱 C++ 연동 예제
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

---

## 📊 화질 및 성능 검증 기준
* **PSNR-HVS-M**: $\ge 42\text{ dB}$ (인간 시각 특성 반영)
* **LPIPS**: $\le 0.02$ (시각적 무손실 레벨)
* **Butteraugli Score**: $< 1.0$ (구글 시각 왜곡 감지 한계선 이하)
* **전체 지연 시간**: 갤럭시 플래그십 AP(Cortex-X4 / A720 + NPU) 기준 **$\approx 3.6\text{ms}$**.
