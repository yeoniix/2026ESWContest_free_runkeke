# HeatSentry 제품 개념

> 기준 문서: HS-PDD-002 v2.0(제품개발 상세설계서), HS-SIID-002 v2.0(시스템 통합·인터페이스 명세서).
> 이 문서는 그 두 문서의 요지를 코드 저장소 관점에서 요약한다. 세부 수치·표는 원본 PDF가 기준이며,
> 여기서는 "왜 이렇게 만들었는지"와 "그래서 코드가 어떻게 생겼는지"를 연결하는 데 집중한다.

## 한 문장 정의

HeatSentry는 질병을 진단하는 장비가 아니라, 개인 생체신호와 활동·환경 정보를 결합해 위험 징후를
조기에 포착하고 **자동 냉각과 구조 절차를 연결하는 현장 안전 시스템**이다.

- RiskIndex와 피부온도는 **의료 진단값이 아니다.**
- 열사병 의심 증상, 의식 변화, 무응답이 있으면 장치 점수와 무관하게 **현장 응급절차가 항상 우선한다.**

## 문제정의

집단훈련에서는 개인이 자신의 열 스트레스 상태를 스스로 정확히 판단하기 어렵다(자가판단 실패).
HeatSentry는 다음을 조기에 탐지해 시스템이 이를 보완한다.

- 활동량은 낮아졌는데 심박수가 계속 높은 경우(회복 지연)
- 피부 온도가 지속적으로 상승하는 경우
- 낙상 후 움직임·응답이 없는 경우
- 위 상태가 자동 개입(냉각) 후에도 회복되지 않는 경우

## 차별점: "경보"가 아니라 "폐루프"

단순 경보 장치와의 차이는 다음 폐루프를 실제로 완성한다는 것이다.

```
센서 → RiskIndex → 자동 냉각 → 30초 재평가 → (미회복 시 에스컬레이션) → SOS → 감사 로그
```

이 폐루프는 이 저장소에서 다음과 같이 코드로 존재한다.

| 폐루프 단계 | 코드 |
| --- | --- |
| 센서 → RiskIndex | `heatsentry/algorithm/risk_engine.py` |
| RiskIndex → 상태/냉각 판정 | `heatsentry/algorithm/fsm.py` |
| 냉각 명령/ACK | `heatsentry/common/packets.py`, `heatsentry/simulator/belt_node.py` |
| 30초 재평가·미회복 에스컬레이션 | `heatsentry/algorithm/fsm.py`의 `HoldTimer` 기반 임계값 로직 |
| SOS/응급 | `HeatSentryFsm.emergency_latched`, `close_emergency()` |
| 감사 로그 | `heatsentry/common/hash_chain.py`, `heatsentry/server/state.py`, `heatsentry/server/db.py` |

## 서브시스템

| ID | 이름 | 책임 | 하지 않는 일 |
| --- | --- | --- | --- |
| SU-W | 손목 노드 | 센서 품질·RiskIndex·상태·냉각 명령 | 장거리 통신·의료진단 |
| SU-B | 허리 노드 | 팬·PCM·전력·안전 정지·ACK | 위험도 최종 판정 |
| SU-E | 환경 노드 | EnvHeatProxy·장소 시간 | WBGT 진단값 생성 |
| SU-G | 게이트웨이 | BLE 집계·저장·WebSocket·선택 LoRa | 센서 원시판정 대체 |
| SU-D | 대시보드 | 경보·확인·로그·시험 내보내기 | 응급 자동 해제 |

자세한 인터페이스·상태기계는 [architecture.md](architecture.md), 알고리즘은 [ai_pipeline.md](ai_pipeline.md),
저장·감사 설계는 [aar_design.md](aar_design.md), 시연 절차는 [demo_scenario.md](demo_scenario.md) 참고.

## 개발 단계

| 단계 | 목표 | 이 저장소의 대응 |
| --- | --- | --- |
| P0 기능증명 | 신호·팬 확인 | `heatsentry/simulator/`가 실제 하드웨어 없이도 동일한 신호·판정 흐름을 소프트웨어로 재현 |
| P1 대회 MVP | 8주 폐루프 시연 | `heatsentry/algorithm/` + `heatsentry/server/` + `heatsentry/simulator/` + `dashboard/`로 폐루프 완성(본 커밋 기준) |
| P2 현장 확장 | 다중 인원·장거리 | LoRa/KR920, 다중 착용자, 실물 BLE는 범위 밖(P1 이후) |

## 안전 경계 (반드시 지켜야 하는 것)

1. 대시보드는 Emergency를 자동 해제할 수 없다 — `heatsentry/server/state.py`의 `close_emergency()`는 감사 기록만
   남기고, 장치의 실제 EMERGENCY 래치(`heatsentry/algorithm/fsm.py`의 `emergency_latched`)는 건드리지 않는다.
2. "알림 확인"과 "응급 해제"는 다른 버튼·다른 권한이다 — `dashboard/src/components/CommandConsole.tsx`.
3. 강제 대응(자동 냉각)은 처벌이 아니라 안전장치다. 자동 개입이 실패해도 수동 정지(`belt.press_physical_stop()`)와
   구조 절차(EMERGENCY 래치)는 항상 유지된다.
