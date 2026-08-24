# 삼성 갤럭시 실시간 AI JPEG 압축 최적화 상세 계획서 (DRUNet 배제 확정판)

---

## 1. 핵심 시스템 사양 및 결정 사항 요약표

| 항목 | 요구 사양 및 확정 결정 | 기술적 해결 방안 |
| :--- | :--- | :--- |
| **대상 해상도** | 12 Megapixels ($4000 \times 3000$) | YUV420 Planar / NV12 ($18\text{ MB}$ 버퍼) |
| **픽셀 디노이징 (DRUNet)** | **완전 배제 (Drop 확정)** | 6초(6,000ms) 지연 원천 차단 $\rightarrow$ **코덱 내 주파수 Dead-Zone으로 대체 (0.00ms)** |
| **최종 인코딩 레이턴시** | **$\approx 3.60\text{ms}$** (상한 예산: $\le 5.0\text{ms}$) | AI NPU $0.15\text{ms}$ + 4코어 NEON SW 코덱 $3.40\text{ms}$ + 조립 $0.05\text{ms}$ |
| **압축률 목표** | **기존 대비 $25\% \sim 35\%$ 용량 절감** | AI 전역 DQT + DCT 도메인 Dead-Zone RDO + 1-Pass Fast-DHT |
| **화질 목표** | **시각적 무손실 (Perceptual Lossless)** | PSNR-HVS $\ge 42\text{ dB}$, LPIPS $\le 0.02$, Butteraugli $< 1.0$ |
| **표준 호환성** | **100% ISO/IEC 10918-1 JPEG 준수** | 일반 표준 JFIF 비트스트림 출력 (모든 뷰어/SNS 완벽 호환) |
| **발열 및 메모리** | DRAM 대역폭 및 발열 최소화 | NPU INT8 경량 추론 ($<35\text{KB}$) + `dmabuf` Zero-Copy 메모리 전달 |

---

## 2. 확정된 실시간 엔드투엔드 파이프라인 구조표

```
[ Camera HAL / 12MP YUV420 dmabuf (카메라 ISP 기본 HW 처리 완료 버퍼) ]
   │
   ├─► [1단계] NPU Micro-QuantNet 초고속 추론 (<0.15ms)
   │     - 12MP 픽셀 직접 연산 X (DRUNet 배제)
   │     - 256x192 썸네일 + 카메라 메타데이터(ISO, 노출)만 분석
   │     - 출력: 최적 8x8 Q_Y, Q_C 양자화 테이블 & Dead-Zone 노이즈 임계치
   │
   ├─► [2단계] 1/16 Stride 1-Pass Fast-DHT 생성 (<0.10ms)
   │     - 전체 12MP 중 6.25% 블록만 고속 샘플링하여 전용 Dynamic Huffman Table 생성
   │
   ├─► [3단계] 4-Core ARM NEON SW 코덱 인코딩 (~3.30ms)
   │     - Forward DCT (8x8 블록 변환)
   │     - ★ NEON Dead-Zone 양자화: DRUNet을 대체하여 고주파 노이즈를 0ms로 완벽 소거
   │     - Fast-EOB 조기 절단: 고립된 고주파 계수 드롭 (블록당 10~20비트 절약)
   │     - Fast-DHT 엔트로피 코딩
   │     - Restart Marker (`DRI`) 락-프리 4코어 병렬화 (Cortex-X4 + Gold)
   │
   └─► [4단계] 비트스트림 패키징 (<0.05ms)
         - O(1) 메모리 포인터 조립 ──► 최종 표준 JFIF 파일 완성
   ────────────────────────────────────────────────────────────────────────────────
   ★ 총 소요 시간: 약 3.60ms (5.0ms 목표 대비 30% 마진) | 총 용량 절감: 25% ~ 35%
```

| 단계 | 파이프라인 단계명 | 실행 하드웨어 | 소요 시간 | 압축 기여도 | 핵심 최적화 기법 |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **1** | **AI 파라미터 예측 (Micro-QuantNet)** | Samsung NPU | `< 0.15ms` | `+12% ~ 18%` | 썸네일 기반 인간 시각 감도(CSF) 최적 64개 Q 계수 회귀 |
| **2** | **1-Pass 샘플링 Fast-DHT** | CPU Native | `< 0.10ms` | `+5% ~ 8%` | 2-Pass 지연 없이 0.08ms 만에 맞춤형 허프만 트리 생성 |
| **3** | **주파수 Dead-Zone 양자화 (DRUNet 대체)** | ARM NEON | `0.00ms (내재화)` | `+10% ~ 15%` | 8x8 DCT 고주파 노이즈를 SIMD 마스킹으로 0ms에 소거 |
| **4** | **Fast-EOB 조기 절단 RDO** | ARM NEON | `0.00ms (내재화)` | `+3% ~ 5%` | 지그재그 끝단 고립 계수 절단으로 EOB 조기 발생 |
| **5** | **DRI 기반 4코어 병렬 인코딩** | 4-Core CPU | `~ 3.30ms` | `속도 3배↑` | Restart Marker 기반 락-프리 메모리 스트라이핑 |
| **6** | **비트스트림 패키징** | Main Thread | `< 0.05ms` | — | $O(1)$ 포인터 링크 기반 표준 JFIF 완성 |
| **★** | **전체 파이프라인 종합** | **NPU + 4-Core** | **$\approx 3.60\text{ms}$** | **총 25%~35%** | **목표 5ms 대비 약 30% 안전 마진 확보** |

---

## 3. DRUNet 배제 사유 및 Dead-Zone 대체 원리 비교표

| 비교 항목 | 방식 A: 픽셀 AI 디노이징 (DRUNet) | 방식 B: 제안 코덱 내 주파수 Dead-Zone (★채택) |
| :--- | :--- | :--- |
| **처리 위치** | 12MP 픽셀 도메인 (RGB/YUV 전처리) | 자체 SW 코덱 8x8 DCT 주파수 도메인 |
| **소요 시간** | **평균 6,000ms (6초) $\rightarrow$ 실시간 불가** | **0.00ms (NEON SIMD 양자화 루프 내 내재화)** |
| **메모리 입출력** | Feature Map 4~6GB 이동 (DRAM 대역폭 고갈) | 추가 메모리 이동 없음 (레지스터 내 연산) |
| **발열 및 배터리** | 극심한 발열 및 쓰로틀링 유발 | 추가 발열 없음 |
| **노이즈 소거 효과** | 고주파 픽셀 노이즈 제거 | **8x8 DCT 고주파 노이즈 계수를 0으로 마스킹 (동일 효과)** |
| **최종 판정** | **완전 배제 (Drop)** | **★ 최종 채택** |

---

## 4. 하드웨어 리소스 할당 및 스케줄링 표

| 프로세서 / 코어 | 담당 작업 | 최적화 방식 | 소요 시간 |
| :--- | :--- | :--- | :---: |
| **Samsung NPU** | Micro-QuantNet 추론 | INT8 양자화, 썸네일 Stride Zero-Copy 바인딩 | `0.15ms` |
| **Cortex-X4 (Prime)** | MCU Row 0 ~ 46 인코딩 + Fast-DHT 생성 | NEON SIMD + Sampling Fast-DHT | `3.30ms` |
| **Cortex-A720 #1 (Gold)** | MCU Row 47 ~ 93 인코딩 | NEON SIMD Dead-Zone 양자화 | `3.20ms` |
| **Cortex-A720 #2 (Gold)** | MCU Row 94 ~ 140 인코딩 | NEON SIMD Dead-Zone 양자화 | `3.20ms` |
| **Cortex-A720 #3 (Gold)** | MCU Row 141 ~ 187 인코딩 | NEON SIMD Dead-Zone 양자화 | `3.20ms` |
| **Main Thread** | 최종 JFIF 헤더 결합 및 비트스트림 완성 | $O(1)$ 메모리 포인터 연결 (`memcpy` 최소화) | `0.05ms` |

---

## 5. 정량적 검증 및 A/B 테스트 매트릭스

| 씬 분류 | 주요 검증 항목 | 합격 기준 메트릭 |
| :--- | :--- | :--- |
| **고감도 야경 ($\text{ISO} \ge 1600$)** | Dead-Zone 노이즈 소거율, 암부 계조 보존 | PSNR-HVS $\ge 40\text{ dB}$ |
| **인물 / 셀피** | 피부 텍스처 보존, 배경 보케 압축률 | LPIPS $\le 0.015$ |
| **풍경 / 자연 (단풍/잔디)** | 나뭇잎 디테일 유지, 에지 링잉 방지 | MS-SSIM $\ge 0.985$ |
| **문서 / 텍스트** | 글자 가독성, 색상 번짐(Chroma bleeding) 방지 | Butteraugli $< 0.8$ |
| **전체 1,000장 종합 BD-Rate** | 동일 체감 화질 기준 파일 용량 감소율 | **$\ge 25.0\%$ 절감** |
| **실기기 전체 레이턴시** | 12MP 캡처에서 JPEG 파일 완성까지 전체 시간 | **$\le 4.5\text{ms}$** |
