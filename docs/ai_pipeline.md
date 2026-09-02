# RiskIndex v0.3 알고리즘

> 기준 문서: HS-PDD-002 v2.0 "위험도 엔진과 데이터 전략". 구현: `heatsentry/algorithm/risk_engine.py`,
> `heatsentry/algorithm/baseline.py`, `heatsentry/algorithm/risk_config.py`.
>
> 이 문서는 옛 기획(README 구버전)의 "룰 기반 + ML + 딥러닝 하이브리드" 구상을 대체한다.
> v2.0 기준선은 **1단계(설명 가능한 규칙 기반)만 P1 범위로 확정**하고, ML/TinyML 고도화는
> 실험 데이터가 쌓인 뒤(P2)로 명시적으로 미룬다 — "다중 기능으로 인한 일정 지연"이 PDD가 지목한
> 가장 큰 리스크(R-07)이기 때문이다.

## 왜 규칙 기반인가

RiskIndex는 의료 확률모델이 아니라 **시연·시험 가능한** 지표여야 한다. 심사/운용자가 "왜 이
점수가 나왔는지"를 그 자리에서 설명할 수 있어야 하고(설명 가능성, ALG-001), 센서 하나가 고장 나도
나머지로 계속 동작해야 한다(품질 게이트, ALG-002). 이 두 요구가 로지스틱 회귀나 딥러닝보다 가중
합 + 품질 게이트 방식을 P1에 적합하게 만든다.

## 공식

```
RiskIndex   = 100 * Σ(w_i * q_i * feature_i) / Σ(w_i * q_i)
valid_weight = Σ(w_i * q_i)
if valid_weight < 0.60: SENSOR_LIMITED

HardTrigger = manual_sos OR (fall AND no_motion AND no_response)
```

- `w_i`: 특징별 고정 가중치(표 참고). 합이 1.00이 되도록 설계됐다.
- `q_i`: 그 특징을 만든 센서의 품질(0~1). 접촉 불량·저품질이면 0으로 떨어져 자동으로
  가중합에서 빠지고 나머지가 재정규화된다 — 별도의 "제외 로직"이 아니라 공식 자체가 그렇게
  동작한다(`heatsentry/algorithm/risk_engine.py`의 `RiskEngine.evaluate`).
- `feature_i`: 0~1로 정규화된 위험 신호. 계산식은 `compute_features()` 참고.

구현이 문서 공식과 정확히 같은 변수명을 쓰도록 맞춰 뒀다(`weighted_sum`, `valid_weight`).

## 특징(feature)과 가중치

| 특징 | w | 정의 | 코드 정규화 |
| --- | --- | --- | --- |
| HR_dev | 0.25 | 개인 기준 심박 대비 편차 | `(hr - baseline.hr_median) / baseline.hr_mad`, 4-시그마에서 포화 |
| HRV_suppression | 0.10 | RMSSD 기준선 대비 저하율 | `(baseline_hrv - hrv) / baseline_hrv`, 0~1 |
| SkinTemp_slope | 0.20 | 피부온도 상승률(°C/min) | 0.3°C/min에서 포화 |
| EDA_delta | 0.10 | 개인 기준 EDA 변화 | 호출측이 이미 0~1 델타로 정규화해 전달 |
| ActivityLoad | 0.15 | IMU 기반 활동 강도 | 0~1 그대로 사용(운동 자체가 발열원이라는 전제) |
| EnvHeatProxy | 0.20 | 환경 상대열부하 | `heatsentry/simulator/env_node.py`가 생성, WBGT_ref와는 별도 지표 |

포화 상수(4-시그마, 0.3°C/min 등)는 PDD 원문에 정확한 숫자가 없어 통합팀이 정할 자리다.
`heatsentry/algorithm/risk_engine.py` 상단에 "설계 기본값" 주석으로 표시해 뒀고, 실측 데이터가 쌓이면
`risk_config_version`을 올리면서 바꾸면 된다.

## 현재 ESP32 하드웨어 프로파일

현재 35바이트 LoRa 패킷에는 HRV와 IMU 활동량이 없다. `heatsentry/algorithm/hardware_adapter.py`는
그 사실을 명시적으로 반영해 아래 네 특징만 계산한다.

| 실물 입력 | RiskIndex 특징 | 계산 방식 |
| --- | --- | --- |
| BPM + Finger | HR_dev | 개인 기준 심박 대비 편차 |
| 피부온도 연속값 | SkinTemp_slope | 최근 60초 상승률 |
| GSR Diff | EDA_delta | 장갑 보정값 대비 양의 변화량 |
| DHT11 온도·습도 | EnvHeatProxy | 상대 열부하(비-WBGT) |

HRV와 `ActivityLoad`는 0점으로 취급하지 않고 품질 게이트에서 제외한다. DHT11까지
정상이면 유효 가중치는 `0.25 + 0.20 + 0.10 + 0.20 = 0.75`이며, DHT11이 없으면
0.55가 되어 `SENSOR_LIMITED`가 된다. GPS 속도나 IR 원시값으로 활동량을 억지로
추정하지 않는다. GPS Fix가 없거나 손가락 미착용인 현재 사진 같은 경우에는
`SENSOR_CHECK`로 처리하며 RiskIndex를 계산하지 않는다.

## PPT 설명용 계산 예시

현재 ESP32 하드웨어 프로파일의 발표용 식은 다음과 같다. 분모 0.75는 실제로 받을 수 없는
HRV(0.10)와 IMU 활동량(0.15)을 제외한 가중치 합이다.

```text
RiskIndex = 100 × (0.25×H + 0.20×T + 0.10×G + 0.20×E) / 0.75

H: 심박 편차         = clamp((BPM - 개인 기준 BPM) / (4 × BPM MAD), 0, 1)
T: 피부온도 상승률   = clamp(피부온도 상승률(°C/min) / 0.30, 0, 1)
G: GSR 변화          = clamp(GSR Diff / 300, 0, 1)
E: 환경 열부하       = clamp((기온 - 20)/20 + (습도 - 40)/200, 0, 1)
```

아래 표는 개인 기준 BPM 80, BPM MAD 5, GSR Diff 기준값 0을 가정한 설명용 예시다.
상태 전이는 점수뿐 아니라 해당 점수가 일정 시간 유지되는지도 함께 확인한다.

| 상황 | BPM | 피부온도 상승률 | GSR Diff | 기온/습도 | H / T / G / E | RiskIndex | 설명 |
| --- | ---: | ---: | ---: | --- | --- | ---: | --- |
| 정상 | 82 | 0.03°C/min | +15 | 26°C / 55% | 0.10 / 0.10 / 0.05 / 0.38 | 17 | 정상 범위 |
| 경고 | 100 | 0.12°C/min | +90 | 31°C / 70% | 1.00 / 0.40 / 0.30 / 0.70 | 67 | 10초 이상이면 WARNING |
| 냉각 C1 | 110 | 0.21°C/min | +180 | 34°C / 80% | 1.00 / 0.70 / 0.60 / 0.90 | 84 | 10초 이상이면 팬 50% 권고 |

예를 들어 냉각 C1 행은 `100 × (0.25×1.00 + 0.20×0.70 + 0.10×0.60 +
0.20×0.90) / 0.75 = 84`로 계산한다. 이 값은 의료 진단값이 아니라 현장 경보와
냉각 우선순위를 정하기 위한 상대 위험도다.

## 품질 게이트와 오류코드

| 오류코드 | 조건 | 제외되는 특징 |
| --- | --- | --- |
| E101 | PPG Quality<70 | HR_dev, HRV_suppression (둘 다 PPG 파생값) |
| E102 | EDA 접촉 손실(Quality<40) | EDA_delta |
| E103 | 피부온도 갱신 지연>3초 | SkinTemp_slope |
| E104 | IMU 응답 없음 | ActivityLoad(+ 낙상 검출 비활성) |
| E105 | 환경 온습도 데이터 없음/저품질 | EnvHeatProxy |

전체 오류코드 표와 로컬/관제 동작은 [api_contract.md](api_contract.md),
구현은 `heatsentry/common/errors.py`.

## 기준선(Baseline)

- 착용 후 3~5분, PPG Quality≥70 & EDA Quality≥40인 구간만 사용.
- 중앙값(median)과 MAD(Median Absolute Deviation)로 이상치를 배제한다(`heatsentry/algorithm/baseline.py`).
- 5분 안에 기준선이 만들어지지 않으면 제한 모드로 전환하고 재착용을 요청한다
  (`heatsentry/simulator/wrist_node.py`의 `BASELINE_FAILED` 이벤트).

## 상태기계와의 연결

RiskIndex는 그 자체로 상태를 정하지 않는다. `heatsentry/algorithm/fsm.py`의 `HeatSentryFsm`이 RiskIndex를
입력으로 받아 히스테리시스·유지시간을 적용해 BASELINE/NORMAL/WARNING/COOLING(C1~C3)/EMERGENCY(C4)
를 결정한다. 임계값 표와 근거는 [architecture.md](architecture.md)의 "상태기계" 절 참고.

## 재현성 (test_vector)

ICD 표1의 `test_vector: TV-20260808-A` 원칙("결과 재현 시 고정")에 따라, `heatsentry/simulator/scenarios.py`의
모든 시나리오는 **난수를 쓰지 않는다.** 같은 입력은 항상 같은 RiskIndex 궤적을 만든다 —
`tests/test_scenarios_integration.py`가 이 재현성 자체를 회귀 테스트로 고정해 둔다.

## 다음 단계(P2, 실험 데이터 확보 후)

1. `RiskEngine.evaluate()`가 반환하는 `contributions`(설명 가능한 기여도)를 라벨로 삼아 로지스틱
   회귀/경량 결정트리로 교체.
2. IMU 원시 시계열 기반 활동 분류(1D CNN 등)는 낙상/활동 분류에만 우선 적용하고, 온열 위험도
   판정 자체는 여전히 설명 가능한 모델을 유지 — PDD 최종 판단: "경쟁력은 센서 수가 아니라
   표준과 한계를 구분하고 실패 안전성을 증명하는 데서 나온다."
