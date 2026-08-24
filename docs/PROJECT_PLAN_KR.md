# 삼성 갤럭시 실시간 AI JPEG 압축 최적화 상세 계획서 (최종 상세 명세판)

---

## 1. 핵심 시스템 사양 및 결정 사항 요약표

| 항목 | 요구 사양 및 확정 결정 | 기술적 해결 방안 |
| :--- | :--- | :--- |
| **대상 해상도** | 12 Megapixels ($4000 \times 3000$) | YUV420 Planar / NV12 ($18\text{ MB}$ 버퍼) |
| **최종 인코딩 레이턴시** | **$\approx 3.60\text{ms}$** (상한 예산: $\le 5.0\text{ms}$) | AI NPU $0.15\text{ms}$ + 4코어 NEON SW 코덱 $3.30\text{ms}$ + 조립 $0.05\text{ms}$ |
| **압축률 목표** | **기존 대비 $25\% \sim 35\%$ 용량 절감** | AI 전역 DQT + DCT 도메인 Dead-Zone RDO + 1-Pass Fast-DHT |
| **화질 목표** | **시각적 무손실 (Perceptual Lossless)** | PSNR-HVS $\ge 42\text{ dB}$, LPIPS $\le 0.02$, Butteraugli $< 1.0$ |
| **표준 호환성** | **100% ISO/IEC 10918-1 JPEG 준수** | 일반 표준 JFIF 비트스트림 출력 (모든 뷰어/SNS 완벽 호환) |
| **발열 및 메모리** | DRAM 대역폭 및 발열 최소화 | NPU INT8 경량 추론 ($<35\text{KB}$) + `dmabuf` Zero-Copy 메모리 전달 |

---

## 2. 확정된 실시간 엔드투엔드 파이프라인 구조도

```
[ Camera HAL / 12MP YUV420 dmabuf ]
   │
   ├─► [1단계] NPU Micro-QuantNet 초고속 추론 (<0.15ms)
   │     └─► Output: 8x8 Q_Y, Q_C 양자화 테이블 (128B) + Dead-Zone 노이즈 임계치
   │
   ├─► [2단계] 1-Pass Sampling Fast-DHT 생성 (<0.10ms)
   │     └─► Output: 이미지 맞춤형 Dynamic Huffman Table 바이너리 세그먼트
   │
   ├─► [3단계] 4-Core ARM NEON SW 코덱 병렬 인코딩 (~3.30ms)
   │     └─► Output: 4개의 독립 압축 비트스트림 청크 (Chunk 0~3)
   │
   └─► [4단계] 비트스트림 패키징 및 JFIF 완성 (<0.05ms)
         └─► Output: 최종 표준 JPEG 파일 (100% 호환, 25~35% 용량 절감)
   ─────────────────────────────────────────────────────────────────────────────
   ★ 전체 파이프라인 총 소요 시간: 약 3.60ms (목표 5.0ms 대비 30% 안전 마진 확보)
```

---

## 3. 단계별 작업 내용, 기대 결과 및 Output 상세 정의표

### 3.1 [1단계] NPU AI 파라미터 예측 (`Micro-QuantNet`)
* **작업할 구체적 내용**:
  1. **Zero-Copy 썸네일 바인딩**: 12MP Y-Plane($4000 \times 3000$)에서 가로/세로 16 Stride로 건너뛰며 $256 \times 192$ 썸네일 포인터를 NPU 입력 텐서에 직접 바인딩 (메모리 복사 $0\text{ms}$).
  2. **메타데이터 벡터 구성**: 카메라 드라이버로부터 촬영 정보(`[ISO_norm, Exposure_norm, Mean_Luma, Face_ROI]`)를 4-dim Float 벡터로 추출.
  3. **NPU 추론 실행**: 삼성 NPU(ENN SDK)에서 INT8로 양자화된 `Micro-QuantNet` 실행 ($<35\text{KB}$, 4-Layer ConvNet).
  4. **양자화 행렬 환산**: 출력된 128개 승수와 베이스 테이블을 곱해 $Q_Y[64], Q_C[64]$ 및 Dead-Zone 임계치를 계산.
* **기대되는 결과**:
  * 추론 지연 시간: **$< 0.15\text{ms}$** (NPU INT8 가속).
  * 메모리/발열: 모델 크기 $<35\text{KB}$, DRAM 이동량 $<50\text{KB}$로 버스 부하 제로.
  * 인간 시각 감도(CSF) 최적화로 **용량 12~18% 절감 기반 확보**.
* **최종 Output**:
  * `struct QuantizationMatrices` (총 132 Bytes):
    * `uint8_t qLuma[64]`: 8x8 휘도 양자화 테이블
    * `uint8_t qChroma[64]`: 8x8 색차 양자화 테이블
    * `int16_t deadZoneThresholdLuma`: 휘도 고주파 노이즈 소거 임계치
    * `int16_t deadZoneThresholdChroma`: 색차 고주파 노이즈 소거 임계치

---

### 3.2 [2단계] 1-Pass Sampling Fast-DHT 엔트로피 생성
* **작업할 구체적 내용**:
  1. **1/16 Stride 블록 샘플링**: 12MP 전체 187,500개 $8 \times 8$ 블록 중 **16개 블록당 1개만(6.25%, 약 11,718개 블록) 고속 스캔**.
  2. **히스토그램 누적**: 샘플링된 블록의 DC 차분 카테고리(`freqDc[16]`)와 AC Run-length 심볼(`freqAc[256]`) 빈도수를 고속 누적 ($0.08\text{ms}$).
  3. **허프만 트리 빌드**: 누적 빈도수를 기반으로 16비트 제한 최적 허프만 코드길이(`BITS`)와 심볼값(`HUFFVAL`) 산출.
  4. **DHT 마커 조립**: 표준 JPEG `0xFFC4` (Define Huffman Table) 바이너리 포맷으로 인코딩.
* **기대되는 결과**:
  * 소요 시간: 기존 전체 2-Pass 스캔(1.5ms) 대비 **93% 단축된 $< 0.10\text{ms}$** 달성.
  * 표준 고정 허프만 테이블 대비 **파일 크기 $5\% \sim 8\%$ 추가 절감**.
* **최종 Output**:
  * `struct DynamicHuffmanSegment` (약 420 Bytes):
    * `uint8_t dhtLumaDc[29]`, `dhtLumaAc[178]`, `dhtChromaDc[29]`, `dhtChromaAc[178]`
    * **인코더 고속 룩업 테이블**: `uint16_t huffCode[256]`, `uint8_t huffSize[256]`

---

### 3.3 [3단계] 4-Core ARM NEON SW 코덱 병렬 인코딩
* **작업할 구체적 내용**:
  1. **4개 밴드 작업 분할**: 12MP(188 MCU 행)를 4개 독립 밴드(각 47행)로 분할하고 `DRI = 11,750 MCU` 설정.
  2. **8x8 Forward DCT**: AAN 정수 알고리즘을 128비트 ARM NEON 레지스터 8개로 병렬 연산.
  3. **NEON Dead-Zone 양자화**: `vabsq_s16`, `vcgtq_s16`, `vandq_u16` 명령어로 1단계의 `deadZoneThreshold` 이하 미세 노이즈를 0으로 강제 소거 후 고정소수점 양자화 곱셈 수행.
  4. **Fast-EOB 조기 절단**: 8x8 지그재그 40~63번 고주파 영역의 고립된 $\pm 1$ 계수를 0으로 날려 EOB 마커 조기 발생.
  5. **엔트로피 인코딩**: 2단계의 맞춤형 DHT 룩업 테이블을 참조하여 비트스트림을 각 스레드 버퍼에 기록.
* **기대되는 결과**:
  * 인코딩 레이턴시: Cortex-X4 (1개) + A720 (3개) 병렬 처리 시 **$\approx 3.30\text{ms}$**.
  * 스레드 동기화 락(Lock) 대기 시간 0.00ms (완전 락-프리).
  * Dead-Zone + Fast-EOB 결합으로 **용량 $10\% \sim 15\%$ 추가 절감**.
* **최종 Output**:
  * 4개의 독립 압축 비트스트림 청크 버퍼:
    * `BitstreamChunk chunk[0]`: MCU 0 ~ 46행 압축 데이터 + `0xFFD0 (RST0)`
    * `BitstreamChunk chunk[1]`: MCU 47 ~ 93행 압축 데이터 + `0xFFD1 (RST1)`
    * `BitstreamChunk chunk[2]`: MCU 94 ~ 140행 압축 데이터 + `0xFFD2 (RST2)`
    * `BitstreamChunk chunk[3]`: MCU 141 ~ 187행 압축 데이터 + `0xFFD3 (RST3)`

---

### 3.4 [4단계] 비트스트림 패키징 및 최종 JFIF 파일 생성
* **작업할 구체적 내용**:
  1. 표준 JPEG 헤더 세그먼트 순차 기록 (`SOI`, `APP0`, `DQT`, `SOF0`, `DHT`, `DRI`, `SOS`).
  2. 3단계에서 4개 스레드가 기록한 청크(Chunk 0~3) 버퍼 포인터를 $O(1)$로 헤더 뒤에 결합.
  3. 파일 끝에 `EOI (0xFFD9)` 기록.
* **기대되는 결과**:
  * 소요 시간: **$< 0.05\text{ms}$** ($O(1)$ 메모리 포인터 조립).
  * 100% ISO/IEC 10918-1 표준 준수로 전 세계 모든 뷰어/SNS/웹에서 무수정 100% 즉시 렌더링.
* **최종 Output**:
  * **`최종 표준 JPEG 파일 (Image.jpg)`**:
    * 파일 크기: 기존 대비 **$25\% \sim 35\%$ 절감** (예: 기존 4.5MB $\rightarrow$ 약 3.0MB).
    * 화질 지표: PSNR-HVS $\ge 42\text{ dB}$, LPIPS $\le 0.02$, Butteraugli $< 1.0$.
    * 총 누적 시간: **$\approx 3.60\text{ms}$** (5.0ms 제약 조건 완벽 충족).

---

## 4. 4단계 종합 요약 매트릭스

| 단계 | 처리 단계명 | 실행 유닛 | 핵심 작업 | 기대 성능 (Latency / Gain) | 최종 산출물 (Output) |
| :---: | :--- | :---: | :--- | :---: | :--- |
| **1단계** | **AI 파라미터 예측** | Samsung NPU | 썸네일/메타 분석 및 CSF 가중치 산출 | `< 0.15ms` / `+12~18%` | `QuantizationMatrices` (Q_Y, Q_C, Dead-Zone) |
| **2단계** | **1-Pass Fast-DHT 생성** | CPU Native | 1/16 블록 고속 샘플링 및 허프만 트리 구성 | `< 0.10ms` / `+5~8%` | `DynamicHuffmanSegment` (DHT 바이너리) |
| **3단계** | **4-Core NEON SW 인코딩** | 4-Core CPU | SIMD DCT + Dead-Zone 양자화 + DRI 병렬화 | `~ 3.30ms` / `+10~15%` | `BitstreamChunk[4]` (압축 데이터 청크) |
| **4단계** | **비트스트림 패키징** | Main Thread | 헤더 세그먼트 작성 및 $O(1)$ 포인터 결합 | `< 0.05ms` / `호환성 100%` | **최종 표준 JPEG 파일 (25~35% 용량 절감)** |
| **★** | **전체 파이프라인** | **NPU + 4-Core** | **12MP YUV $\rightarrow$ 표준 JPEG 완결** | **$\approx 3.60\text{ms}$ / 총 25~35% 절감** | **완전한 JFIF 이미지 파일 (<5.0ms)** |
