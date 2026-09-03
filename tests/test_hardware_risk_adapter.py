from dataclasses import replace

from heatsentry.algorithm.hardware_adapter import HardwareRiskAdapter
import pytest

from heatsentry.algorithm.risk_config import DEFAULT_CONFIG, HARDWARE_CONFIG
from heatsentry.common.errors import ErrorCode
from heatsentry.common.glove_packets import TELEMETRY_PACKET, decode_glove_telemetry


def _fast_baseline(config):
    """3분 기준선을 6초로 줄인 시험용 설정."""
    return replace(config, baseline=replace(config.baseline, min_minutes=0.1, max_minutes=0.2))


# 설계 기준 6특징 설정(DHT가 붙어 있던 시절 경로를 계속 검증한다)
DESIGN_CONFIG = _fast_baseline(DEFAULT_CONFIG)
# 현재 실물 하드웨어 프로필(HRV·IMU·환경 가중치 0)
HW_CONFIG = _fast_baseline(HARDWARE_CONFIG)


def _packet(
    sequence: int,
    *,
    bpm: int = 80,
    skin_c: float = 36.0,
    gsr_diff: int = 0,
    state_cause_word: int = 0,
    stage_risk_word: int = 0,
    flags: int = 0b1001,
):
    payload = TELEMETRY_PACKET.pack(
        0xA55A, 1, 1, sequence, bpm, round(skin_c * 100), 2400, gsr_diff, 60_000,
        state_cause_word, stage_risk_word, 0, 0, 0, 0, 0, flags,
    )
    return decode_glove_telemetry(payload)


def test_design_profile_on_real_packets_loses_three_features():
    """설계 6특징 설정을 실물 패킷에 그대로 쓰면 HRV·IMU·환경이 모두 빠진다.

    HARDWARE_CONFIG가 필요한 이유가 이것이다 — 남은 가중치가 0.55로 고정돼
    정상 착용 중에도 SENSOR_LIMITED가 상시로 뜬다.
    """
    adapter = HardwareRiskAdapter(DESIGN_CONFIG)
    for sequence in range(30):
        reading = adapter.update(_packet(sequence), sequence * 1_000)

    assert reading.baseline_ready
    assert reading.risk is not None
    assert reading.risk.valid_weight == 0.55
    assert reading.risk.sensor_limited is True
    assert reading.risk.contributions["HRV_suppression"] == 0
    assert reading.risk.contributions["ActivityLoad"] == 0
    assert ErrorCode.E104 in reading.risk.active_errors


def test_hardware_profile_uses_three_available_signals_for_high_risk():
    """심박·피부온도·GSR 세 특징만으로 고위험을 판정할 수 있어야 한다."""
    adapter = HardwareRiskAdapter(HW_CONFIG)
    for sequence in range(30):
        adapter.update(_packet(sequence), sequence * 1_000)

    reading = adapter.update(
        _packet(30, bpm=160, skin_c=38.0, gsr_diff=500),
        30_000,
    )
    assert reading.risk is not None
    assert reading.risk.risk_index >= 90
    assert reading.risk.valid_weight == pytest.approx(1.0)
    assert reading.risk.sensor_limited is False


def test_missing_dht_excludes_environment_feature_and_enters_limited_mode():
    adapter = HardwareRiskAdapter(DESIGN_CONFIG)
    for sequence in range(30):
        adapter.update(_packet(sequence), sequence * 1_000)

    reading = adapter.update(_packet(30), 30_000)
    assert reading.risk is not None
    assert reading.risk.valid_weight == 0.55
    assert reading.risk.sensor_limited is True
    assert ErrorCode.E105 in reading.risk.active_errors


# --- 현재 실물 하드웨어 프로필 (DHT 제거 반영) ------------------------------
# 벨트에서 DHT 온습도 센서가 동작하지 않아 제거됐고, 펌웨어는 그 자리를
# 자기 상태/원인 코드 전송에 재활용한다. 설계 가중치를 그대로 쓰면 살아있는
# 가중치가 0.55로 고정돼 실물 장비가 항상 SENSOR_LIMITED로 보고됐다.


def _run_baseline(adapter, *, ticks: int = 30, **packet_kwargs):
    reading = None
    for sequence in range(ticks):
        reading = adapter.update(
            _packet(sequence, **packet_kwargs), sequence * 1_000
        )
    return reading


def test_hardware_weights_sum_to_one_over_available_features():
    """실물에 없는 3특징의 가중치는 0이고, 남은 3특징 합이 1.00이어야 한다."""
    weights = HARDWARE_CONFIG.weights.as_dict()
    assert weights["HRV_suppression"] == 0.0   # 패킷에 RMSSD 필드 없음
    assert weights["ActivityLoad"] == 0.0      # IMU 미탑재
    assert weights["EnvHeatProxy"] == 0.0      # DHT 제거
    assert sum(weights.values()) == pytest.approx(1.0)


def test_healthy_hardware_is_not_permanently_sensor_limited():
    adapter = HardwareRiskAdapter(HW_CONFIG)
    reading = _run_baseline(adapter)
    assert reading.risk is not None
    assert reading.risk.valid_weight == pytest.approx(1.0)
    assert reading.risk.sensor_limited is False


def test_designed_out_sensors_are_not_reported_as_errors():
    """가중치 0인 특징의 결손은 오류가 아니라 설계다 — E104/E105가 상시로 뜨면 안 된다."""
    adapter = HardwareRiskAdapter(HW_CONFIG)
    reading = _run_baseline(adapter)
    codes = {error.value for error in reading.risk.active_errors}
    assert ErrorCode.E104.value not in codes  # IMU 미탑재
    assert ErrorCode.E105.value not in codes  # DHT 제거


def test_real_quality_loss_still_triggers_sensor_limited():
    """설계상 결손을 봐준다고 실제 센서 이탈까지 봐주면 안 된다."""
    adapter = HardwareRiskAdapter(HW_CONFIG)
    _run_baseline(adapter)
    # 손가락이 떨어진 패킷(FINGER_DETECTED 비트 없음) — PPG/EDA/피부온도가 모두 무효
    reading = adapter.update(_packet(30, flags=0b0001), 30_000)
    assert reading.risk.sensor_limited is True
    codes = {error.value for error in reading.risk.active_errors}
    assert ErrorCode.E101.value in codes


def test_risk_score_is_unchanged_by_the_weight_redistribution():
    """가중치 재분배는 valid_weight의 의미만 바꾸고 점수는 그대로여야 한다.

    RiskIndex가 valid_weight로 나눠 재정규화하기 때문이다. 이 성질이 깨지면
    프로필 교체가 조용히 판정 기준을 옮긴 것이므로 CR 대상이다.
    """
    design = HardwareRiskAdapter(DESIGN_CONFIG)
    hardware = HardwareRiskAdapter(HW_CONFIG)
    for adapter in (design, hardware):
        _run_baseline(adapter)

    hot = dict(bpm=160, skin_c=38.0, gsr_diff=500)
    design_reading = design.update(_packet(30, **hot), 30_000)
    hardware_reading = hardware.update(_packet(30, **hot), 30_000)
    assert design_reading.risk.risk_index == hardware_reading.risk.risk_index
