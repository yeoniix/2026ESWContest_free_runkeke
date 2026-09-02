# 시스템 아키텍처

> 기준 문서: HS-SIID-002 v2.0. 통합 원칙: "인터페이스는 먼저 동결하고 구현은 교체 가능하게 한다.
> BLE Mesh·LoRa는 핵심 폐루프 밖에 두어, 장거리 통신이 없어도 안전 개입과 로컬 관제가 완전하게
> 동작해야 한다."

## 계층

```
착용자 계층                현장 엣지 계층              지휘/기록 계층
손목 노드(SU-W) ── BLE ──▶ 게이트웨이(SU-G) ── LAN/선택 KR920 ──▶ 지휘소
허리 노드(SU-B) ◀─┘         (BLE 집계·저장·WebSocket)

               ▲
               │ 폐루프 개입: RiskIndex 상승 → 진동 경고 →
               │ 자동 냉각 → 30초 재평가 → 미회복 시 상향
               │
        환경 노드(SU-E, EnvHeatProxy)
```

## 이 저장소에서의 구현 매핑

실제 nRF52840 펌웨어와 BLE Central 스택은 P1 범위 밖(하드웨어 조달 이후)이므로, 지금은 **같은
인터페이스 계약을 소프트웨어로 재현**해 두었다. 나중에 진짜 BLE GATT로 교체할 때 바뀌는 것은
전송 계층뿐이고, `heatsentry/algorithm/`과 `heatsentry/common/`의 판정·패킷 로직은 그대로 재사용된다.

| ICD 개념 | 실물(향후) | 지금 이 저장소 |
| --- | --- | --- |
| SU-W 손목 노드 | ESP32 + PPG/온도/EDA/IMU | `heatsentry/simulator/wrist_node.py` (`WristNode`) |
| SU-B 허리 노드 | ESP32 + PCM/블로워/전류센서 | `heatsentry/simulator/belt_node.py` (`BeltNode`) |
| SU-E 환경 노드 | SHT41 | `heatsentry/simulator/env_node.py` (`EnvNode`) |
| SU-G 게이트웨이 | Raspberry Pi 5 + BLE Central | `heatsentry/server/main.py` (FastAPI) |
| SU-D 대시보드 | 태블릿 브라우저 | `dashboard/` (React + Vite) |
| IF-02/03 (손목↔허리 BLE GATT) | 실제 BLE | `WristNode._send_cool_cmd()` → `BeltNode.handle_cmd()` 직접 호출(인프로세스) |
| IF-04 (노드→게이트웨이 BLE GATT) | 실제 BLE | `POST /ingest/telemetry`, `/ingest/event`, `/ingest/command_ack` (`heatsentry/server/routes_ingest.py`) |
| IF-05 (게이트웨이→UI WebSocket) | 그대로 | `GET /ws/live` (`heatsentry/server/ws.py`) — 이미 최종 형태 |
| IF-06 (UI→게이트웨이 REST) | 그대로 | `/api/v2/*` (`heatsentry/server/routes_api_v2.py`) — 이미 최종 형태 |
| IF-07 (게이트웨이→지휘소, 선택 LoRa) | KR920 | 범위 밖(P2) |

IF-05/06은 처음부터 소프트웨어 인터페이스라 지금 구현이 곧 최종 구현이다. IF-01~04만 "BLE 대신
HTTP로 같은 계약을 흉내낸 것"이라는 점을 구분해서 봐야 한다.

## 책임 경계가 코드에 남아있는 방식

- `heatsentry/server/state.py`의 `GatewayStore`는 **RiskIndex를 절대 재계산하지 않는다.** SU-G의
  "하지 않는 일: 센서 원시판정 대체"를 지키기 위해, telemetry를 받아 저장·집계·전파만 하고
  상태 전이가 생기면 `STATE_CHANGE` 이벤트만 파생시킨다.
- `heatsentry/simulator/belt_node.py`의 `BeltNode`는 RiskIndex/FSM을 아예 import하지 않는다. SU-B의
  "하지 않는 일: 위험도 최종 판정"을 코드 레벨에서 강제한 것이다.
- Emergency 해제는 게이트웨이(`/api/v2/emergency/{id}/close`)가 감사 기록만 남기고, 실제 래치
  해제는 `HeatSentryFsm.close_emergency()`를 통해서만 가능하다 — 이 함수는 대시보드 API가 직접
  호출하지 않는다("금지 사항" 참고, [concept.md](concept.md)).

## 상태기계

```
BASELINE → NORMAL → WARNING → COOLING(C1→C2→C3) → EMERGENCY(C4)
             ▲                        │
             └──── 회복 시 단계 하향(히스테리시스) ──┘

낙상+무동작+무응답 또는 수동 SOS는 RiskIndex와 무관하게 즉시 EMERGENCY로 상향한다.
```

구현: `heatsentry/algorithm/fsm.py`의 `HeatSentryFsm`. 임계값·유지시간은 `heatsentry/algorithm/risk_config.py`의
`FsmConfig`에 모여 있으며, 문서에 명시된 값과 "설계 기본값(CR 대상)"을 코드 주석으로 구분해 둔다.

## 명령 중재 우선순위

1. 수동 STOP/과전류/저온 → 팬 OFF, 안전 오류 유지
2. 수동 SOS/낙상+무동작+무응답 → Emergency, 관제 즉시
3. RiskIndex 상태 전이 → C0~C4 명령
4. 지휘관 수동 냉각 → 안전 한계 내 명령
5. 시험 모드 → 명시적 TEST 플래그

구현: `heatsentry/algorithm/fsm.py`의 `HeatSentryFsm.update()` 하단 "명령 중재" 블록, `ManualInputs` 데이터클래스.

## 통신·시간 기준

- `monotonic_ms`(부팅 후 경과)는 상태 전이·지연 계산에, `gateway_utc`는 감사·내보내기에 쓴다
  (`heatsentry/common/schema.py`의 `TelemetryV2`, `EventRecord`).
- 냉각 명령은 `cmd_id`+`sequence`로 idempotent하게 재전송한다(`heatsentry/common/packets.py`의 `CoolCmd`,
  `heatsentry/simulator/belt_node.py`의 `_processed_cmds` 캐시).
- BLE 10초 손실 시 새 명령 없음, 60초 시 팬 20%로 안전 하향 — `heatsentry/simulator/belt_node.py`의
  `BeltNode.tick()`이 손목과 무관하게 스스로 이 타이머를 돈다(실제 허리 MCU가 별도 워치독을
  갖는 것과 같은 이유).

## 다음에 할 일(하드웨어 붙일 때)

1. `heatsentry/common/packets.py`의 바이트 레이아웃을 실제 BLE GATT characteristic으로 옮긴다 — 로직은
   이미 있으므로 전송 계층만 구현하면 된다.
2. `heatsentry/simulator/wrist_node.py` / `belt_node.py`의 판정·안전 로직을 ESP32 펌웨어(C/C++)로
   포팅한다. `heatsentry/algorithm/`의 파이썬 코드가 그대로 레퍼런스 구현이 된다.
3. `heatsentry/server/routes_ingest.py`의 HTTP 엔드포인트를 BLE Central 수신 데몬으로 교체한다 —
   `GatewayStore` 이하는 변경할 필요가 없다.
