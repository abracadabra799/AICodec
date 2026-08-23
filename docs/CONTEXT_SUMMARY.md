# AICodec 프로젝트 인수인계 및 컨텍스트 요약서 (Context Summary)
> **목적**: 다른 PC 및 계정의 Gemini CLI 환경에서 본 세션을 즉시 이어서 진행하기 위한 컨텍스트 요약 문서

---

## 1. 프로젝트 핵심 메타데이터 표

| 항목 | 내용 |
| :--- | :--- |
| **프로젝트명** | `AICodec` (삼성 갤럭시 카메라 실시간 AI JPEG 압축 최적화) |
| **담당자 도메인** | Android Media Framework, MediaCodec, Image & Video Codec 엔지니어 |
| **타겟 스펙** | 12MP ($4000 \times 3000$) YUV420 이미지 당 **$\le 5.0\text{ms}$** 이내 인코딩 |
| **목표 압축률** | 기존 자체 DQT 대비 시각적 무손실(Perceptual Lossless) 유지하며 **$25\% \sim 35\%$ 파일 크기 절감** |
| **표준 호환성** | **100% ISO/IEC 10918-1 표준 JPEG (JFIF)** 규격 준수 (별도 디코더 불필요) |
| **현재 진행 상황** | 자체 In-House SW 코덱 운용 중 $\rightarrow$ 기존 룰 기반 DQT를 대체하는 6단계 AI 솔루션 설계 완료 |
| **GitHub 저장소** | `https://github.com/abracadabra799/AICodec.git` (Branch: `main`) |

---

## 2. 확정된 6단계 엔드투엔드 파이프라인 구조표

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

| 단계 | 명칭 | 구현 위치 | 소요 시간 | 핵심 내용 |
| :---: | :--- | :---: | :---: | :--- |
| **1** | **AI Noise Shaping** | NPU/DSP | `< 0.20ms` | 센서 고주파 노이즈를 DCT 기저함수와 상쇄 사전 정돈 |
| **2** | **AI Micro-QuantNet** | Samsung NPU | `< 0.15ms` | 64개 CSF 인간 시각 가중치 회귀 (INT8 $<35\text{KB}$) |
| **3** | **Block Dead-Zone RDO** | ARM NEON | `~ 1.20ms` | 평탄 영역 불감대 마스킹 & Fast-EOB 조기 절단 |
| **4** | **Semantic Chroma Mode** | CPU Native | `< 0.05ms` | 텍스트 4:4:4 vs 일반 4:2:0 자동 전환 |
| **5** | **1-Pass Fast-DHT** | CPU Native | `< 0.10ms` | 1/16 블록 고속 샘플링 기반 전용 허프만 테이블 |
| **6** | **DRI 4-Core Parallel** | 4-Core CPU | `~ 2.00ms` | Restart Marker 기반 락-프리 메모리 스트라이핑 |
| **★** | **전체 파이프라인 종합** | **NPU + 4-Core** | **$\approx 3.60\text{ms}$** | **목표 5.0ms 대비 30% 마진 확보 (용량 25~35% 절감)** |

---

## 3. 저장소 코드베이스 맵

| 디렉토리 / 파일 | 역할 및 상태 |
| :--- | :--- |
| **[`docs/PROJECT_PLAN_KR.md`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/docs/PROJECT_PLAN_KR.md)** | 시스템 사양표, 파이프라인표, 비교표, 하드웨어 할당표, A/B 매트릭스 |
| **[`ai_training/micro_quant_net.py`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/ai_training/micro_quant_net.py)** | MicroQuantNet PyTorch 모델 정의 (<35k 파라미터) |
| **[`ai_training/diff_jpeg.py`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/ai_training/diff_jpeg.py)** | 2D DCT / STE 미분 가능 양자화 / Rate 추정 시뮬레이터 |
| **[`ai_training/train_micro_quant_net.py`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/ai_training/train_micro_quant_net.py)** | L1/LPIPS 화질 손실 + Rate 비트율 페널티 학습 스크립트 |
| **[`ai_training/export_tflite.py`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/ai_training/export_tflite.py)** | ONNX $\rightarrow$ Samsung NPU용 INT8 TFLite 모델 변환기 |
| **[`native/FastJpegQuantizer.h`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/native/FastJpegQuantizer.h)** / [`.cpp`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/native/FastJpegQuantizer.cpp) | ARM NEON Dead-Zone 양자화 및 1/16 Fast-DHT 히스토그램 생성 C++ 모듈 |
| **[`native/NpuQuantRunner.h`](file:///Users/dong.kim/AndroidStudioProjects/AICodec/native/NpuQuantRunner.h)** | 12MP Y-Plane Zero-Copy 스트라이드 샘플링 및 NPU C-API 추론 C++ 모듈 |

---

## 4. 내각 이어받아 진행할 작업 (Next Action Items)

1. **Android NDK 빌드 연동**: `native/CMakeLists.txt` 작성 및 `app` 모듈 JNI 연결.
2. **PyTorch 모델 학습 실행**: 실제 이미지 데이터셋 또는 샘플 패치로 `train_micro_quant_net.py` 실행 및 `micro_quant_net_int8.tflite` 생성.
3. **자체 SW 코덱에 C++ 코드 연결**: `FastJpegQuantizer` 및 `NpuQuantRunner`를 자체 코덱 인스턴스에 결합하여 12MP 인코딩 실측.
