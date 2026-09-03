"""LoRa 수신 경로: 벨트 판정을 그대로 관제로 옮기는지 검증한다.

실물 경로에서 판정 주체는 벨트 하나다. 벨트는 LoRa가 끊겨도 팬과 장갑 OLED를
스스로 구동해야 하므로 자체 위험점수·상태기계를 갖고, 게이트웨이는 그 결론을
다시 계산하지 않고 전달만 한다. 전달 과정에서 값이 바뀌거나, 벨트가 보낸 값이
해석 불가일 때 조용히 넘어가지 않는 것이 이 파일의 관심사다.
"""

import pytest

from heatsentry.common.glove_packets import (
    TELEMETRY_PACKET,
    BeltCauseCode,
    CoolingStageCode,
    DeviceStateCode,
    TelemetryFlags,
)
from heatsentry.server.lora_adapter import LoRaTelemetryAdapter

WORN = TelemetryFlags.GLOVE_DATA | TelemetryFlags.FINGER_DETECTED


def _payload(
    sequence: int,
    *,
    bpm: int = 95,
    skin_c: float = 36.5,
    belt_state: int = DeviceStateCode.NORMAL,
    belt_cause: int = BeltCauseCode.NONE,
    cooling_stage: int = CoolingStageCode.C0,
    belt_risk: int = 20,
    flags: int = WORN,
) -> bytes:
    return TELEMETRY_PACKET.pack(
        0xA55A, 1, 1, sequence, bpm, round(skin_c * 100), 800, 20, 50_000,
        (belt_state << 8) | belt_cause,
        (cooling_stage << 8) | belt_risk,
        375_000_000, 1_270_000_000, 7, 300, 0, flags,
    )


def test_belt_verdict_is_forwarded_verbatim():
    """벨트가 팬을 돌린 근거가 그대로 관제에 올라와야 한다."""
    adapter = LoRaTelemetryAdapter()
    telemetry = adapter.convert(
        _payload(
            1, bpm=178, skin_c=38.9,
            belt_state=DeviceStateCode.COOLING,
            belt_cause=BeltCauseCode.TEMP_UP,
            cooling_stage=CoolingStageCode.C2,
            belt_risk=93,
        ),
        monotonic_ms=1_000,
    )
    assert telemetry.state == "COOLING"
    assert telemetry.risk_index == 93
    assert telemetry.cooling.requested == int(CoolingStageCode.C2)
    assert telemetry.raw.belt_state == "COOLING"
    assert telemetry.raw.belt_cause == "TEMP_UP"


def test_gateway_does_not_recompute_the_risk_index():
    """게이트웨이가 재판정하면 현장에서 실제로 쓰인 값과 갈라진다."""
    adapter = LoRaTelemetryAdapter()
    telemetry = adapter.convert(
        _payload(1, bpm=95, skin_c=36.5,
                 belt_state=DeviceStateCode.CAUTION, belt_risk=61),
        monotonic_ms=1_000,
    )
    assert telemetry.risk_index == 61
    assert telemetry.state == "CAUTION"


def test_unknown_state_falls_back_to_sensor_check():
    adapter = LoRaTelemetryAdapter()
    telemetry = adapter.convert(_payload(1, belt_state=99), monotonic_ms=1_000)
    assert telemetry.state == "SENSOR_CHECK"
    assert "STATE_INVALID" in telemetry.active_errors


def test_out_of_range_risk_is_reported_not_guessed():
    adapter = LoRaTelemetryAdapter()
    telemetry = adapter.convert(_payload(1, belt_risk=200), monotonic_ms=1_000)
    assert telemetry.risk_index == 255
    assert "RISK_INVALID" in telemetry.active_errors


def test_unknown_cooling_stage_is_reported():
    adapter = LoRaTelemetryAdapter()
    telemetry = adapter.convert(_payload(1, cooling_stage=9), monotonic_ms=1_000)
    assert telemetry.cooling.requested == 0
    assert "COOLING_STAGE_INVALID" in telemetry.active_errors


def test_absent_dht_is_not_reported_as_an_error():
    """DHT 미탑재는 설계이지 오류가 아니다. 매 초 뜨는 경고가 되면 안 된다."""
    adapter = LoRaTelemetryAdapter()
    telemetry = adapter.convert(_payload(1), monotonic_ms=1_000)
    assert telemetry.active_errors == []
    assert telemetry.raw.air_temp_c is None
    assert telemetry.raw.humidity_percent is None


def test_repurposed_field_is_never_shown_as_a_temperature():
    """상태/원인 워드를 기온으로 잘못 읽으면 관제에 엉뚱한 온도가 뜬다."""
    adapter = LoRaTelemetryAdapter()
    telemetry = adapter.convert(
        _payload(1, belt_state=DeviceStateCode.COOLING,
                 belt_cause=BeltCauseCode.HR_HIGH,
                 cooling_stage=CoolingStageCode.C1, belt_risk=82),
        monotonic_ms=1_000,
    )
    assert telemetry.raw.air_temp_c is None
    assert telemetry.raw.belt_state == "COOLING"


def test_emergency_is_carried_through():
    adapter = LoRaTelemetryAdapter()
    telemetry = adapter.convert(
        _payload(1, flags=WORN | TelemetryFlags.EMERGENCY,
                 belt_state=DeviceStateCode.EMERGENCY,
                 cooling_stage=CoolingStageCode.C4, belt_risk=99),
        monotonic_ms=1_000,
    )
    assert telemetry.state == "EMERGENCY"
    assert telemetry.cooling.requested == 4


def test_valid_risk_yields_full_valid_weight():
    adapter = LoRaTelemetryAdapter()
    telemetry = adapter.convert(_payload(1), monotonic_ms=1_000)
    assert telemetry.valid_weight == pytest.approx(1.0)
    assert "SENSOR_LIMITED" not in telemetry.active_errors
