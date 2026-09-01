from dataclasses import replace

from algorithm.hardware_adapter import HardwareRiskAdapter
from algorithm.risk_config import DEFAULT_CONFIG
from common.errors import ErrorCode
from common.glove_packets import TELEMETRY_PACKET, decode_glove_telemetry


HARDWARE_CONFIG = replace(
    DEFAULT_CONFIG,
    baseline=replace(DEFAULT_CONFIG.baseline, min_minutes=0.1, max_minutes=0.2),
)


def _packet(
    sequence: int,
    *,
    bpm: int = 80,
    skin_c: float = 36.0,
    gsr_diff: int = 0,
    air_c: float = 25.0,
    humidity: float = 50.0,
    flags: int = 0b1011,
):
    payload = TELEMETRY_PACKET.pack(
        0xA55A, 1, 1, sequence, bpm, round(skin_c * 100), 2400, gsr_diff, 60_000,
        round(air_c * 10), round(humidity * 10), 0, 0, 0, 0, 0, flags,
    )
    return decode_glove_telemetry(payload)


def test_hardware_profile_excludes_unavailable_hrv_and_imu_features():
    adapter = HardwareRiskAdapter(HARDWARE_CONFIG)
    for sequence in range(30):
        reading = adapter.update(_packet(sequence), sequence * 1_000)

    assert reading.baseline_ready
    assert reading.risk is not None
    assert reading.risk.valid_weight == 0.75
    assert reading.risk.contributions["HRV_suppression"] == 0
    assert reading.risk.contributions["ActivityLoad"] == 0
    assert ErrorCode.E104 in reading.risk.active_errors


def test_hardware_profile_uses_four_available_signals_for_high_risk():
    adapter = HardwareRiskAdapter(HARDWARE_CONFIG)
    for sequence in range(30):
        adapter.update(_packet(sequence), sequence * 1_000)

    reading = adapter.update(
        _packet(30, bpm=160, skin_c=38.0, gsr_diff=500, air_c=38.0, humidity=90.0),
        30_000,
    )
    assert reading.risk is not None
    assert reading.risk.risk_index >= 90
    assert reading.risk.valid_weight == 0.75


def test_missing_dht_excludes_environment_feature_and_enters_limited_mode():
    adapter = HardwareRiskAdapter(HARDWARE_CONFIG)
    for sequence in range(30):
        adapter.update(_packet(sequence, flags=0b1001), sequence * 1_000)

    reading = adapter.update(_packet(30, flags=0b1001), 30_000)
    assert reading.risk is not None
    assert reading.risk.valid_weight == 0.55
    assert reading.risk.sensor_limited is True
    assert ErrorCode.E105 in reading.risk.active_errors
