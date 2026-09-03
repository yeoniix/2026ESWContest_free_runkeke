# HeatSentry TAC

**군 집단훈련 온열위험 대응 시스템** — 감지 · 자가 개입 · 관제 전파를 한 장비에서 완결하는
현장 안전 웨어러블 시스템

> 제24회 임베디드SW경진대회 자유공모 출품작 · 팀 **런크크(RUNKEKE)**
> 개발기간 2026.07.01 ~ 2026.09.03

```
센서 취득 → RiskIndex → 상태 판정(FSM) → 자동 냉각 → 재평가 → (미회복 시 상향) → SOS → 감사 로그
```

HeatSentry는 손목 웨어러블의 생체신호, 허리의 능동 냉각, 로컬 게이트웨이, 관제 대시보드를
하나의 폐루프로 묶는다. 위험도가 임계를 넘으면 **누구의 지시도 기다리지 않고** 벨트가 팬을
돌리고 장갑 OLED·진동으로 착용자에게 알리며, 같은 판정 결과가 LoRa로 관제까지 전파된다.

> [!IMPORTANT]
> **RiskIndex와 피부온도는 의료 진단값이 아니다.** 현장 경보와 냉각 우선순위를 정하기 위한
> 상대 위험도이며, 열사병 의심 증상·의식 변화·무응답이 있으면 장치 점수와 무관하게 현장
> 응급절차가 항상 우선한다.

---

<img width="983" height="555" alt="스크린샷 2026-09-03 오전 10 31 55" src="https://github.com/user-attachments/assets/69db7e74-5f36-4991-b68d-4bbad2a9d78c" />

<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 32 06" src="https://github.com/user-attachments/assets/ee003f0e-3d13-4308-b3c3-0d4c14ddf959" />

<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 32 22" src="https://github.com/user-attachments/assets/d192c3e1-d98c-4b28-8cc9-049e3b064236" />

<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 32 43" src="https://github.com/user-attachments/assets/ddf5a395-e786-4732-b4ac-ff307a8ced62" />

<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 33 26" src="https://github.com/user-attachments/assets/9216c7f3-fcca-48e3-8515-9d9b1d4d55dc" />

<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 33 35" src="https://github.com/user-attachments/assets/eaedb501-5257-4eaa-8bbc-6bab268f8ea3" />

<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 33 56" src="https://github.com/user-attachments/assets/6fca27c2-93c7-40cf-97a4-0726ae635e19" />

<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 34 07" src="https://github.com/user-attachments/assets/73ce7a04-5c3f-454c-8a8d-049905a632e3" />

<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 34 17" src="https://github.com/user-attachments/assets/a3638500-6458-410b-843c-3d8d8995f942" />

<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 34 25" src="https://github.com/user-attachments/assets/be346c44-3c95-40f4-a202-f1d5ab6b852a" />

<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 34 34" src="https://github.com/user-attachments/assets/439b6b4e-e873-4f17-ba5f-6f9ed4d77ddc" />

<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 34 41" src="https://github.com/user-attachments/assets/f18356e6-6c05-47cb-8ddb-da7ffc453e1e" />

<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 34 51" src="https://github.com/user-attachments/assets/2b73cdff-757b-495f-a2eb-54dda439ec21" />

<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 35 01" src="https://github.com/user-attachments/assets/e4877590-0aed-45e3-8224-92dea6887125" />

<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 35 11" src="https://github.com/user-attachments/assets/b420307e-2855-4f5a-bcae-dca604447aad" />


<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 35 21" src="https://github.com/user-attachments/assets/63e9bad5-003f-426c-a14d-eef1e601dcff" />

<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 35 31" src="https://github.com/user-attachments/assets/1fbb2788-748c-42f9-8217-365c3a3ae6d8" />

<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 35 39" src="https://github.com/user-attachments/assets/4e69158d-0a01-42c6-8479-c29d423be8c9" />


<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 35 48" src="https://github.com/user-attachments/assets/9d6f8aaa-ac85-4de2-a2d3-2fef5d56542a" />

<img width="983" height="551" alt="스크린샷 2026-09-03 오전 10 35 59" src="https://github.com/user-attachments/assets/a0283eec-992d-4346-ae7c-a4c81dfdc5e5" />

## 목차

1. [왜 만들었나](#왜-만들었나)
2. [시스템 구성](#시스템-구성)
3. [저장소 구조](#저장소-구조)
4. [빠르게 돌려보기](#빠르게-돌려보기)
5. [실물 하드웨어 연동](#실물-하드웨어-연동)
6. [RiskIndex 계산](#riskindex-계산)
7. [상태 판정(FSM)](#상태-판정fsm)
8. [게이트웨이 API](#게이트웨이-api)
9. [데이터 무결성과 감사 로그](#데이터-무결성과-감사-로그)
10. [보안·운영 설정](#보안운영-설정)
11. [시험](#시험)
12. [안전 경계와 적용 범위](#안전-경계와-적용-범위)
13. [알려진 차이와 남은 작업](#알려진-차이와-남은-작업)
14. [문서 · 팀](#문서--팀)

---

## 왜 만들었나

2024년 5월 육군 12사단 훈련병 사망 사고에서, 우리 팀은 집단훈련 온열 질환 사고를 세 가지
문제로 정의했다.

| 문제 | 이 저장소의 대응 |
| --- | --- |
| **주관적 오판** — 개인의 위험 신호가 "꾀병"으로 묵살될 여지 | 센서값과 RiskIndex를 위·변조 탐지 가능한 해시체인 로그로 관제에 전송해, 주관이 아닌 수치로 판단하게 한다 |
| **자가진단 실패** — 열 스트레스는 당사자가 스스로 인지하기 어렵다 | 장갑 손등 OLED에 상태를 상시 표시하고, 임계 초과 시 진동 모터가 즉시 작동한다 |
| **초기 개입 수단 부재** — 이상을 감지해도 즉시 취할 물리적 수단이 없다 | 지휘관 개입 이전에 허리 장착형 냉각 팬을 자동 구동한다 |

개인의 통제 아래 놓인 기존 웨어러블과 달리, **집단 통제가 필요한 특수 환경**에서 쓸 수 있는
반응형 경보 시스템을 목표로 했다.

### 기존 개인용 웨어러블과의 차이

| 비교 항목 | 일반적인 개인 경고형 웨어러블 | HeatSentry |
| --- | --- | --- |
| 위험 대응 | 알림 제공 후 종료 | OLED·진동 경고 → 팬 1개 → 팬 2개 → 관제 전파 |
| 통신 두절 | 서버 연결이 끊기면 관제·대응 제한 | 벨트가 로컬에서 계속 판정하고 팬을 독립 제어 |
| 판정 구조 | 서버 판정에 의존 | 벨트가 단독 판정자 — 게이트웨이는 재계산하지 않고 전달만 하며, 해석 불가 값은 오류로 남긴다 |
| 센서 고장 | 누락값으로 위험을 과소평가 | 고장 센서 제외 + 가중치 재정규화 + `SENSOR_LIMITED` 별도 표시 |
| 통신 효율 | Wi-Fi·서버 연결 중심 | 35바이트 LoRa 패킷으로 생체·상태·GPS 원거리 전송 |
| 사후 기록 | 수정 가능한 일반 로그 | SHA-256 해시체인으로 최초 변경 지점 탐지 |

---

## 시스템 구성

```
 ┌──────────────────┐  ESP-NOW   ┌──────────────────┐   LoRa    ┌──────────────┐  HTTP  ┌───────────┐
 │   손목 노드       │ ─ 28B/1s ─▶│    벨트 노드      │─ 35B/2s ─▶│ LoRa 수신기   │───────▶│ 게이트웨이 │
 │  ESP32 Dev       │◀─ 12B/0.5s │  Heltec ESP32-S3 │  922.3MHz └──────────────┘        │ FastAPI   │
 │                  │            │                  │                                   └─────┬─────┘
 │ MAX30102  심박    │            │ 로컬 FSM 판정     │                                    WS /ws/live
 │ TMP117    피부온도 │            │ ATGM336H GPS     │                                    REST /api/v2
 │ GSR       피부전도 │            │ 비상 버튼         │                                         │
 │ SSD1306   OLED   │            │ 팬 ×2 (PWM)      │                                   ┌─────▼─────┐
 │ 진동 모터         │            │ LoRa 송신         │                                   │  대시보드  │
 └──────────────────┘            └──────────────────┘                                   │ React+Vite│
                                                                                        └───────────┘
   판정하지 않는다.                실물 경로의 단독 판정자.            위험도를 다시 계산하지        현장 팬을 제어할 수 없고
   벨트가 회신한 상태를             LoRa가 끊겨도 팬과 OLED를          않고 저장·전파만 한다.       응급도 해제할 수 없다.
   띄우고 경고 시 진동.             혼자 계속 구동한다.                                           확인 기록만 남긴다.
```

### 통신 규격

| 링크 | 내용 | 주기 | 정의 위치 |
| --- | --- | --- | --- |
| ESP-NOW 손목→벨트 | `SensorPacket` 28B (bpm, temp, gsr, gsrDiff, ir, finger, seq) | 1초 | [firmware/glove_esp32/glove_esp32.ino](firmware/glove_esp32/glove_esp32.ino) |
| ESP-NOW 벨트→손목 | `DisplayPacket` 12B (state, cause, fanPercent, bpm, skinTemp, flags) | 0.5초 | [firmware/glove_esp32/display_protocol.h](firmware/glove_esp32/display_protocol.h) |
| LoRa 벨트→수신기 | `TelemetryPacket` 35B · SF7 · BW 125kHz · CR 4/5 · 922.3MHz. 생체값 + GPS + 벨트 판정(state·cause·냉각단계·위험도) | GPS fix 시 단축 | [firmware/lora_get/esplora_get.ino](firmware/lora_get/esplora_get.ino) · [glove_packets.py](heatsentry/common/glove_packets.py) |
| HTTP 브리지→게이트웨이 | `POST /ingest/telemetry` (TelemetryV2 JSON) | 패킷마다 | [heatsentry/common/schema.py](heatsentry/common/schema.py) |
| WebSocket 게이트웨이→UI | `/ws/live` — `snapshot` / `telemetry` / `event` / `command_ack` | ≤1초 | [heatsentry/server/ws.py](heatsentry/server/ws.py) |

35바이트 안에 벨트의 판정까지 담기 위해, DHT 제거로 비게 된 두 16비트 자리를 재활용한다.

```
state_cause_word = (DeviceState << 8) | CauseCode
stage_risk_word  = (CoolingStage << 8) | RiskIndex
```

패킷 크기는 펌웨어의 `static_assert`와 파이썬 디코더가 서로 검증하며,
[tests/test_display_protocol_sync.py](tests/test_display_protocol_sync.py)가 장갑·벨트 두
헤더 파일과 파이썬 enum의 코드 정의가 어긋나지 않는지 확인한다.

> [!WARNING]
> 현재 `firmware/belt_heltec/belt_heltec.ino`에 **벨트 펌웨어가 없다** — 장갑 스케치로
> 덮어써진 상태다. LoRa 송신 주기·송신 출력 등 벨트 측 수치는 저장소에서 확인할 수 없다.
> [알려진 차이](#알려진-차이와-남은-작업) 참고.

### 서브시스템 책임

| 서브시스템 | 책임 | 코드 |
| --- | --- | --- |
| SU-W 손목 노드 | 센서 취득·품질 검사, OLED 표시, 진동 | `firmware/glove_esp32/`, `heatsentry/simulator/wrist_node.py` |
| SU-B 허리 노드 | 로컬 위험 판정, 팬 PWM 제어, GPS, 비상 버튼, LoRa 송신 | `firmware/belt_heltec/`, `heatsentry/simulator/belt_node.py` |
| SU-E 환경 노드 | EnvHeatProxy (WBGT와는 별개 지표, 시뮬레이터 전용) | `heatsentry/simulator/env_node.py` |
| SU-G 게이트웨이 | 패킷 디코딩·저장·해시체인·역할 분리·WebSocket 전파 (재판정하지 않음) | `heatsentry/server/` |
| SU-D 대시보드 | 상태 카드, 위험도 추이, GPS 지도, 이벤트·확인 기록 | `dashboard/` |

---

## 저장소 구조

파이썬 코드는 전부 `heatsentry/` 패키지 하나에 있고, 그 바깥에는 파이썬이 아닌 것만 둔다 —
임베디드 펌웨어, 웹 대시보드, 문서, 시험.

```
heatsentry/          파이썬 패키지 (pip install -e . 로 설치 가능)
├─ common/           패킷 정의·해시체인·CRC16·오류코드·게이트웨이 스키마
│  ├─ packets.py         HS_STATUS / COOL_CMD / COOL_ACK 바이너리 레이아웃, DeviceState
│  ├─ glove_packets.py   실물 35B TelemetryPacket 디코더, 벨트 상태·원인 코드
│  ├─ schema.py          TelemetryV2 (게이트웨이 ↔ 대시보드 JSON 계약)
│  └─ hash_chain.py      SHA-256 이벤트 해시체인
├─ algorithm/        위험도 판정
│  ├─ risk_config.py     가중치·임계값·냉각 단계 표 (형상관리 대상 숫자 전부)
│  ├─ risk_engine.py     RiskIndex v0.3 계산 + 품질 게이트
│  ├─ baseline.py        개인 기준선(3~5분) 생성
│  ├─ fsm.py             C0~C4 냉각 단계 · DeviceState · 명령 중재
│  ├─ hardware_adapter.py 실물 3특징 프로필용 어댑터
│  └─ display_status.py  OLED 2줄 문구 생성
├─ simulator/        결정적 노드 시뮬레이터 (실물 펌웨어의 레퍼런스 구현)
│  └─ run_demo.py        T01~T08·T10 시나리오 러너
└─ server/           게이트웨이 (FastAPI)
   ├─ main.py            앱 조립 · CORS · /ws/live
   ├─ routes_ingest.py   /ingest/* (장치 키 인증 · 시퀀스 중복 제거)
   ├─ routes_api_v2.py   /api/v2/* (역할 기반 확인·해제·내보내기·설정)
   ├─ lora_adapter.py    35B 패킷 → TelemetryV2 변환 (벨트 판정을 그대로 전달)
   ├─ state.py / db.py   메모리 상태 + SQLite 저장 + 해시체인
   └─ ws.py              WebSocket 브로드캐스트

firmware/            임베디드 C/C++
├─ glove_esp32/      장갑 ESP32 스케치 + OLED 표시 프로토콜 헤더
├─ belt_heltec/      벨트 Heltec LoRa 스케치 (로컬 판정 · 팬 제어) + 표시 프로토콜 헤더
└─ lora_get/         LoRa 수신기 스케치 (35B를 시리얼로 넘긴다)

dashboard/           React + TypeScript + Vite 관제 대시보드
docs/hardware/       실물 배선 · 핀맵 · 조립 · 브리지 연동 가이드, CAD 소스
tests/               pytest 80건
pyproject.toml       패키지 경계와 pytest 설정
requirements.txt     고정 의존성
```

임계값·가중치 같은 형상관리 대상 숫자는 [heatsentry/algorithm/risk_config.py](heatsentry/algorithm/risk_config.py)
한 파일에 모여 있다. FSM은 이 파일의 표만 읽으므로, 냉각 단계 기준을 바꿀 때 `fsm.py`는
건드리지 않는다.

---

## 빠르게 돌려보기

하드웨어 없이 시뮬레이터만으로 감지 → 냉각 → 관제 전파 폐루프 전체를 재현할 수 있다.
터미널 3개가 필요하다.

### 1) 게이트웨이 (FastAPI)

```bash
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn heatsentry.server.main:app --reload --port 8000
```

`http://127.0.0.1:8000/docs`에서 OpenAPI 문서를 확인할 수 있다.

### 2) 노드 시뮬레이터

```bash
# 새 터미널, 같은 가상환경
python -m heatsentry.simulator.run_demo --scenario T03 --fast
```

| 옵션 | 기본값 | 설명 |
| --- | --- | --- |
| `--scenario` | `T03` | `T01`~`T08`, `T10` 중 하나 (정의는 [scenarios.py](heatsentry/simulator/scenarios.py)) |
| `--gateway-url` | `http://127.0.0.1:8000` | 게이트웨이 주소 |
| `--device-id` | `HS-W-001` | 장치 ID |
| `--fast` | off | 3~5분 걸리는 기준선 측정을 6~9초로 단축 (**개발용**, 실제 시연에는 쓰지 않는다) |
| `--sleep` | `1.0` | tick 사이 실제 대기 시간(초). `0`이면 최대 속도 |
| `--dt` | `1.0` | tick 하나가 나타내는 시뮬레이션 시간(초) |
| `--cycles` | `3` | T10 통합 시나리오 반복 횟수 |

주요 시나리오:

| ID | 검증 내용 |
| --- | --- |
| T01 | 기준선 안정 → NORMAL 유지 |
| T02 | PPG/EDA 동시 품질 저하 → `valid_weight < 0.60` → `SENSOR_LIMITED` |
| T03 | RiskIndex ≥ 80이 10초 지속 → 냉각 C1 진입 (CTL-001) |
| T04 | 냉각 명령 ACK 손실 → 재전송 |
| T05 | 팬 과전류 → 팬 OFF (E301) |
| T06 | 90→70 회복 → 30초 후 단계 하향 |
| T07 | C2가 60초 이상 미회복 → C3, 지휘관 확인 후에만 하향 |
| T08 | 낙상+무동작+무응답 → HardTrigger → 즉시 EMERGENCY |
| T10 | 폐루프 통합 반복 + 로그 변조 시 해시체인 불일치 검출 |

### 3) 대시보드 (React + Vite)

```bash
cd dashboard
npm install
npm run dev
```

`http://localhost:5173`에서 실시간 장치 카드, RiskIndex 추이, 냉각 상태, GPS 지도,
이벤트 로그(해시체인), 확인/응급 해제 콘솔을 볼 수 있다. 우측 상단 역할 선택기로
`observer` / `commander` / `tester` / `maintainer`를 바꿔가며 권한 분리를 확인한다(HMI-001).

선택 설정 — `dashboard/.env.local`:

```bash
VITE_GATEWAY_URL=http://127.0.0.1:8000   # 기본값
VITE_KAKAO_MAP_APP_KEY=<카카오맵 JS 키>   # 없으면 지도 대신 안내 문구 표시
```

---

## 실물 하드웨어 연동

### 부품

| 노드 | 부품 | 역할 |
| --- | --- | --- |
| 손목 | ESP32 Dev Module | 메인 MCU |
| | MAX30102 | PPG · 심박 |
| | TMP117 | 피부 온도 |
| | GSR Sensor | 피부 전도 |
| | SSD1306 OLED 128×64 | 상태 표시 |
| | 진동 모터 | 경고 |
| 벨트 | Heltec ESP32-S3 (LoRa 915) | 로컬 판정 · LoRa 송신 |
| | ATGM336H | GPS 측위 |
| | 12mm 버튼 | 비상 입력 |
| | 40×40mm Fan ×2 | 능동 냉각 (PWM 5kHz · 8bit) |

기구부는 Fusion 360으로 설계해 3D 프린팅했다 — 듀얼 팬 모듈, 유도판, 상부 덕트, 팬 교체가
가능한 분리형 하우징. CAD 파라메트릭 소스는 [docs/hardware/cad/](docs/hardware/cad/)에 있다.

### 펌웨어 빌드

Arduino IDE 2.x + ESP32 Arduino Core로 세 스케치를 각각 업로드한다.

| 스케치 | 보드 |
| --- | --- |
| [firmware/glove_esp32/glove_esp32.ino](firmware/glove_esp32/glove_esp32.ino) | ESP32 Dev Module |
| [firmware/belt_heltec/belt_heltec.ino](firmware/belt_heltec/belt_heltec.ino) | Heltec WiFi LoRa 32 (V3) — **현재 소스 유실 상태** |
| [firmware/lora_get/esplora_get.ino](firmware/lora_get/esplora_get.ino) | Heltec WiFi LoRa 32 (V3) |

벨트와 수신기의 LoRa 파라미터(922.3MHz · SF7 · BW 125kHz · CR 4/5)는 **반드시 동일해야**
한다. 자세한 배선·핀맵·조립 순서는 [docs/hardware/hardware_integration_kr.md](docs/hardware/hardware_integration_kr.md).

### 수신기 → 게이트웨이 브리지

LoRa 수신기 스케치는 35바이트를 검증한 뒤 시리얼로 넘긴다. 파이썬 쪽에는 이를 관제
텔레메트리로 바꾸는 어댑터가 준비돼 있다.

```python
import requests
from heatsentry.server.lora_adapter import LoRaTelemetryAdapter

adapter = LoRaTelemetryAdapter()

def handle_packet(payload: bytes, rssi: int, snr: int) -> None:
    telemetry = adapter.convert(payload, rssi_dbm=rssi, snr_db=snr)
    requests.post("http://127.0.0.1:8000/ingest/telemetry",
                  json=telemetry.model_dump(), timeout=3).raise_for_status()
```

> [!NOTE]
> **USB 시리얼을 읽어 위 함수를 호출하는 상주 프로세스는 아직 저장소에 없다.** 디코더·어댑터·
> 게이트웨이 수신단은 모두 구현·시험되어 있고, 남은 것은 시리얼 루프 하나다. 권장 시리얼 한 줄
> 형식과 전체 예제는 [docs/hardware/hardware_integration_kr.md](docs/hardware/hardware_integration_kr.md) 12장에 있다.

---

## RiskIndex 계산

RiskIndex v0.3 엔진은 **시뮬레이터 경로(손목 노드)** 가 쓴다. 실물 경로에서는 벨트가 자체
위험점수를 계산해 패킷에 실어 보내므로 게이트웨이가 이 엔진을 다시 돌리지 않는다
([판정 주체](#판정-주체--경로에-따라-다르다) 참고).

세 개 이상의 생체·환경 특징을 각각 0~1로 정규화해 가중 평균한다. 핵심은 **분모가 상수가
아니라 "지금 살아있는 가중치의 합"**이라는 점이다. 센서 하나가 죽어도 0으로 희석되지 않고,
남은 센서끼리 다시 정규화한다.

```
RiskIndex = 100 × Σ(wᵢ · qᵢ · featureᵢ) / Σ(wᵢ · qᵢ)

  w       가중치
  q       센서 품질 (0~1, 게이트 미달이면 0)
  feature 0~1로 정규화(clamp)한 특징

valid_weight = Σ(wᵢ · qᵢ)
  < 0.60 → SENSOR_LIMITED 플래그
  = 0    → 판정 불가 (risk_index = 255)
```

### 가중치 — 두 개의 프로필

`risk_config.py`는 설계 기준과 실물 하드웨어, 두 벌의 가중치를 갖는다.

| 특징 | 정규화 | `DEFAULT_CONFIG`<br>(설계 · 시뮬레이터) | `HARDWARE_CONFIG`<br>(실물 3특징) |
| --- | --- | --- | --- |
| `HR_dev` 심박 편차 | (BPM − 기준선) / MAD ÷ 4 | 0.25 | **0.45** |
| `SkinTemp_slope` 온도 상승률 | (°C/분) ÷ 0.3 | 0.20 | **0.37** |
| `EDA_delta` 발한 변화 | GSR 변화량 ÷ 300 | 0.10 | **0.18** |
| `HRV_suppression` | RMSSD 억제 | 0.10 | 0 — 패킷에 RMSSD 없음 |
| `ActivityLoad` | IMU 활동량 | 0.15 | 0 — IMU 미탑재 |
| `EnvHeatProxy` | 환경 열부하 | 0.20 | 0 — DHT 센서 제거 |

실물 패킷에는 6특징 중 3개가 오지 않는다(DHT는 하드웨어에서 제거됐고, 그 자리는 벨트 판정
전송에 재활용된다). 설계 가중치를 그대로 쓰면 살아있는 가중치 합이
0.55로 `min_valid_weight`(0.60)에 항상 미달해 실물 장비가 무조건 `SENSOR_LIMITED`로 보고되는
문제가 있었다. 그래서 남은 3특징에 가중치를 비례 재분배해 합이 1.00이 되게 했다. RiskIndex는
어차피 `valid_weight`로 나눠 재정규화하므로 **점수 자체는 달라지지 않고**, `valid_weight`의
의미만 달라진다 — 이제 0.60 미달은 "설계상 없는 센서" 때문이 아니라 손가락 이탈·온도 정지 같은
**실제 품질 저하**일 때만 발생한다.

### 품질 게이트

| 코드 | 조건 | 제외되는 특징 |
| --- | --- | --- |
| `E101` | PPG 품질 < 70 | `HR_dev`, `HRV_suppression` |
| `E102` | EDA 접촉 손실 (품질 < 40) | `EDA_delta` |
| `E103` | 피부온도 3초 이상 갱신 없음 | `SkinTemp_slope` |
| `E105` | 환경 센서 품질 < 50 | `EnvHeatProxy` |

게이트를 통과하면 `q = 품질/100`으로 비례 반영하고, 미달하면 `q = 0`으로 계산에서 제외한 뒤
오류코드를 `active_errors`에 남긴다. 개인 기준선은 유효 착용 3~5분 구간에서 생성하며, 기준선이
없으면 RiskIndex를 계산하지 않고 `BASELINE` 상태로 보고한다.

---

## 상태 판정(FSM)

상태 코드는 펌웨어·게이트웨이·대시보드가 **하나의 정의를 공유한다.** 벨트가 보낸 값을
관제가 다른 뜻으로 읽는 일이 없도록, `firmware/*/display_protocol.h`의 enum과
`heatsentry/common/glove_packets.py`의 파이썬 enum이 이름·값 모두 같아야 하며
[tests/test_display_protocol_sync.py](tests/test_display_protocol_sync.py)가 이를 검사한다.

### DeviceState — 지금 어떤 상황인가

| 값 | 상태 | 조건 |
| --- | --- | --- |
| 0 | `BOOT` | 부팅 |
| 1 | `BASELINE` | 기준선 미완성 → RiskIndex 미계산 |
| 2 | `NORMAL` | C0이면서 경고 없음 |
| 3 | `CAUTION` | 경고 활성 (진입 60 · 10초 / 해제 55 · 30초) |
| 4 | `COOLING` | 냉각 단계가 C1 이상 |
| 5 | `EMERGENCY` | 비상 래치 걸림 |
| 6 | `SENSOR_CHECK` | 손가락 미착용 · BPM 0 · 데이터 무효 |

### 냉각 단계 — 팬을 얼마나 트는가

상태와 별개로 `CoolingStageCode`(C0~C4)가 함께 전송된다. 정의는
[risk_config.py](heatsentry/algorithm/risk_config.py)의 `CoolingStageConfig` 표 하나뿐이다.

| 단계 | 진입 조건 | 해제 조건 | 팬 |
| --- | --- | --- | --- |
| C0 | 최하단 | — | 0% |
| C1 | risk ≥ 80 · 10초 | risk < 70 · 30초 | 50% |
| C2 | risk ≥ 90 · 10초 | risk < 80 · 30초 | 100% |
| C3 | risk ≥ 90 · 60초 | risk < 85 · 60초 **+ 지휘관 확인** | 100% |
| C4 | risk ≥ 95 · 즉시 | **자동 해제 없음** | 100% |

C2와 C3가 같은 100%인 것은, 실제 블로워의 저출력 구간이 체감 냉각 효과가 작아 현장 제어를
OFF → 50% → 100% 두 출력 단계로 단순화했기 때문이다. 두 단계의 구분은 출력이 아니라 **위험
지속 시간과 경보 수준**에 있다.

`fsm.py`는 단계 이름조차 코드에 두지 않는다 — 최하단·최상단과 "자동 해제 조건이 없는
비상 단계"를 모두 위 표에서 유도하므로, 냉각 기준을 바꿀 때 고칠 파일은 `risk_config.py`
하나다. [tests/test_fsm.py](tests/test_fsm.py)가 임계값을 바꾼 설정으로 이를 회귀 검증한다.

Fail-safe: 링크 10초 두절 시 저하 모드, 팬 안전 타이머 60초, 명령 ACK 타임아웃 500ms ·
최대 3회 재전송.

### 판정 주체 — 경로에 따라 다르다

| 경로 | 판정 주체 | 게이트웨이의 역할 |
| --- | --- | --- |
| **실물 하드웨어** (LoRa 35B) | **벨트 노드** | 재계산하지 않고 전달만 한다 |
| **시뮬레이터** (HTTP) | 손목 노드 (RiskIndex v0.3 + FSM) | 재계산하지 않고 저장·전파만 한다 |

두 경로 모두 게이트웨이는 **판정을 다시 내리지 않는다.** 특히 실물 경로에서 벨트가 단독
판정자인 이유는, LoRa가 끊겨도 팬과 장갑 OLED가 계속 동작해야 하기 때문이다. 현장에서 실제로
팬을 돌린 근거와 관제 화면의 값이 갈리면 사고 조사에서 어느 쪽도 신뢰할 수 없게 되므로,
`lora_adapter.py`는 벨트가 보낸 `DeviceState` · `CoolingStage` · `RiskIndex` · `Cause`를
그대로 옮긴다.

대신 **값이 해석 불가일 때 조용히 넘어가지 않는다.**

| `active_errors` | 조건 | 처리 |
| --- | --- | --- |
| `STATE_INVALID` | 모르는 상태 코드 | `SENSOR_CHECK`으로 낮춘다 |
| `COOLING_STAGE_INVALID` | 모르는 냉각 단계 | C0으로 낮춘다 |
| `RISK_INVALID` | 위험도가 0~100 범위 밖 | `risk_index = 255`(판정 불가) |
| `SENSOR_CHECK` | 손가락 미착용 · 장갑 데이터 무효 | 그대로 표시 |

### 비상 상태 해제

`hard_trigger`(낙상+무동작 / SOS)로 걸린 래치는 **자동으로 풀리지 않는다.**
`close_emergency()`는 `/api/v2/emergency/{id}/close` 핸들러가 현장 확인자 정보와 함께
명시적으로 호출할 때만 실행되며, 이 엔드포인트는 `commander` 역할을 요구한다. 해제 직후에도
팬을 즉시 끄지 않고 한 단계 아래(C3)를 유지한다.


## 게이트웨이 API

| 메서드 | 경로 | 권한 | 설명 |
| --- | --- | --- | --- |
| `POST` | `/ingest/telemetry` | 장치 키 | 텔레메트리 수신 (시퀀스 증가분만 반영) |
| `POST` | `/ingest/event` | 장치 키 | 장치 이벤트 → 해시체인 기록 |
| `POST` | `/ingest/command_ack` | 장치 키 | 냉각 명령 ACK |
| `GET` | `/api/v2/devices` | 전체 | 장치별 최신 상태 |
| `GET` | `/api/v2/events` | 전체 | 이벤트 로그 (해시 포함) |
| `GET` | `/api/v2/alerts` | 전체 | 경보 목록 |
| `GET` | `/api/v2/emergency` | 전체 | 응급 목록 |
| `POST` | `/api/v2/alerts/{id}/ack` | `commander` | 알림 확인 |
| `POST` | `/api/v2/emergency/{id}/close` | `commander` | 응급 해제 (현장 확인자 기록 필수) |
| `POST` | `/api/v2/export` | `tester` | 이벤트 CSV/JSON 내보내기 |
| `PUT` | `/api/v2/config` | `maintainer` | 설정 변경 (HMAC-SHA256 서명 검증) |
| `WS` | `/ws/live` | observer 수준 | `snapshot` → `telemetry`/`event`/`command_ack` 스트림 |

역할은 `X-HS-Role`, 행위자는 `X-HS-Actor`, 장치 키는 `X-HS-Device-Key` 헤더로 전달한다.

> [!WARNING]
> `heatsentry/server/auth.py`의 역할 검사는 **프로덕션 인증이 아니다.** 대회 MVP 단계에서
> "권한이 분리되어 있어야 한다"는 구조를 먼저 세워둔 헤더 기반 placeholder이며, 실사용 전에는
> 서명된 토큰으로 교체해야 한다. `/api/v2/config` PUT만은 요구사항상 HMAC 서명 검증을 최소
> 구현해 두었다.

---

## 데이터 무결성과 감사 로그

모든 경보·명령·ACK·확인 기록은 SQLite에 저장되면서 해시체인으로 묶인다.

```
event_hash = SHA256( previous_hash || canonical_json(event_without_hash) )
canonical_json: UTF-8 · sorted keys · no whitespace · 소수점 6자리 고정
genesis previous_hash = "0" * 64
```

체인 중간의 한 건이라도 수정되면 그 지점부터 해시가 어긋나므로 **최초 변경 지점을 특정할 수
있다.** T10 시나리오가 실제로 로그를 변조해 불일치 검출을 확인한다. `/api/v2/export`로
`seq`, `gateway_utc`, `event_hash`, `previous_hash`를 포함한 CSV/JSON을 내보내 외부에서 재검증할
수 있고, 내보내기 행위 자체도 감사 기록에 남는다.

기본 DB 경로는 `heatsentry/heatsentry_gateway.db`이며 `HEATSENTRY_DB_PATH`로 바꿀 수 있다.
보존 정책과 스키마는 [db.py](heatsentry/server/db.py), 체인 계산은 [hash_chain.py](heatsentry/common/hash_chain.py)에 있다.

---

## 보안·운영 설정

실장 환경에서는 장치별 비밀키를 반드시 등록한다. **키가 비어 있으면 시뮬레이터 호환을 위한
개발 모드이며 `/ingest/*` 인증이 수행되지 않는다.**

```bash
export HEATSENTRY_DEVICE_KEYS='{"HS-W-001":"change-this-device-secret"}'
export HEATSENTRY_DEVICE_KEY='change-this-device-secret'   # 시뮬레이터 실행 터미널
export HEATSENTRY_CONFIG_SECRET='change-this-config-secret'
export HEATSENTRY_CORS_ORIGINS='http://127.0.0.1:5173'
export HEATSENTRY_DB_PATH='/var/lib/heatsentry/gateway.db'
```

| 환경변수 | 기본값 | 용도 |
| --- | --- | --- |
| `HEATSENTRY_DEVICE_KEYS` | `{}` (인증 없음) | 장치 ID → 비밀키 JSON 맵 |
| `HEATSENTRY_DEVICE_KEY` | 없음 | 시뮬레이터가 보낼 키 |
| `HEATSENTRY_CONFIG_SECRET` | `dev-only-insecure-secret` | `/api/v2/config` HMAC 키 |
| `HEATSENTRY_CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | 허용 오리진 (쉼표 구분) |
| `HEATSENTRY_DB_PATH` | `heatsentry/heatsentry_gateway.db` | SQLite 경로 |

장치 키가 설정되면 모든 `/ingest/*` 요청은 `X-HS-Device-Key`가 일치해야 한다. 텔레메트리는
장치별 `sequence`가 증가할 때만 반영되므로, 재전송이 현재 상태나 감사 이벤트를 중복으로
덮어쓰지 않는다.

---

## 시험

```bash
# 파이썬 — 80건
pytest -q

# 대시보드 — 타입체크 · 빌드 · 린트
cd dashboard
npm run build
npx eslint .
```

| 파일 | 건수 | 검증 대상 |
| --- | --- | --- |
| `test_fsm.py` | 13 | 냉각 단계 승급·강등, 히스테리시스, 비상 래치, 명령 중재, 임계값 하드코딩 금지 |
| `test_gateway_api.py` | 10 | REST v2, 역할 분리, 장치 키, 시퀀스 중복 제거 |
| `test_hardware_risk_adapter.py` | 8 | 실물 3특징 프로필, 가중치 재정규화 |
| `test_scenarios_integration.py` | 8 | T01~T10 폐루프 통합 |
| `test_lora_adapter.py` | 9 | 35B → TelemetryV2 변환, 벨트 판정 무손실 전달, 해석 불가 값 검출 |
| `test_packets.py` | 7 | HS_STATUS / COOL_CMD / COOL_ACK 바이트 레이아웃 · CRC16 |
| `test_risk_engine.py` | 6 | RiskIndex 공식, 품질 게이트, `valid_weight` |
| `test_glove_packets.py` | 6 | 35B TelemetryPacket 디코딩, 상태·원인·냉각단계·위험도 워드 분해 |
| `test_display_protocol_sync.py` | 5 | 장갑·벨트 헤더와 파이썬 enum의 상태·냉각단계·원인 코드 일치 |
| `test_display_status.py` | 4 | OLED 2줄 문구 결정성 |
| `test_hash_chain.py` | 4 | 정규화 JSON, 체인 연결, 변조 검출 |
| **합계** | **80** | |

---

## 안전 경계와 적용 범위

### 안전 경계

1. **대시보드는 EMERGENCY를 자동 해제할 수 없다.** 관제의 "해제" 버튼은 감사 기록을 남기고
   `commander` 확인 절차를 거치며, 현장의 물리적 확인이 전제된다.
2. **"알림 확인"과 "응급 해제"는 다른 버튼·다른 권한이다.**
3. **자동 냉각이 실패해도 수동 정지와 구조 절차는 항상 유지된다.**
4. **RiskIndex/피부온도는 의료 진단값이 아니다** — 현장 응급절차가 항상 장치 판정보다 우선한다.
5. **관제는 현장 팬을 원격 제어하지 않는다.** 팬 제어 권한은 벨트 노드에만 있다.

### 적용 범위 — 훈련 안전 한정

HeatSentry는 **지정된 훈련장에서 훈련 시간 중에만** 운용하는 훈련 안전 장비다. 실작전·경계
근무 상황에서의 상시 착용과 위치 전송은 설계 단계부터 비적용 범위로 고정했다.

- **RF 노출** — LoRa 상시 송신은 방향 탐지로 역추적될 수 있어, 실전에서는 부대의 위치와 규모를
  스스로 노출하는 수단이 된다. 이미 공개된 고정 구역인 훈련장에서만 쓰면 이 위험이 사라진다.
- **해킹 위험** — 장치 정보가 유출되면 저장된 위치 이력이 함께 넘어간다. 위치 데이터를 훈련
  세션 단위로만 유지하는 이유다.
- **감시 전용 방지** — 위치·생체 데이터는 안전 목적을 벗어나는 순간 감시 도구가 되기에, 구조
  대상자를 찾는 데 필요한 최소 정보로 범위를 좁혔다.

민간 산업 안전(고온 작업장·옥외 건설·소방)으로 확장할 경우, 위치 계층을 옵션으로 분리하고
데이터 보관 기간과 열람 권한을 사업장 안전관리 규정에 맞춰 설정한다. 안전 목적 외 사용을 막는
것이 확장의 전제 조건이다.

---

## 알려진 차이와 남은 작업

투명성을 위해 현재 코드와 설계 문서 사이의 차이를 명시한다.

| 항목 | 현황 |
| --- | --- |
| LoRa 시리얼 브리지 | 디코더·어댑터·수신단은 구현·시험 완료. USB 시리얼을 읽는 상주 프로세스는 미구현 (예제 코드는 HW 가이드 12장) |
| `auth.py` 역할 검사 | 헤더 기반 placeholder. 실사용 전 서명 토큰으로 교체 필요 |
| **벨트 펌웨어 소스 유실** | `firmware/belt_heltec/belt_heltec.ino`가 장갑 스케치로 덮어써져 LoRa·GPS·팬 제어·비상 버튼 코드가 저장소에 없다. 마지막 정상본은 커밋 `b2daff8`이나 옛 상태코드를 써서 현재 헤더로는 빌드되지 않는다 — **복구 필요** |
| `WARNING` → `CAUTION` 진입 임계 60 | 기준 문서에 숫자가 없어 v1.0 값을 이어받은 설계 기본값. 실측 데이터 확보 시 CR로 조정하고 `RISK_CONFIG_VERSION`을 올린다 |
| `EnvHeatProxy` / `HRV` / `ActivityLoad` | 시뮬레이터에만 존재. DHT 제거·RMSSD 미산출·IMU 미탑재로 실물에서는 가중치 0 |
| `HardwareRiskAdapter` | 게이트웨이가 재판정을 그만두면서 실행 경로에서 빠졌다. 시험으로만 유지 중이며, 벨트 없이 원시 센서만 받는 구성으로 되돌릴 때 필요하다 |
| `SU-E` 환경 노드 | `heatsentry/simulator/env_node.py`가 어디서도 import되지 않는다. 설계 문서상 서브시스템이라 남겨 뒀다 |
| `pyserial` 의존성 | 시리얼 브리지 추가를 위해 미리 고정해 둔 것으로 현재 코드에서는 사용하지 않는다 |

### 발전 방향

- **IMU 추가** — 낙상 감지·행동 분류를 정식 기능으로 편입하고 실측 데이터로 임계값 보정
- **냉각 방식 보완** — 팬 구동에 더해 PCM(상변화물질) 모듈을 허리 노드에 추가
- **다중 착용자 확장** — 한 게이트웨이가 다수 노드를 수용하도록 스케줄링·패킷 충돌 제어 확장

### 개발 단계

| 단계 | 목표 | 상태 |
| --- | --- | --- |
| P0 기능증명 | 신호·팬 확인 | 완료 |
| P1 대회 MVP | 8주 폐루프 시연 | 알고리즘·게이트웨이·대시보드·시뮬레이터 폐루프 완성, 실물 3노드 동작 확인. 시리얼 브리지 자동화가 남음 |
| P2 현장 확장 | 다중 인원·장거리 | 범위 밖 |

---

## 문서 · 팀

### 설계 문서

| 문서 | 내용 |
| --- | --- |
| [docs/hardware/hardware_integration_kr.md](docs/hardware/hardware_integration_kr.md) | 실물 배선·핀맵·조립·브리지 연동 가이드 |
| [docs/hardware/cad/](docs/hardware/cad/) | 냉각 하우징 CAD 소스·STL·BOM·출력 체크리스트 |

설계 근거와 수치의 1차 출처는 기준선 문서(`HS-PDD-002`, `HS-SIID-002`)이며, 코드에서
그 근거가 필요한 자리에는 해당 절·표 번호를 주석으로 달아 두었다. 알고리즘·상태 판정·
패킷 규격은 이 README와 아래 코드가 기준이다.

| 대상 | 코드 |
| --- | --- |
| RiskIndex 공식·품질 게이트 | [risk_engine.py](heatsentry/algorithm/risk_engine.py) |
| 가중치·임계값·냉각 단계 표 | [risk_config.py](heatsentry/algorithm/risk_config.py) |
| 상태 판정·명령 중재 | [fsm.py](heatsentry/algorithm/fsm.py) |
| 패킷 바이트 레이아웃 | [packets.py](heatsentry/common/packets.py) · [glove_packets.py](heatsentry/common/glove_packets.py) |
| 게이트웨이 데이터 계약 | [schema.py](heatsentry/common/schema.py) |
| 시험 벡터 T01~T10 | [scenarios.py](heatsentry/simulator/scenarios.py) |

기준선 문서는 `HS-PDD-002`(제품개발 상세설계서)와 `HS-SIID-002`(시스템 통합·인터페이스
명세서) v2.0이다. 인터페이스 정의가 코드와 어긋나면 **인터페이스는 먼저 동결하고 구현을
교체 가능하게 한다**는 원칙을 따른다.

### 개발 환경

| 구분 | 내용 |
| --- | --- |
| Embedded | Arduino IDE 2.x · ESP32 Arduino Core · C/C++ |
| Backend | Python 3.11+ · FastAPI · Uvicorn |
| Frontend | React 19 · TypeScript · Vite |
| Database | SQLite + SHA-256 Hash Chain |
| Communication | ESP-NOW · LoRa · UART · I2C · HTTP/REST · WebSocket |
| Design / CAD | Autodesk Fusion 360 |

### 업무 분담 — 팀 런크크(RUNKEKE)

| 팀원 | 담당 |
| --- | --- |
| **박주영** (전자공학과) | 장갑 센서 회로 설계·배선, ESP32 펌웨어 구현, 생체·환경 센서 측정 및 보정, 시뮬레이터 및 단위·통합·현장시험 |
| **이영재** (전자공학과) | Heltec 기반 벨트 노드 회로 설계, GPS 연동, 냉각 팬·모터 드라이버 제어, 벨트 하우징 및 냉각 구조 제작 |
| **박솔희** (전자공학과) | LoRa 수신기 펌웨어 구현, 패킷 송수신·CRC16 검증, 센서 품질·통합 오류코드 관리, 35B 텔레메트리 패킷 생성·송신 |
| **정여은** (소프트웨어융합학과) | 게이트웨이 서버 구축(FastAPI·SQLite·WebSocket), RiskIndex 엔진 및 안전 상태기계 설계·구현, 관제 대시보드 개발, 해시체인 감사 로그 |

### 참고자료

부품 사양과 안전·환경 지표의 1차 출처는 `HS-PDD-002`/`HS-SIID-002`의 참고자료 절(NIOSH 열
스트레스 권고, NIOSH/OSHA WBGT 안내, ESP32/MAX30102/TMP117/GSR/BQ24074/Heltec ESP32-S3
데이터시트)을 따른다. 구매·인증·현장 적용 전 최신 개정본을 재확인한다.
