# 삼성 갤럭시 실시간 AI JPEG 압축 최적화 프로젝트 계획서
**목표 성능**: 12MP 이미지 기준 $\le 5\text{ms}$ 인코딩 | **화질 목표**: 시각적 무손실 (PSNR-HVS / LPIPS) | **대상 플랫폼**: 삼성 갤럭시 (Exynos / Snapdragon)

---

## 1. 프로젝트 개요 및 제약 조건 분석

### 1.1 주요 요구사항 및 성능 한계점
1. **해상도**: 12 Megapixels ($4000 \times 3000$) YUV420 버퍼 ($18\text{ MB}$).
2. **시간 제약**: 실시간 카메라 촬영 파이프라인 내 프레임당 **$5\text{ms}$ 이하** 처리.
3. **표준 호환성**: ISO/IEC 10918-1 표준 JPEG (JFIF) 규격 100% 준수 (전 세계 모든 브라우저, SNS, 갤러리 앱에서 별도 디코더 없이 호환).
4. **압축률 목표**: 기존 룰 기반 자체 DQT 대비 동일 체감 화질에서 **$20\% \sim 35\%$ 파일 용량 절감**.
5. **발열 및 배터리**: NPU 추론 시간 $0.15\text{ms}$ 이내, CPU/메모리 버스 대역폭 부하 최소화.

---

## 2. 시스템 아키텍처 및 엔드투엔드 파이프라인

```
[ Camera HAL / 12MP YUV420 dmabuf 버퍼 ]
                    │
                    ├─► [ Step 1: NPU Micro-QuantNet 추론 (<0.15ms) ]
                    │     - 입력: Stride 샘플링된 256x192 Luma + 카메라 메타데이터 (ISO, 노출, ROI)
                    │     - 출력: 최적 8x8 Q_Y, Q_C 양자화 테이블 및 Dead-Zone 노이즈 임계치
                    │
                    ├─► [ Step 2: 1/16 Stride Fast-DHT 생성 (<0.10ms) ]
                    │     - 전체 12MP 블록의 6.25%만 고속 샘플링
                    │     - 1-Pass 전용 Dynamic Huffman Table (DHT) 빌드
                    │
                    ├─► [ Step 3: 4-Core 병렬 SIMD SW 코덱 인코딩 (~3.30ms) ]
                    │     - ARM NEON Forward DCT
                    │     - NEON SIMD Dead-Zone 양자화 (시각적 무의미 고주파 노이즈 소거)
                    │     - Restart Marker (DRI / RST0~RST7) 기반 락-프리 멀티스레딩 (Cortex-X + Gold)
                    │
                    └─► [ Step 4: 비트스트림 결합 (<0.05ms) ]
                          - 최종 표준 JFIF 파일 완성 (25~35% 용량 절감)
                          - 전체 소요 시간: 약 3.60ms (5ms 목표 대비 30% 여유)
```

---

## 3. AI DQT 생성 모델: Micro-QuantNet 아키텍처 및 학습 설계

### 3.1 신경망 아키텍처 설계
* **백본 (Backbone)**: 4단계 Depthwise-Separable ConvNet ($3\times 3$, Stride 2)
* **메타데이터 융합**: $[ \text{ISO}_{\text{norm}}, \text{Exp}_{\text{norm}}, \text{MeanBrightness}, \text{FaceFlag} ]$ 선형 프로젝션 및 결합
* **회귀 헤드 (Regression Head)**: 기본 JPEG 테이블에 곱해질 128개 가중치 승수 출력 ($Q_Y$ 64개, $Q_C$ 64개).
* **모델 크기**: 파라미터 수 약 **32k개** (INT8 양자화 시 **$\sim 35\text{KB}$**).
* **추론 속도**: 삼성 갤럭시 NPU (ENN SDK) / 퀄컴 Hexagon 기준 **$0.12\text{ms} \sim 0.15\text{ms}$**.

### 3.2 학습 손실 함수 (미분 가능한 JPEG R-D 손실)
$$\mathcal{L}_{\text{total}} = \mathcal{L}_{\text{perceptual}}(\hat{I}, I) + \lambda \cdot \mathcal{L}_{\text{rate}}(Q_Y, Q_C)$$
* $\mathcal{L}_{\text{perceptual}} = \mathcal{L}_{\text{L1}} + \alpha \mathcal{L}_{\text{MS-SSIM/LPIPS}}$ (인간 시각 왜곡 최소화)
* $\mathcal{L}_{\text{rate}} = \mathbb{E}[\log_2(1 + |C_{\text{quantized}}|)]$ (허프만 비트스트림 길이 대리 손실)
* $\lambda$: 목표 품질에 따른 Rate-Distortion 조절 계수.

---

## 4. 자체 SW 코덱 내부 최적화 기법 (Native C++)

1. **ARM NEON SIMD Dead-Zone 양자화**:
   * `vabsq_s16`, `vcgtq_s16`, `vandq_u16` 명령어를 활용하여 인간 눈에 보이지 않는 고주파 노이즈 성분을 양자화 곱셈 전 0으로 마스킹.
   * 내부 SIMD 루프에 추가 사이클 지연 없이 허프만 Run-length 대폭 감소.
2. **1-Pass 샘플링 Dynamic Huffman Table (Fast-DHT)**:
   * 기존 2-Pass 허프만의 1.5ms 스캔 지연을 제거하고, $1/16$ 스트라이드 샘플링을 통해 $<0.08\text{ms}$ 내에 최적 DHT 구성.
3. **Restart Marker (`DRI`) 락-프리 멀티스레딩**:
   * 12MP 이미지(188 MCU 행)를 4개 독립 밴드로 분할하여 Cortex-X 및 Gold 코어에서 동기화 락 없이 병렬 인코딩.

---

## 5. 정량적 검증 및 A/B 테스트 전략 (기존 자체 DQT 대비)

### 5.1 테스트 데이터셋 구성 (1,000장 이상)
* **야경 / 고감도 ($\text{ISO} \ge 1600$)**: 센서 노이즈 억제 및 암부 디테일 보존 검증.
* **인물 / 피부톤**: 얼굴 텍스처, 눈/머리카락 선명도 및 배경 아웃포커스 보케 압축률 검증.
* **풍경 및 미세 텍스처**: 나뭇잎, 잔디, 글자 엣지 링잉 현상 억제 검증.
* **평탄면 및 그라데이션 (하늘, 벽)**: 색상 밴딩(블로킹) 억제 검증.

### 5.2 평가 메트릭
* **BD-Rate (Bjøntegaard Delta Rate)**: 동일 화질에서 절감되는 용량 백분율(%).
* **LPIPS (Learned Perceptual Image Patch Similarity)**: $\le 0.02$ (육안 구별 불가 수준).
* **PSNR-HVS-M**: $\ge 42\text{ dB}$ 유지.
* **Butteraugli Score (구글 시각 왜곡 메트릭)**: $< 1.0$ (시각적 왜곡 한계선 이하).
* **인코딩 지연 시간**: 갤럭시 S24/S25 실측 전체 인코딩 시간 ($< 5\text{ms}$).

---

## 6. 단계별 개발 로드맵

| 단계 | 주요 마일스톤 | 산출물 | 예상 기간 |
| :--- | :--- | :--- | :--- |
| **Phase 1** | **알고리즘 및 PyTorch 모델 학습** | - Differentiable JPEG Loss 및 MicroQuantNet 학습<br>- BD-Rate 곡선 검증 | 1 ~ 2 주 |
| **Phase 2** | **INT8 경량화 및 NPU 포팅** | - ONNX $\rightarrow$ TFLite INT8 변환<br>- 삼성 ENN/NPU 추론 0.15ms 실측 확인 | 3 ~ 4 주 |
| **Phase 3** | **자체 SW 코덱 소스 통합** | - NEON Dead-Zone 양자화 및 Fast-DHT C++ 통합<br>- DRI 기반 멀티스레드 파이프라인 결합 | 5 ~ 6 주 |
| **Phase 4** | **갤럭시 단말 실기기 튜닝 및 A/B QA** | - 기존 자체 DQT 대비 화질/용량 정량 벤치마크<br>- 발열 및 배터리 소모 프로파일링 및 최종 배포 | 7 ~ 8 주 |
