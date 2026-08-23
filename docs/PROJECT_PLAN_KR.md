# 삼성 갤럭시 실시간 6단계 AI JPEG 압축 최적화 상세 계획서

---

## 1. 핵심 시스템 사양 및 제약 조건 요약

| 항목 | 요구 사양 | 기술적 대응 방안 |
| :--- | :--- | :--- |
| **대상 해상도** | 12 Megapixels ($4000 \times 3000$) | YUV420 Planar / NV12 ($18\text{ MB}$ 버퍼) |
| **목표 레이턴시** | **$\le 5.0\text{ms}$** (실시간 카메라 캡처) | AI 추론 $\le 0.15\text{ms}$ + 4코어 NEON 병렬 인코딩 $\le 3.45\text{ms}$ |
| **압축률 목표** | **$20\% \sim 35\%$ 용량 절감** | 다계층 양자화(DQT + Dead-Zone RDO) 및 Fast-DHT 적용 |
| **화질 목표** | **시각적 무손실 (Perceptual Lossless)** | PSNR-HVS $\ge 42\text{ dB}$, LPIPS $\le 0.02$, Butteraugli $< 1.0$ |
| **표준 호환성** | **100% ISO/IEC 10918-1 JPEG 규격** | 일반 JFIF 비트스트림 출력 (모든 뷰어/SNS 완벽 호환) |
| **발열 및 배터리** | NPU/CPU 부하 최소화 | NPU INT8 경량 추론 + `dmabuf` Zero-Copy 메모리 전달 |

---

## 2. 6단계 엔드투엔드 파이프라인 구조표

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

| 단계 | 처리 단계명 | 실행 하드웨어 | 입·출력 데이터 | 소요 시간 | 압축 기여도 | 핵심 최적화 기법 |
| :---: | :--- | :---: | :--- | :---: | :---: | :--- |
| **1** | **공간 도메인 노이즈 쉐이핑** | NPU / DSP | **In**: 12MP YUV<br>**Out**: 정돈된 YUV | `< 0.20ms` | `+5% ~ 10%` | 센서 고주파 노이즈를 DCT 기저함수와 상쇄 정돈 |
| **2** | **전역 DQT 예측 (Micro-QuantNet)** | Samsung NPU | **In**: 256x192 + 메타데이터<br>**Out**: 64B $Q_Y, Q_C$ | `< 0.15ms` | `+12% ~ 18%` | 인간 시각 감도(CSF) 기반 64개 주파수 가중치 회귀 |
| **3** | **블록 단위 적응형 Dead-Zone RDO** | ARM NEON | **In**: 8x8 DCT 계수<br>**Out**: 양자화 계수 | `~ 1.20ms` | `+10% ~ 15%` | 평탄 영역 불감대 마스킹 & Fast-EOB 조기 절단 |
| **4** | **시맨틱 Chroma 모드 전환** | CPU Native | **In**: 씬 분류 태그<br>**Out**: 서브샘플링 포맷 | `< 0.05ms` | `+3% ~ 5%` | 문서/텍스트 4:4:4 vs 일반 4:2:0 자동 스위칭 |
| **5** | **1-Pass 샘플링 Fast-DHT** | CPU Native | **In**: 1/16 샘플링 히스토그램<br>**Out**: 커스텀 DHT | `< 0.10ms` | `+5% ~ 8%` | 2-Pass 스캔 없이 0.08ms 만에 맞춤형 허프만 트리 생성 |
| **6** | **DRI 기반 4코어 병렬 결합** | 4-Core CPU | **In**: 4개 분할 MCU 밴드<br>**Out**: 표준 JFIF 파일 | `~ 2.00ms` | `속도 3배↑` | Restart Marker 기반 락-프리 메모리 스트라이핑 |
| **★** | **전체 파이프라인 종합** | **NPU + 4-Core** | **12MP YUV $\rightarrow$ 표준 JPEG** | **$\approx 3.60\text{ms}$** | **총 25%~35%** | **목표 5ms 대비 약 30% 마진 확보** |

---

## 3. 기존 룰 기반 DQT vs 제안 6단계 AI 솔루션 비교표

| 비교 항목 | 기존 룰 기반 자체 DQT 방식 | 제안 6단계 AI 솔루션 (`AICodec`) |
| :--- | :--- | :--- |
| **양자화 방식** | 이미지 전체에 1개의 정적/선형 DQT 적용 | **AI 전역 DQT + 블록별 적응형 불감대(Dead-Zone) 융합** |
| **센서 노이즈 처리** | 고주파 노이즈가 DCT AC 계수로 변환되어 비트 낭비 | **AI Noise Shaping으로 고주파 노이즈 사전 소거** |
| **허프만 코딩** | 표준 고정 테이블(1992 권고안) 사용 | **1/16 고속 샘플링 기반 1-Pass Dynamic Huffman (DHT)** |
| **RDO (율-왜곡 최적화)** | 없음 (단순 나눗셈 반올림) | **Fast-EOB 조기 절단 (블록당 10~20비트 절감)** |
| **멀티스레딩 구조** | 스레드 간 동기화 락 발생 가능성 존재 | **Restart Marker (`DRI`) 기반 완전 Lock-Free 스트라이핑** |
| **동일 화질 기준 용량** | 기준치 ($100\%$) | **$65\% \sim 75\%$ ($25\% \sim 35\%$ 추가 절감)** |
| **처리 레이턴시 (12MP)** | 약 $4.5\text{ms} \sim 6.0\text{ms}$ | **약 $3.60\text{ms}$ (안정적 5ms 이내 보장)** |

---

## 4. 하드웨어 리소스 할당 및 스케줄링 구조표

| 프로세서 / 엔진 | 할당 작업 | 실행 기법 및 최적화 | 소요 시간 |
| :--- | :--- | :--- | :---: |
| **Samsung NPU** | Micro-QuantNet 추론 | INT8 양자화, Stride Zero-Copy 메모리 바인딩 | `0.15ms` |
| **Cortex-X4 (Prime)** | MCU Row 0 ~ 46 인코딩 + DHT 생성 | NEON SIMD + Sampling Fast-DHT | `3.30ms` |
| **Cortex-A720 #1 (Gold)** | MCU Row 47 ~ 93 인코딩 | NEON SIMD Dead-Zone Quantization | `3.20ms` |
| **Cortex-A720 #2 (Gold)** | MCU Row 94 ~ 140 인코딩 | NEON SIMD Dead-Zone Quantization | `3.20ms` |
| **Cortex-A720 #3 (Gold)** | MCU Row 141 ~ 187 인코딩 | NEON SIMD Dead-Zone Quantization | `3.20ms` |
| **Main Thread** | JFIF 헤더 결합 & 최종 파일 패키징 | $O(1)$ 메모리 포인터 링크 (`memcpy` 최소화) | `0.05ms` |

---

## 5. 정량적 검증 및 A/B 테스트 매트릭스

### 5.1 씬(Scene)별 테스트 데이터셋 구조표 (총 1,000장 이상)

| 씬 분류 | 주요 특성 | 주요 검증 항목 | 목표 화질 메트릭 |
| :--- | :--- | :--- | :--- |
| **고감도 야경** | $\text{ISO} \ge 1600$, 암부 노이즈 | 노이즈 소거율, 암부 계조 뭉개짐 방지 | PSNR-HVS $\ge 40\text{ dB}$ |
| **인물 / 셀피** | 얼굴 피부톤, 눈동자, 머리카락 | 피부 텍스처 보존, 배경 보케 압축률 | LPIPS $\le 0.015$ |
| **풍경 / 자연** | 나뭇잎, 잔디, 복잡한 고주파 텍스처 | 나뭇잎 디테일 유지, 에지 링잉 방지 | MS-SSIM $\ge 0.985$ |
| **문서 / 텍스트** | 영수증, 표지판, 텍스트 에지 | 글자 가독성, 색상 번짐(Chroma bleeding) 방지 | Butteraugli $< 0.8$ |
| **그라데이션** | 하늘, 단색 벽면 | 컬러 밴딩(블로킹) 아티팩트 발생 차단 | PSNR $\ge 44\text{ dB}$ |

### 5.2 정량 평가 지표 정의표

| 평가 지표 | 지표 설명 | 합격 기준 (Target Threshold) |
| :--- | :--- | :--- |
| **BD-Rate (용량 절감)** | 동일 화질 곡선 기준 비트레이트 절감률 | **$\ge 25.0\%$ 절감** |
| **LPIPS** | 딥러닝 기반 인간 시각 인지 왜곡 거리 | **$\le 0.020$** (인간 육안 구별 불가) |
| **PSNR-HVS-M** | 인간 시각 특성 및 마스킹 반영 PSNR | **$\ge 42.0\text{ dB}$** |
| **Butteraugli** | 구글 시각 왜곡 감지 척도 | **$< 1.0$** (시각적 왜곡 인지 한계선 미만) |
| **End-to-End Latency** | 12MP 캡처에서 JPEG 완성까지 전체 시간 | **$\le 4.5\text{ms}$** (5.0ms 상한선 대비 마진) |

---

## 6. 단계별 마일스톤 및 산출물 일정표

| 단계 | 기간 | 주요 개발 내용 | 산출물 | 완료 기준 |
| :---: | :---: | :--- | :--- | :--- |
| **Phase 1** | 1~2주 | PyTorch MicroQuantNet & Differentiable JPEG 학습 | `micro_quant_net.pth`, R-D 손실 함수 | BD-Rate 20% 이상 향상 검증 |
| **Phase 2** | 3~4주 | ONNX $\rightarrow$ TFLite INT8 경량화 및 NPU 포팅 | `micro_quant_net_int8.tflite`, C++ NPU Runner | 갤럭시 NPU 추론 $\le 0.15\text{ms}$ |
| **Phase 3** | 5~6주 | 자체 SW 코덱 소스에 NEON Dead-Zone & Fast-DHT 통합 | `FastJpegQuantizer.cpp`, DRI 병렬 파이프라인 | 4코어 SW 인코딩 $\le 3.45\text{ms}$ |
| **Phase 4** | 7~8주 | 1,000장 실기기 A/B 벤치마크 & 발열/배터리 QA | 종합 성능 리포트, 최종 릴리즈 바이너리 | 12MP $\le 5\text{ms}$, 25~35% 용량 절감 |
