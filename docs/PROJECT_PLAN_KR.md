# 삼성 갤럭시 실시간 AI JPEG 압축 최적화 상세 프로젝트 계획서
**목표 성능**: 12MP 이미지 기준 $\le 5\text{ms}$ 인코딩 | **화질 목표**: 시각적 무손실 (PSNR-HVS / LPIPS) | **대상 플랫폼**: 삼성 갤럭시 (Exynos / Snapdragon)

---

## 1. 프로젝트 개요 및 배경

### 1.1 핵심 과제 및 한계점
* **12MP 대용량 데이터**: $4000 \times 3000$ 해상도의 YUV420 버퍼 크기는 **$18\text{ MB}$**로, 5ms 이내 처리를 위해서는 초당 **2.4 Gigapixels / 3.6 GB/s** 이상의 처리 대역폭이 필요합니다.
* **단순 DQT 테이블 튜닝의 한계**: 이미지별 전역 DQT(양자화 테이블) 튜닝만으로는 압축률 향상에 명확한 한계가 존재합니다.
* **본 솔루션의 핵심 철학**: 표준 JPEG 규격(디코더)을 100% 준수하면서, **[공간 도메인 전처리 $\rightarrow$ 전역 양자화 $\rightarrow$ 블록 단위 RDO $\rightarrow$ 색차/주파수 변환 $\rightarrow$ 엔트로피 코딩 $\rightarrow$ 4코어 병렬화]**의 **6단계 멀티레이어 통합 최적화**를 통해 12MP 5ms 이내 25~35% 압축률 개선을 달성합니다.

---

## 2. 6단계 엔드투엔드 파이프라인 아키텍처

```
[12MP YUV420 입력 버퍼 (AHardwareBuffer / dmabuf Zero-Copy)]
   │
   ├─► ① [공간 도메인] AI-Guided Sub-band Noise Shaping & JND 맵 추출 (<0.20ms)
   │     - 센서 고주파 노이즈가 DCT 비트를 낭비하지 않도록 평탄 영역 미세 잡음 사전 정돈
   │
   ├─► ② [전역 주파수 양자화] AI Micro-QuantNet: 최적 DQT 테이블 예측 (<0.15ms)
   │     - 64개 주파수별 인간 시각 감도(CSF) 기반 최적 Q_Y, Q_C 행렬 산출
   │
   ├─► ③ [블록 레벨 양자화] AI Block-Adaptive Dead-Zone & Fast Trellis RDO (~1.20ms)
   │     - ★ [핵심] 표준 디코더 호환을 유지하며 인코더 내부에서 블록별/계수별 차등 양자화!
   │     - 엣지/얼굴 블록: 원본 디테일 100% 보존
   │     - 배경/보케 블록: 불감대(Dead-Zone)를 넓혀 미세 고주파 계수 강제 소거
   │     - Fast-EOB (End-of-Block): 지그재그 스캔 끝단의 고립된 계수 조기 절단
   │
   ├─► ④ [주파수/색차 변환] Semantic Chroma Mode Dynamic Switching (<0.05ms)
   │     - 텍스트/문서: 4:4:4 or 4:2:2 전환 (색상 번짐 방지)
   │     - 인물/풍경/야경: 4:2:0 + Chroma 고주파 컷오프
   │
   ├─► ⑤ [엔트로피 코딩] 1-Pass Sampling Dynamic Huffman Table (DHT) (<0.10ms)
   │     - 30년 된 고정 테이블 폐기 ──► 1/16 블록 고속 샘플링 기반 맞춤형 Huffman Tree 생성
   │
   └─► ⑥ [하드웨어 병렬화] Restart Marker (`DRI`) 기반 Lock-Free 4-Core NEON (~2.00ms)
         - 12MP를 4개 밴드로 분할하여 스레드 동기화 락 없이 병렬 인코딩 후 O(1) 메모리 결합
   ────────────────────────────────────────────────────────────────────────────────
   ★ 총 소요 시간: ~3.60ms (< 5ms) | 총 용량 절감: 25% ~ 35% | 표준 JPEG 100% 호환
```

---

## 3. 세부 최적화 기술 분석

### 3.1 [Stage 1] AI-Guided Sub-band Noise Shaping (공간 도메인 전처리)
* **원리**: 카메라 센서의 Shot Noise/Thermal Noise는 육안으로는 인지되지 않지만, 8x8 DCT 변환 시 막대한 고주파 AC 에너지를 생성하여 파일 크기의 30% 이상을 낭비합니다.
* **구현**: 엣지 방향성을 보존하는 고속 그래디언트 필터와 AI JND 맵을 결합하여, 평탄/그림자 영역의 노이즈를 8x8 DCT 기저함수와 상쇄되는 형태로 정돈합니다.

### 3.2 [Stage 2] AI Micro-QuantNet (전역 주파수 DQT 예측)
* **원리**: 썸네일($256 \times 192$)과 카메라 메타데이터(ISO, 노출, 조도, Face ROI)를 입력받아 64개 주파수별 인간 시각 감도(CSF)에 최적화된 $Q_Y^*, Q_C^*$ 행렬을 회귀 예측합니다.
* **스펙**: 파라미터 약 32k개, INT8 양자화 모델 크기 $<35\text{KB}$, 삼성 NPU에서 **0.12ms ~ 0.15ms** 내 추론 완료.

### 3.3 [Stage 3] Block-Adaptive Dead-Zone & Fast Trellis RDO (블록별 양자화)
* **원리**: 표준 JPEG 디코더는 역양자화 시 `Deq = Q * Coeff`만 수행하므로, 인코더 내부의 계수 결정(Rounding/Truncation)은 100% 자유롭습니다.
* **적응형 불감대 (Dead-Zone)**:
  * 텍스처/에지 블록: Dead-Zone = 0 (원음 보존)
  * 평탄/보케 블록: $|C| \le \text{Threshold}$ 인 미세 계수를 0으로 소거하여 연속 0 Run-length를 극대화.
* **Fast-EOB (End-of-Block) 조기 절단**:
  * 지그재그 스캔 40~63번 고주파 영역에 홀로 남은 $\pm 1$ 계수를 0으로 절단하고 `EOB` 마커를 조기 발생시켜 블록당 10~20비트 절약.

### 3.4 [Stage 4] Semantic Chroma Mode Dynamic Switching (색차 변환)
* AI 씬 분류기를 활용하여 문서/텍스트 캡처 시 4:4:4 또는 4:2:2로 전환하여 글자 색 번짐을 방지하고, 일반 인물/풍경은 4:2:0으로 최대 압축률을 확보합니다.

### 3.5 [Stage 5] 1-Pass Sampling Dynamic Huffman Table (Fast-DHT)
* 기존 2-Pass 스캔의 1.5ms 지연을 회피하기 위해, $1/16$ 스트라이드 샘플링(전체의 6.25%)으로 0.08ms 만에 고정확도 통계 히스토그램을 추출하고 전용 맞춤형 DHT를 생성합니다.

### 3.6 [Stage 6] Restart Marker (`DRI`) 기반 Lock-Free 4-Core SIMD 인코딩
* 12MP 이미지(188 MCU 행)를 4개 독립 밴드로 나누어 Cortex-X4 및 A720 코어에서 Mutex Lock 없이 병렬 인코딩합니다.
* 각 스레드가 별도의 메모리 버퍼에 비트스트림을 기록한 후, 헤더와 $O(1)$ 포인터 링크로 최종 JPEG을 조립합니다.

---

## 4. 기법별 기여도 분석 (Ablation Study Matrix)

| 최적화 기법 | 파이프라인 단계 | 압축률 기여도 | 처리 시간 | 표준 호환성 |
| :--- | :--- | :--- | :--- | :--- |
| **1. AI Micro-QuantNet (DQT)** | 전역 주파수 양자화 | **+12% ~ 18%** | 0.15ms (NPU) | 100% |
| **2. Block-Adaptive Dead-Zone & Fast EOB** | 블록별 RDO 양자화 | **+10% ~ 15%** | 0.00ms (NEON 내재화) | 100% |
| **3. 1-Pass Sampling Dynamic Huffman (DHT)** | 엔트로피 코딩 | **+5% ~ 8%** | 0.10ms (CPU) | 100% |
| **4. AI Noise Shaping** | 전처리 공간 도메인 | **+5% ~ 10%** | 0.20ms (NPU/NEON) | 100% |
| **5. DRI 4-Core Lock-Free SIMD** | 병렬 처리 스케줄링 | 인코딩 속도 **3배 가속** | 전체 ~3.30ms 달성 | 100% |
| **★ 종합 시너지 효과** | **전체 파이프라인** | **총 25% ~ 35% 절감** | **총 ~3.60ms (<5ms)** | **100% 표준 JPEG** |

---

## 5. 정량적 검증 및 A/B 테스트 전략

### 5.1 테스트 데이터셋 구성 (1,000장 이상)
* **야경 / 고감도 ($\text{ISO} \ge 1600$)**: 센서 노이즈 억제 및 암부 디테일 보존 검증.
* **인물 / 피부톤**: 얼굴 텍스처, 눈/머리카락 선명도 및 배경 아웃포커스 보케 압축률 검증.
* **풍경 및 미세 텍스처**: 나뭇잎, 잔디, 글자 엣지 링잉 현상 억제 검증.
* **평탄면 및 그라데이션 (하늘, 벽)**: 색상 밴딩(블로킹) 억제 검증.

### 5.2 평가 메트릭
* **BD-Rate (Bjøntegaard Delta Rate)**: 동일 화질에서 절감되는 용량 백분율(%).
* **LPIPS (Learned Perceptual Image Patch Similarity)**: $\le 0.02$ (육안 구별 불가 수준).
* **PSNR-HVS-M**: $\ge 42\text{ dB}$ 유지.
* **Butteraugli Score**: $< 1.0$ (시각적 왜곡 감지 한계선 이하).
* **인코딩 지연 시간**: 갤럭시 S24/S25 실측 전체 인코딩 시간 ($< 5\text{ms}$).

---

## 6. 단계별 개발 로드맵

| 단계 | 주요 마일스톤 | 산출물 | 예상 기간 |
| :--- | :--- | :--- | :--- |
| **Phase 1** | **알고리즘 및 PyTorch 모델 학습** | - Differentiable JPEG Loss 및 MicroQuantNet 학습<br>- BD-Rate 곡선 검증 | 1 ~ 2 주 |
| **Phase 2** | **INT8 경량화 및 NPU 포팅** | - ONNX $\rightarrow$ TFLite INT8 변환<br>- 삼성 ENN/NPU 추론 0.15ms 실측 확인 | 3 ~ 4 주 |
| **Phase 3** | **자체 SW 코덱 소스 통합** | - NEON Dead-Zone 양자화 및 Fast-DHT C++ 통합<br>- DRI 기반 멀티스레드 파이프라인 결합 | 5 ~ 6 주 |
| **Phase 4** | **갤럭시 단말 실기기 튜닝 및 A/B QA** | - 기존 자체 DQT 대비 화질/용량 정량 벤치마크<br>- 발열 및 배터리 소모 프로파일링 및 최종 배포 | 7 ~ 8 주 |
