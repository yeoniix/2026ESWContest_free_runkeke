# 펌웨어 인터페이스 계약 (ICD 요약)

> 기준 문서: HS-SIID-002 v2.0. 이 문서는 손목(SU-W)/허리(SU-B) 펌웨어를 실제로 작성할 때 참고할
> "계약" 요약본이다. 바이트 단위 정의의 1차 소스는 `heatsentry/common/packets.py`이며, 이 문서와 코드가
> 어긋나면 **코드가 아니라 이 문서를 고친다** (인터페이스는 먼저 동결하고 구현은 교체 가능하게
> 한다는 통합 원칙).

## 형상 기준선

| 항목 | 기준 | 이 저장소 위치 |
| --- | --- | --- |
| protocol_version | 2 | `heatsentry/common/PROTOCOL_VERSION`, `heatsentry/common/packets.py` |
| risk_config_version | 0.4.0 | `heatsentry/algorithm/risk_config.py`의 `RISK_CONFIG_VERSION` |
| gateway_schema | 2.0 | `heatsentry/common/GATEWAY_SCHEMA_VERSION`, `heatsentry/common/schema.py` |
| test_vector | TV-20260808-A | `heatsentry/simulator/scenarios.py` (결정적 재생, 난수 없음) |

## 인터페이스 목록

| IF | 송신→수신 | 방식(문서) | 지금 구현 |
| --- | --- | --- | --- |
| IF-01 | 손목 센서→RiskTask | 로컬 큐, 10~1000ms | `heatsentry/simulator/wrist_node.py`의 `WristNode.tick()` (1Hz) |
| IF-02 | 손목→허리 | BLE GATT, 명령 즉시 | `WristNode._send_cool_cmd()` → `BeltNode.handle_cmd()` |
| IF-03 | 허리→손목 | BLE Notify, 1s/이벤트 | `CoolAck` 반환값(동기 호출) |
| IF-04 | 노드→게이트웨이 | BLE GATT, 1s/이벤트 | `POST /ingest/telemetry`·`/ingest/event`·`/ingest/command_ack` |
| IF-05 | 게이트웨이→UI | WebSocket, ≤1s | `GET /ws/live` |
| IF-06 | UI→게이트웨이 | REST, 사용자 동작 | `/api/v2/*` |
| IF-07 | 게이트웨이→지휘소 | 선택 KR920/LAN | 범위 밖(P2) |

IF-01~04는 실제 BLE 스택이 없는 지금 단계에서 **HTTP/인프로세스 호출로 같은 계약을 흉내낸
것**이다. 펌웨어 담당자가 실제 nRF52840 BLE 스택으로 옮길 때는 아래 바이트 레이아웃만 그대로
GATT characteristic payload로 쓰면 된다.

## BLE 역할과 GATT 서비스

게이트웨이가 Central, 손목·허리가 Peripheral. 손목↔허리 직접 연결 우선, 동시 연결 수 초과 시
손목이 허리 상태를 게이트웨이에 릴레이한다.

| Characteristic | 방향 | 속성 | 길이 | 구현 |
| --- | --- | --- | --- | --- |
| HS_STATUS | W→G/B | Notify | 24B | `common.packets.HsStatus` |
| COOL_CMD | W→B | Write+ACK | 12B | `common.packets.CoolCmd` |
| COOL_ACK | B→W | Notify | 16B | `common.packets.CoolAck` |
| BELT_STATUS | B→W/G | Notify | 20B | `common.packets.BeltStatus` (초안, 아래 참고) |
| SOS_EVENT | W/B→G | Indicate | 24B | 미구현 — CR 필요 |
| CONFIG | G→W/B | Write | 가변 | `PUT /api/v2/config` (HMAC 서명, `heatsentry/server/routes_api_v2.py`) |

### 바이트 레이아웃

### 현재 Heltec LoRa 센서 텔레메트리 (35B)

하드웨어 팀의 현재 구현은 `TelemetryPacket` packed 구조체를 LoRa로 보낸다. ESP32는
little-endian이므로 서버/게이트웨이 디코더도 같은 순서(`<HBBHBhHhIhHiiBhHB`)를 쓴다.
디코더 구현은 `heatsentry/common/glove_packets.py`에 있다.

| flags bit | 의미 |
| --- | --- |
| 0 | 장갑 데이터 유효 |
| 1 | DHT11 데이터 유효 — **현재 펌웨어는 세우지 않는다** |
| 2 | GPS Fix 유효 |
| 3 | Finger 감지 |
| 4 | 벨트 비상 버튼 활성 |
| 5 | 벨트 팬 ON |

`Finger=NO`, `BPM=0`, 또는 장갑 데이터 무효는 위험점수 0이 아니라 LCD의
`SENSOR CHECK / WEAR GLOVE` 상태로 처리한다. 이 LoRa payload는 현장 하드웨어
중간 형식이며, 게이트웨이 API의 `TelemetryV2`와는 별개다.

#### `airTemp_x10` 자리의 용도 변경 (중요)

벨트에서 DHT11 온습도 센서가 동작하지 않아 하드웨어에서 제거됐다. 펌웨어는 빈
16비트 자리를 자신이 판정한 상태·원인 코드를 관제로 올리는 데 재활용한다.

```c
// firmware/belt_heltec/belt_heltec.ino, makeTelemetryPacket()
txData.airTemp_x10  = (state << 8) | cause;   // DisplayPacket과 같은 코드 체계
txData.humidity_x10 = 0;                       // 미사용
// flags의 DHT_DATA(bit1)는 세우지 않는다
```

**DHT_DATA 플래그가 이 자리의 의미를 결정한다.** 서 있으면 옛 정의대로 기온/습도,
서 있지 않으면(현재 펌웨어) 벨트의 상태/원인이다. 디코더
`heatsentry/common/glove_packets.py`는 플래그를 보고 둘 중 하나만 유효한 값으로
돌려주고, 나머지 쪽에는 `None`을 준다. 상태/원인 코드값은
`firmware/*/display_protocol.h`의 `StateCode`/`CauseCode`와 같으며,
`tests/test_display_protocol_sync.py`가 펌웨어 헤더와 파이썬 정의의 일치를 검사한다.

#### 실물 하드웨어의 RiskIndex 특징 (3개)

현재 패킷에는 6특징 중 3개가 없다 — HRV(RMSSD 필드 없음), ActivityLoad(IMU 미탑재),
EnvHeatProxy(DHT 제거). `heatsentry/algorithm/hardware_adapter.py`는 없는 값을 0으로
넣지 않고, 남은 3특징에 가중치를 재분배한 `HARDWARE_CONFIG`를 쓴다.

| 특징 | 설계 가중치 | 하드웨어 프로필 |
| --- | --- | --- |
| HR_dev | 0.25 | 0.45 |
| SkinTemp_slope | 0.20 | 0.37 |
| EDA_delta | 0.10 | 0.18 |
| HRV_suppression | 0.10 | 0.00 (패킷에 없음) |
| ActivityLoad | 0.15 | 0.00 (IMU 미탑재) |
| EnvHeatProxy | 0.20 | 0.00 (DHT 제거) |

RiskIndex는 `valid_weight`로 나눠 재정규화하므로 **점수 자체는 달라지지 않는다.**
달라지는 것은 `valid_weight`의 의미다 — 설계 가중치를 그대로 쓰면 살아있는 가중치가
0.55로 고정돼 실물 장비가 항상 `SENSOR_LIMITED`로 보고됐고, 실제 조치가 필요한
품질 저하(E101 손가락 이탈, E103 온도 센서 정지)와 구분되지 않았다. 같은 이유로
가중치가 0인 특징의 결손은 오류로 보고하지 않는다(E104/E105 상시 발생 방지).

#### 판정이 두 벌인 이유

벨트 펌웨어는 LoRa가 끊겨도 팬과 장갑 OLED를 스스로 구동해야 하므로 자체
위험점수·상태기계를 갖고 있고, 게이트웨이는 같은 패킷으로 RiskIndex v0.3을 따로
계산한다. 두 판정은 임계값도 입력 특징도 다르다.

| | 게이트웨이 (RiskIndex v0.3) | 벨트 펌웨어 |
| --- | --- | --- |
| 점수 | 3~6특징 가중합, 품질 재정규화 | BPM/피부온도/GSR 가산식 |
| 경고 | WARNING: risk≥60, 10초 | CAUTION: risk≥40, 즉시 |
| 1단계 냉각 | C1: risk≥80, 10초 — 팬 50% 듀티 | risk 60~84, 10초 — 팬 2개 중 1개 100% |
| 2단계 냉각 | C2: risk≥90, 10초 — 팬 100% | risk≥85, 10초 — 팬 2개 100% |
| 기준선 | 3~5분, 품질 게이트, median/MAD | 3분, 단순 평균 |
| 강등 | 히스테리시스(70/30초 등) | 없음 |

`heatsentry/server/lora_adapter.py`는 **어느 한쪽으로 덮어쓰지 않는다.** 게이트웨이
판정은 `state`/`risk_index`에, 벨트 판정은 `raw.belt_state`/`raw.belt_cause`에 실린다.
현장에서 팬이 돌고 장갑 화면이 바뀐 근거는 후자다. 둘이 갈리면 `active_errors`에
`BELT_STATE_MISMATCH`를 남겨 관제 화면에 드러낸다.

**공통 헤더 + HS_STATUS (24B)** — `heatsentry/common/packets.py`의 `HsStatus`:

```
0      protocol_version u8      = 2
1      msg_type         u8      0x01 status
2-3    payload_len      u16 LE
4-7    monotonic_ms     u32 LE
8-9    sequence         u16 LE
10     state            u8      DeviceState enum
11     risk_index       u8      0~100, 255=invalid
12     sensor_quality   u8      0~100
13     flags            u8      bit0 FALL, bit1 SOS, bit2 SENSOR_LIMITED, bit3 COOLING
14-21  payload(8B)      -       heart_rate_bpm(u8), skin_temp_x100(u16), eda_norm_x1000(u16),
                                 battery_percent(u8), reserved(u16)
22-23  crc16            u16 LE  CRC-16/CCITT-FALSE
```

**COOL_CMD (12B)** — `common.packets.CoolCmd`:

```
0      version    u8
1      level      u8   fan percent (0/50/100)
2-3    duration_s u16 LE
4-5    cmd_id     u16 LE
6-7    sequence   u16 LE
8      reason     u8   CoolReason enum (RISK_FSM/COMMANDER/TEST/SAFETY_STOP/EMERGENCY)
9      flags      u8   bit0 TEST_MODE, bit1 SOS
10-11  crc16      u16 LE
```

**COOL_ACK (16B)** — `common.packets.CoolAck`:

```
0-1    cmd_id           u16 LE
2-3    sequence         u16 LE
4      result           u8   AckResult enum (OK/REJECTED_SAFETY/IDEMPOTENT_REPEAT)
5      actual_pwm       u8
6-7    current_mA       u16 LE
8-9    belt_temp_centiC i16 LE
10-11  error_bits       u16 LE
12-13  reserved
14-15  crc16            u16 LE
```

**BELT_STATUS (20B, 초안)** — `common.packets.BeltStatus`. ICD 표4는 길이(20B)와 내용
("배터리·전압·온도·팬")만 정하고 바이트 배치는 정하지 않았다. 아래는 통합팀 CR 승인 전까지의
제안이며, 실제 펌웨어 구현 전에 CR로 고정해야 한다:

```
0      protocol_version u8
1-2    sequence         u16 LE
3-6    monotonic_ms     u32 LE
7      battery_percent  u8
8-9    voltage_mV       u16 LE
10-11  belt_temp_centiC i16 LE
12     fan_pwm_percent  u8
13-14  fan_rpm          u16 LE
15-16  current_mA       u16 LE
17     error_bits       u8   (허리 관련 오류만: E301=bit0, E302=bit1, E303=bit2)
18-19  crc16            u16 LE
```

**SOS_EVENT (24B)** — 아직 코드로 구현하지 않았다. ICD는 "원인·위치상태·seq"만 명시한다.
현재는 EMERGENCY 상태 전이가 `HS_STATUS`의 `flags` bit1(SOS)과 `state=EMERGENCY`로 이미
전달되므로 기능적으로는 대체되지만, Indicate 방식의 별도 긴급 채널이 필요하면 CR로 필드를
확정한 뒤 `heatsentry/common/packets.py`에 추가한다.

## 연결·재전송 정책

1. COOL_CMD는 `cmd_id`+`sequence`를 포함하고, 500ms 이내 ACK 없으면 최대 3회 재전송한다.
   구현: `heatsentry/simulator/wrist_node.py`의 `WristNode._send_cool_cmd()` (`RawTick.drop_ack_attempts`로
   시험 가능).
2. 동일 `cmd_id` 재수신 시 허리는 팬을 재시작하지 않고 현재 결과만 ACK한다(idempotent).
   구현: `heatsentry/simulator/belt_node.py`의 `BeltNode._processed_cmds` 캐시.
3. 상태 Notify는 손실 허용, Emergency는 Indicate 또는 애플리케이션 ACK을 쓴다.
4. 연결 손실 10초에서 COMMS_LOST(E201), 60초에서 팬 안전 타이머(50%로 하향) — 구현:
   `heatsentry/simulator/belt_node.py`의 `BeltNode.tick()`, 상수는 `heatsentry/common/errors.py`의
   `BLE_COMMS_LOST_S`/`FAN_SAFETY_TIMER_S`/`FAN_SAFETY_LEVEL`.

## 통합 오류코드

| 코드 | 조건 | 로컬 동작 | 관제 표시 | RiskIndex 영향 |
| --- | --- | --- | --- | --- |
| E101 | PPG Quality<70 10초 | HR 제외·SENSOR_LIMITED 가능 | 노란 품질 | HR_dev, HRV_suppression 제외 |
| E102 | EDA 접촉 손실 | EDA 가중치 제외 | 회색 입력 | EDA_delta 제외 |
| E103 | 피부온도 오류 | 온도 가중치 제외 | 센서 오류 | SkinTemp_slope 제외 |
| E104 | IMU 응답 없음 | 낙상 비활성·위험표시 | 기능 제한 | ActivityLoad 제외 |
| E105 | 환경 온습도 데이터 없음/저품질 | 환경열부하 제외 | 환경 센서 오류 | EnvHeatProxy 제외 |
| E201 | BLE 10초 손실 | 재연결·팬 안전타이머 | 통신 손실 | — |
| E301 | 팬 과전류/정지 | 팬 OFF | 긴급 장치오류 | — |
| E302 | 배터리 10% 이하 | 출력 제한 | 저배터리 | — |
| E303 | 접촉부 저온 | 팬 OFF·PCM 분리 안내 | 안전 알림 | — |
| E401 | 로그 저장 실패 | RAM 큐·재시도 | 무결성 경고 | — |

전체 정의: `heatsentry/common/errors.py`의 `ERROR_TABLE`.

## 저하 모드 원칙

1. `valid_weight >= 0.60`이면 가중치를 재정규화해 운용한다(`heatsentry/algorithm/risk_engine.py`).
2. IMU가 없으면 낙상 검출을 끄고 기능 제한을 표시한다(E104).
3. 게이트웨이가 없어도 손목↔허리 자동 냉각·로컬 경고는 유지된다 — `heatsentry/simulator/wrist_node.py`와
   `belt_node.py`는 게이트웨이 연결 여부와 무관하게 판정·안전 로직을 수행한다(전송만 별도).
4. 장거리 브리지(LoRa/KR920)가 없는 것은 전체 시스템 장애가 아니다 — IF-07은 애초에 P1 범위 밖.

## 호환성 규칙

- 수신 장치는 `protocol_version`과 `payload_len`을 먼저 확인한다(`heatsentry/common/packets.py`의
  `_check_common_header`).
- 알 수 없는 `msg_type`은 무시하고 `UNSUPPORTED_MESSAGE` 이벤트를 남긴다 — 현재
  `heatsentry/common/packets.py`는 알려진 타입만 디코드하며, 게이트웨이 쪽에서 알 수 없는 메시지를 받으면
  `PacketError`가 발생한다. 실제 펌웨어에서는 예외 대신 이벤트 로깅 후 무시하도록 구현해야 한다
  (P1 TODO).
- `protocol_version` 또는 `risk_config_version`이 오르면 CR에 반드시 명시한다
  (HS-SIID-002 "변경요청(CR) 필수 필드").
