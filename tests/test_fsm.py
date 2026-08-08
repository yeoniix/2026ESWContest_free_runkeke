from algorithm.fsm import HeatSentryFsm, ManualInputs
from algorithm.risk_engine import RiskResult
from common.packets import CoolReason, DeviceState


def _risk(index: int, hard_trigger: bool = False) -> RiskResult:
    return RiskResult(
        risk_index=index, valid_weight=1.0, sensor_limited=False, hard_trigger=hard_trigger,
        contributions={}, features={}, active_errors=[],
    )


def test_c1_enters_after_10s_above_80_ctl_001():
    fsm = HeatSentryFsm()
    for _ in range(9):
        out = fsm.update(_risk(85), dt_s=1.0)
        assert out.cooling_stage == "C0"
    out = fsm.update(_risk(85), dt_s=1.0)
    assert out.cooling_stage == "C1"
    assert out.commanded_fan_percent == 20
    assert out.device_state == DeviceState.COOLING


def test_c1_does_not_enter_before_10s():
    fsm = HeatSentryFsm()
    for _ in range(5):
        out = fsm.update(_risk(90), dt_s=1.0)
    assert out.cooling_stage == "C0"


def test_can_skip_directly_to_c2_when_risk_jumps_high():
    fsm = HeatSentryFsm()
    for _ in range(10):
        out = fsm.update(_risk(92), dt_s=1.0)
    assert out.cooling_stage == "C2"
    assert out.commanded_fan_percent == 60


def test_c3_requires_60s_unrecovered_and_commander_confirm_to_downgrade():
    fsm = HeatSentryFsm()
    for _ in range(60):
        out = fsm.update(_risk(92), dt_s=1.0)
    assert out.cooling_stage == "C3"
    assert out.commanded_fan_percent == 100

    # 지휘관 확인 없이는 하향하지 않는다
    for _ in range(60):
        out = fsm.update(_risk(50), dt_s=1.0)
    assert out.cooling_stage == "C3"

    fsm.confirm_recovery()
    out = fsm.update(_risk(50), dt_s=1.0)
    assert out.cooling_stage == "C2"


def test_c1_exits_after_30s_below_70():
    fsm = HeatSentryFsm()
    for _ in range(10):
        fsm.update(_risk(85), dt_s=1.0)
    assert fsm.stage == "C1"
    for _ in range(30):
        out = fsm.update(_risk(50), dt_s=1.0)
    assert out.cooling_stage == "C0"


def test_hard_trigger_forces_emergency_regardless_of_risk_index():
    fsm = HeatSentryFsm()
    out = fsm.update(_risk(10, hard_trigger=True), dt_s=1.0)
    assert out.cooling_stage == "C4"
    assert out.device_state == DeviceState.EMERGENCY
    assert out.sos is True


def test_emergency_does_not_auto_clear_on_low_risk():
    fsm = HeatSentryFsm()
    fsm.update(_risk(10, hard_trigger=True), dt_s=1.0)
    for _ in range(120):
        out = fsm.update(_risk(0), dt_s=1.0)
    assert out.cooling_stage == "C4"  # 금지 사항: 자동 해제 없음


def test_close_emergency_requires_explicit_call():
    fsm = HeatSentryFsm()
    fsm.update(_risk(10, hard_trigger=True), dt_s=1.0)
    fsm.close_emergency()
    out = fsm.update(_risk(0), dt_s=1.0)
    assert out.cooling_stage != "C4"


def test_safety_stop_forces_fan_off_but_keeps_stage():
    fsm = HeatSentryFsm()
    for _ in range(10):
        fsm.update(_risk(85), dt_s=1.0)
    assert fsm.stage == "C1"

    out = fsm.update(_risk(85), dt_s=1.0, manual=ManualInputs(safety_stop=True))
    assert out.commanded_fan_percent == 0
    assert out.cool_reason == CoolReason.SAFETY_STOP
    assert out.cooling_stage == "C1"  # 표7: 팬 OFF지만 판정 자체는 유지


def test_warning_hysteresis_enter_and_exit():
    fsm = HeatSentryFsm()
    for _ in range(10):
        out = fsm.update(_risk(65), dt_s=1.0)
    assert out.warning_active is True

    for _ in range(30):
        out = fsm.update(_risk(50), dt_s=1.0)
    assert out.warning_active is False
