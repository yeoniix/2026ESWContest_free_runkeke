from common.glove_packets import TELEMETRY_PACKET, TelemetryFlags, decode_glove_telemetry


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
