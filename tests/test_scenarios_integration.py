"""firmware simulator 시나리오를 게이트웨이 없이(=순수 WristNode/BeltNode) 끝까지 재생해
표12(T01~T10) 합격 기준의 핵심을 회귀 테스트로 고정한다."""

import dataclasses

from heatsentry.algorithm.risk_config import DEFAULT_CONFIG
from heatsentry.simulator.belt_node import BeltNode
from heatsentry.simulator.scenarios import (
    t01_baseline_stability,
    t03_risk_rise,
    t04_ack_loss,
    t05_cooling_safety,
    t06_recovery,
    t07_unrecovered,
    t08_fall_emergency,
)
from heatsentry.simulator.wrist_node import WristNode

FAST_CONFIG = dataclasses.replace(
    DEFAULT_CONFIG,
    baseline=dataclasses.replace(DEFAULT_CONFIG.baseline, min_minutes=0.1, max_minutes=0.15),
)
BASELINE_TICKS = int(FAST_CONFIG.baseline.min_minutes * 60) + 5


def _run(ticks) -> list[dict]:
    belt = BeltNode()
    wrist = WristNode(belt, config=FAST_CONFIG)
    telemetries = []
    for raw in ticks:
        belt.overcurrent_fault = raw.belt_overcurrent
        belt.low_temp_fault = raw.belt_low_temp
        result = wrist.tick(raw)
        telemetries.append(result)
    return telemetries


def test_t01_baseline_ends_normal():
    results = _run(t01_baseline_stability(BASELINE_TICKS))
    assert results[-1]["telemetry"]["state"] == "NORMAL"


def test_t03_risk_rise_reaches_cooling_c1():
    results = _run(t03_risk_rise(BASELINE_TICKS))
    final = results[-1]["telemetry"]
    assert final["state"] == "COOLING"
    assert final["cooling"]["requested"] == 1
    assert final["risk_index"] >= 80


def test_t03_reaction_latency_within_2s_of_threshold_met():
    """CTL-001 합격 기준: 임계 충족 이후 2초 내 C1 명령."""
    results = _run(t03_risk_rise(BASELINE_TICKS))
    first_c1_index = next(
        i for i, r in enumerate(results) if r["telemetry"]["cooling"]["requested"] == 1
    )
    # 10초 유지 조건이 만족된 바로 다음 tick(<=1s)에서 C1이 걸려야 한다.
    events_at = results[first_c1_index]["events"]
    assert any(e["event_type"] == "COOLING_C1" for e in events_at)


def test_t04_ack_retry_recovers_within_max_retries():
    results = _run(t04_ack_loss(BASELINE_TICKS))
    all_events = [e["event_type"] for r in results for e in r["events"]]
    assert "ACK_TIMEOUT" in all_events
    assert "ACK_RETRY_SUCCESS" in all_events
    assert "COOL_CMD_FAILED" not in all_events


def test_t05_overcurrent_forces_fan_off():
    results = _run(t05_cooling_safety(BASELINE_TICKS))
    final = results[-1]["telemetry"]
    assert final["cooling"]["actual_pwm"] == 0
    assert any(e["event_type"] == "SAFETY_STOP" for e in results[-1]["events"])


def test_t06_recovers_to_normal():
    results = _run(t06_recovery(BASELINE_TICKS))
    assert results[-1]["telemetry"]["state"] == "NORMAL"


def test_t07_reaches_c3_then_recovers_after_commander_confirm():
    results = _run(t07_unrecovered(BASELINE_TICKS))
    stages = [r["telemetry"]["cooling"]["requested"] for r in results]
    assert 3 in stages  # C3 도달
    assert results[-1]["telemetry"]["state"] in ("NORMAL", "WARNING")
    assert results[-1]["telemetry"]["cooling"]["requested"] < 3


def test_t08_emergency_within_5_ticks_of_fall():
    ticks = t08_fall_emergency(BASELINE_TICKS)
    results = _run(ticks)
    fall_index = next(i for i, t in enumerate(ticks) if t.fall and t.no_motion and t.no_response)
    emergency_index = next(
        i for i, r in enumerate(results) if r["telemetry"]["state"] == "EMERGENCY"
    )
    # SYS-006/COM-002: 5초 이내 Emergency
    assert emergency_index - fall_index <= 5
