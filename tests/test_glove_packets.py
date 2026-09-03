from heatsentry.common.glove_packets import (
    TELEMETRY_PACKET,
    BeltCauseCode,
    CoolingStageCode,
    DeviceStateCode,
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


# --- 벨트 판정 전송 --------------------------------------------------------
# DHT 제거로 비게 된 두 16비트 자리를 벨트 판정 전송에 쓴다.
#   state_cause_word = (state << 8) | cause
#   stage_risk_word  = (cooling_stage << 8) | risk_index


def _packet(
    *,
    state_cause_word: int,
    stage_risk_word: int = 0,
    flags: TelemetryFlags,
) -> bytes:
    return TELEMETRY_PACKET.pack(
        0xA55A, 1, 1, 7, 120, 3680, 800, 40, 50_000,
        state_cause_word, stage_risk_word,
        375_000_000, 1_270_000_000, 6, 300, 0, flags,
    )


def test_belt_state_and_cause_decode():
    packet = decode_glove_telemetry(
        _packet(
            state_cause_word=(DeviceStateCode.COOLING << 8) | BeltCauseCode.TEMP_UP,
            flags=TelemetryFlags.GLOVE_DATA | TelemetryFlags.FINGER_DETECTED,
        )
    )
    assert packet.device_state is DeviceStateCode.COOLING
    assert packet.belt_state is packet.device_state  # 호환 별칭
    assert packet.belt_cause is BeltCauseCode.TEMP_UP
    # DHT는 하드웨어에서 제거됐다 — 같은 바이트를 기온으로 읽어서는 안 된다
    assert packet.air_temp_c is None
    assert packet.humidity_percent is None


def test_cooling_stage_and_belt_risk_decode():
    """벨트가 판정한 냉각 단계와 위험도가 같은 패킷으로 올라온다."""
    packet = decode_glove_telemetry(
        _packet(
            state_cause_word=(DeviceStateCode.COOLING << 8) | BeltCauseCode.HR_HIGH,
            stage_risk_word=(CoolingStageCode.C2 << 8) | 93,
            flags=TelemetryFlags.GLOVE_DATA | TelemetryFlags.FAN_ON,
        )
    )
    assert packet.cooling_stage is CoolingStageCode.C2
    assert packet.belt_risk_index == 93
    assert packet.fan_on


def test_unknown_state_code_does_not_raise():
    """펌웨어가 새 상태를 추가해도 게이트웨이가 죽지 않아야 한다."""
    packet = decode_glove_telemetry(
        _packet(state_cause_word=(99 << 8) | 0, flags=TelemetryFlags.GLOVE_DATA)
    )
    assert packet.device_state is None
    assert packet.belt_state is None


def test_out_of_range_belt_risk_is_rejected():
    packet = decode_glove_telemetry(
        _packet(
            state_cause_word=(DeviceStateCode.NORMAL << 8) | BeltCauseCode.NONE,
            stage_risk_word=(CoolingStageCode.C0 << 8) | 200,
            flags=TelemetryFlags.GLOVE_DATA,
        )
    )
    assert packet.belt_risk_index is None
