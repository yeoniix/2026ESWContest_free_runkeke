"""LoRa 수신 경로: 벨트 판정과 게이트웨이 판정을 나란히 싣는지 검증한다.

벨트 펌웨어는 LoRa가 끊겨도 팬과 장갑 OLED를 스스로 구동해야 하므로 자체
위험점수·상태기계를 갖고 있고, 게이트웨이는 같은 패킷으로 RiskIndex v0.3을
따로 계산한다. 어느 쪽도 상대를 덮어쓰지 않는 것이 이 파일의 관심사다.
"""

import pytest

from heatsentry.common.glove_packets import (
    TELEMETRY_PACKET,
    BeltCauseCode,
    BeltStateCode,
    TelemetryFlags,
)
from heatsentry.server.lora_adapter import LoRaTelemetryAdapter

WORN = TelemetryFlags.GLOVE_DATA | TelemetryFlags.FINGER_DETECTED


def _payload(
    sequence: int,
    *,
    bpm: int = 95,
    skin_c: float = 36.5,
    belt_state: int = BeltStateCode.NORMAL,
    belt_cause: int = BeltCauseCode.NONE,
    flags: int = WORN,
) -> bytes:
    return TELEMETRY_PACKET.pack(
        0xA55A, 1, 1, sequence, bpm, round(skin_c * 100), 800, 20, 50_000,
        (belt_state << 8) | belt_cause, 0,
        375_000_000, 1_270_000_000, 7, 300, 0, flags,
    )


def _settled(adapter: LoRaTelemetryAdapter, ticks: int = 200, **kwargs):
    """기준선이 잡힐 때까지 흘린 뒤 마지막 텔레메트리를 돌려준다."""
    telemetry = None
    for sequence in range(ticks):
        telemetry = adapter.convert(_payload(sequence, **kwargs), monotonic_ms=sequence * 1_000)
    return telemetry


def test_belt_verdict_is_carried_alongside_the_gateway_verdict():
    adapter = LoRaTelemetryAdapter()
    _settled(adapter)
    telemetry = adapter.convert(
        _payload(300, bpm=178, skin_c=38.9,
                 belt_state=BeltStateCode.DANGER, belt_cause=BeltCauseCode.TEMP_UP),
        monotonic_ms=300_000,
    )
    # 벨트가 실제로 한 판정이 그대로 보존된다
    assert telemetry.raw.belt_state == "DANGER"
    assert telemetry.raw.belt_cause == "TEMP_UP"
    # 게이트웨이 판정은 별도로 살아 있다
    assert telemetry.state in {"NORMAL", "WARNING", "COOLING", "EMERGENCY"}
    assert telemetry.risk_index != 255


def test_disagreement_between_the_two_verdicts_is_surfaced():
    """벨트는 DANGER, 게이트웨이는 아직 NORMAL — 감추지 않고 경고로 남긴다."""
    adapter = LoRaTelemetryAdapter()
    _settled(adapter)
    telemetry = adapter.convert(
        _payload(300, bpm=100, skin_c=36.6, belt_state=BeltStateCode.DANGER),
        monotonic_ms=300_000,
    )
    assert telemetry.state == "NORMAL"
    assert "BELT_STATE_MISMATCH" in telemetry.active_errors


def test_agreement_produces_no_mismatch_warning():
    adapter = LoRaTelemetryAdapter()
    telemetry = _settled(adapter)
    assert telemetry.state == "NORMAL"
    assert telemetry.raw.belt_state == "NORMAL"
    assert "BELT_STATE_MISMATCH" not in telemetry.active_errors


def test_absent_dht_is_not_reported_as_an_error():
    """DHT 미탑재는 설계이지 오류가 아니다. 매 초 뜨는 경고가 되면 안 된다."""
    adapter = LoRaTelemetryAdapter()
    telemetry = _settled(adapter)
    assert telemetry.active_errors == []
    assert "DHT_INVALID" not in telemetry.active_errors
    assert telemetry.raw.air_temp_c is None
    assert telemetry.raw.humidity_percent is None


def test_repurposed_field_is_never_shown_as_a_temperature():
    """상태/원인 워드를 기온으로 잘못 읽으면 관제에 엉뚱한 온도가 뜬다."""
    adapter = LoRaTelemetryAdapter()
    telemetry = _settled(adapter, belt_state=BeltStateCode.COOLING_50,
                         belt_cause=BeltCauseCode.HR_HIGH)
    assert telemetry.raw.air_temp_c is None
    assert telemetry.raw.belt_state == "COOLING_50"


def test_manual_sos_still_wins_over_everything():
    adapter = LoRaTelemetryAdapter()
    _settled(adapter)
    telemetry = adapter.convert(
        _payload(300, flags=WORN | TelemetryFlags.EMERGENCY,
                 belt_state=BeltStateCode.EMERGENCY),
        monotonic_ms=300_000,
    )
    assert telemetry.state == "EMERGENCY"
    assert telemetry.cooling.requested == 4


def test_gateway_uses_the_hardware_profile_so_valid_weight_is_meaningful():
    adapter = LoRaTelemetryAdapter()
    telemetry = _settled(adapter)
    assert telemetry.valid_weight == pytest.approx(1.0)
    assert "SENSOR_LIMITED" not in telemetry.active_errors
