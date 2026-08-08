# 시연 시나리오 & 시험 벡터

> 기준 문서: HS-PDD-002 v2.0 "수상형 시연 구성", "검증 계획과 증거 패키지"; HS-SIID-002 v2.0
> "요구사항-시험 추적 매트릭스". 실행 코드: `node_sim/scenarios.py`, `node_sim/run_demo.py`.

## 지금 바로 돌려보기

```bash
# 1) 게이트웨이
python -m venv .venv && source .venv/bin/activate
pip install -r server/requirements.txt
uvicorn server.app.main:app --reload --port 8000

# 2) 손목+허리 노드 시뮬레이터 (다른 터미널)
python -m node_sim.run_demo --scenario T03 --fast

# 3) 대시보드 (다른 터미널)
cd dashboard && npm install && npm run dev
```

`--fast`는 SYS-001의 3~5분 기준선을 6~9초로 줄여 로컬에서 빨리 확인하기 위한 개발용 플래그다.
실제 심사·시연에서는 절대 쓰지 않는다(`node_sim/run_demo.py`의 `build_config()` 주석 참고).

## 표12/표13 시험 벡터 ↔ node_sim 시나리오

| Test | 절차(문서) | node_sim 시나리오 | 합격 기준 | 자동화 테스트 |
| --- | --- | --- | --- | --- |
| T01 | 기준선 5분 | `--scenario T01` | Baseline Valid | `tests/test_scenarios_integration.py::test_t01_baseline_ends_normal` |
| T02 | 센서 순차 제거 | `--scenario T02` | valid_weight<0.60 → SENSOR_LIMITED | `tests/test_risk_engine.py::test_sensor_limited_when_valid_weight_below_060` |
| T03 | 80 이상 10초 | `--scenario T03` | 2초 내 C1 명령 | `test_t03_risk_rise_reaches_cooling_c1`, `test_t03_reaction_latency_within_2s_of_threshold_met` |
| T04 | 100회+패킷드롭 | `--scenario T04` | 재시도 포함 성공 | `test_t04_ack_retry_recovers_within_max_retries` |
| T05 | STOP/과전류/저온 | `--scenario T05` | 팬 OFF | `test_t05_overcurrent_forces_fan_off` |
| T06 | 냉각 후 30초 재평가 | `--scenario T06` | 단계 하향 | `test_t06_recovers_to_normal` |
| T07 | C2 60초 미회복 | `--scenario T07` | C3·지휘관 확인 | `test_t07_reaches_c3_then_recovers_after_commander_confirm` |
| T08 | 낙상+무동작 | `--scenario T08` | 5초 내 Emergency | `test_t08_emergency_within_5_ticks_of_fall` |
| T09 | 실부하 방전 | (하드웨어 필요, 범위 밖) | 8h/4h 목표 | — |
| T10 | 전원 재인가 포함 5회 연속 | `--scenario T10 --cycles 5` | 5회 연속 성공 | 수동 확인(리허설용) |

로그 변조 검출(T10/DAT-001)은 `tests/test_hash_chain.py`와
`tests/test_gateway_api.py::test_tamper_detected_via_verify_chain`이 담당한다.

## 140초 시연 대본 (PDD "수상형 시연 구성")

1. **0~20초** — preflight: 장치 ID·펌웨어·설정·배터리·센서 품질 확인, 실제 기준선 상태 표시.
   대시보드에서 `state: BASELINE` → `NORMAL` 전환을 보여준다.
2. **20~50초** — `node_sim`으로 재생 데이터를 흘려 RiskIndex 상승, 손목 진동(가상)과 대시보드의
   `WARNING`/`COOLING` 전환을 동시에 보여준다(`--scenario T03`).
3. **50~80초** — 팬 전류·PWM·ACK과 30초 재평가를 한 화면(DeviceCard의 냉각 패널 + EventLog)에서
   확인한다.
4. **80~110초** — 센서 분리(`--scenario T02`) 또는 BLE 손실(RawTick.comms_ok=False)을 주입해
   SENSOR_LIMITED/안전 타이머가 동작함을 증명한다.
5. **110~140초** — 수동 SOS 또는 낙상(`--scenario T08`)으로 EMERGENCY 전이와 Command
   Console의 "현장 확인 후 응급 해제" 절차, 감사 로그를 보여준다.

## P1 인수 체크리스트 (요약)

- [ ] 필수 요구사항/시험 PASS — `pytest -q` 전체 통과
- [ ] P0/P1 결함 0건
- [ ] 5회 연속 시연 — `--scenario T10 --cycles 5`
- [ ] 형상 태그·BOM·설정 보관 — `algorithm/risk_config.py`의 `RISK_CONFIG_VERSION`,
      `common/__init__.py`의 `PROTOCOL_VERSION`/`GATEWAY_SCHEMA_VERSION`
- [ ] 전력·냉각·통신 시험성적 — T05/T09(하드웨어), T04
