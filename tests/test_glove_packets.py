import pytest

from heatsentry.common.glove_packets import (
    TELEMETRY_PACKET,
    BeltCauseCode,
    BeltStateCode,
    TelemetryFlags,
    decode_glove_telemetry,
)


def test_decode_hardware_telemetry_packet():
    payload = TELEMETRY_PACKET.pack(
        0xA55A, 1, 1, 41, 82, 2901, 2392, -7, 1008,
        243, 630, 375_666_789, 126_978_456, 8, 385, 12, 0b1111,
    )
    assert len(payload) == 35
    packet = decode_glove_telemetry(payload)
    assert packet.sequence == 41
    assert packet.skin_temp_c == 29.01
    assert packet.gsr_diff == -7
    assert packet.sensor_ready
    assert packet.flags & TelemetryFlags.GPS_FIX


def test_rejects_wrong_size():
    try:
        decode_glove_telemetry(b"short")
        assert False, "expected invalid size"
    except ValueError as error:
        assert "35 bytes" in str(error)


# --- 벨트 상태·원인 전송 (airTemp_x10 재활용) ------------------------------
# firmware/belt_heltec/belt_heltec.ino의 makeTelemetryPacket():
#   txData.airTemp_x10 = (state << 8) | cause
# DHT가 제거되면서 이 자리를 벨트 판정 전송에 쓴다. DHT_DATA 플래그가
# 이 16비트를 기온으로 읽을지 상태/원인으로 읽을지 결정한다.


def _packet(*, status_word: int, humidity_x10: int = 0, flags: TelemetryFlags) -> bytes:
    return TELEMETRY_PACKET.pack(
        0xA55A, 1, 1, 7, 120, 3680, 800, 40, 50_000,
        status_word, humidity_x10, 375_000_000, 1_270_000_000, 6, 300, 0, flags,
    )


def test_belt_state_and_cause_decode_when_dht_absent():
    packet = decode_glove_telemetry(
        _packet(
            status_word=(BeltStateCode.DANGER << 8) | BeltCauseCode.TEMP_UP,
            flags=TelemetryFlags.GLOVE_DATA | TelemetryFlags.FINGER_DETECTED,
        )
    )
    assert packet.belt_state is BeltStateCode.DANGER
    assert packet.belt_cause is BeltCauseCode.TEMP_UP
    # 같은 바이트를 기온으로 읽어서는 안 된다
    assert packet.air_temp_c is None
    assert packet.humidity_percent is None


def test_dht_flag_restores_the_legacy_temperature_reading():
    """DHT가 다시 붙으면 같은 자리를 기온/습도로 읽는다."""
    packet = decode_glove_telemetry(
        _packet(
            status_word=283,  # 28.3도
            humidity_x10=615,
            flags=TelemetryFlags.GLOVE_DATA | TelemetryFlags.DHT_DATA,
        )
    )
    assert packet.air_temp_c == pytest.approx(28.3)
    assert packet.humidity_percent == pytest.approx(61.5)
    assert packet.belt_state is None
    assert packet.belt_cause is None


def test_unknown_state_code_does_not_raise():
    """펌웨어가 새 상태를 추가해도 게이트웨이가 죽지 않아야 한다."""
    packet = decode_glove_telemetry(
        _packet(status_word=(99 << 8) | 0, flags=TelemetryFlags.GLOVE_DATA)
    )
    assert packet.belt_state is None
