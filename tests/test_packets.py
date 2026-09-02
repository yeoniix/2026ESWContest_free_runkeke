import pytest

from heatsentry.common.packets import (
    AckResult,
    BeltStatus,
    CoolAck,
    CoolCmd,
    CoolReason,
    DeviceState,
    HsStatus,
    PacketError,
)


def test_hs_status_round_trip():
    status = HsStatus(
        monotonic_ms=184225,
        sequence=1842,
        state=DeviceState.COOLING,
        risk_index=88,
        sensor_quality=82,
        flags=0b1000,
        heart_rate_bpm=148,
        skin_temp_c=35.72,
        eda_norm=0.55,
        battery_percent=76,
    )
    packet = status.encode()
    assert len(packet) == 24  # SIID 표5
    decoded = HsStatus.decode(packet)
    assert decoded.risk_index == 88
    assert decoded.state == DeviceState.COOLING
    assert decoded.heart_rate_bpm == 148
    assert decoded.skin_temp_c == pytest.approx(35.72)
    assert decoded.eda_norm == pytest.approx(0.55)


def test_hs_status_crc_corruption_detected():
    status = HsStatus(
        monotonic_ms=1, sequence=1, state=DeviceState.NORMAL, risk_index=10,
        sensor_quality=100, flags=0, heart_rate_bpm=80, skin_temp_c=36.0,
        eda_norm=0.1, battery_percent=100,
    )
    packet = bytearray(status.encode())
    packet[5] ^= 0xFF  # risk_index 바이트 변조
    with pytest.raises(PacketError):
        HsStatus.decode(bytes(packet))


def test_hs_status_protocol_version_mismatch():
    status = HsStatus(
        monotonic_ms=1, sequence=1, state=DeviceState.NORMAL, risk_index=10,
        sensor_quality=100, flags=0, heart_rate_bpm=80, skin_temp_c=36.0,
        eda_norm=0.1, battery_percent=100,
    )
    packet = bytearray(status.encode())
    packet[0] = 99
    # protocol_version이 바뀌면 CRC도 같이 깨지므로(같은 바이트가 CRC 입력에도
    # 포함) 새 CRC를 다시 계산해 "버전만 다른" 상황을 재현한다.
    from heatsentry.common.crc16 import append_crc16
    packet = append_crc16(bytes(packet[:22]))
    with pytest.raises(PacketError):
        HsStatus.decode(packet)


def test_cool_cmd_round_trip():
    cmd = CoolCmd(level=60, duration_s=30, cmd_id=7, sequence=3, reason=CoolReason.RISK_FSM)
    packet = cmd.encode()
    assert len(packet) == 12  # SIID p5 COOL_CMD payload
    decoded = CoolCmd.decode(packet)
    assert decoded.level == 60
    assert decoded.cmd_id == 7
    assert decoded.reason == CoolReason.RISK_FSM


def test_cool_ack_round_trip():
    ack = CoolAck(
        cmd_id=7, sequence=3, result=AckResult.OK, actual_pwm=60,
        current_ma=284, belt_temp_centic=3200, error_bits=0,
    )
    packet = ack.encode()
    assert len(packet) == 16  # SIID p5 COOL_ACK payload
    decoded = CoolAck.decode(packet)
    assert decoded.actual_pwm == 60
    assert decoded.current_ma == 284
    assert decoded.result == AckResult.OK


def test_belt_status_round_trip():
    status = BeltStatus(
        monotonic_ms=1000, sequence=5, battery_percent=68, voltage_mv=7400,
        belt_temp_centic=3150, fan_pwm_percent=60, fan_rpm=4200, current_ma=284,
        error_bits=0,
    )
    packet = status.encode()
    assert len(packet) == 20  # SIID 표4
    decoded = BeltStatus.decode(packet)
    assert decoded.fan_pwm_percent == 60
    assert decoded.fan_rpm == 4200


def test_version_constants_have_a_single_source():
    """같은 버전을 두 곳에 적어 두면 조용히 갈라진다.

    실제로 heatsentry/common/__init__.py에 RISK_CONFIG_VERSION이 0.3.0으로
    복제돼 있어, risk_config.py를 0.4.0으로 올린 뒤에도 옛 값이 남아 있었다.
    """
    import heatsentry.common as common
    from heatsentry.algorithm.risk_config import RISK_CONFIG_VERSION
    from heatsentry.common.packets import PROTOCOL_VERSION

    assert common.PROTOCOL_VERSION is PROTOCOL_VERSION
    assert not hasattr(common, "RISK_CONFIG_VERSION"), (
        "RISK_CONFIG_VERSION은 algorithm/risk_config.py 한 곳에만 있어야 한다"
    )
    assert RISK_CONFIG_VERSION == "0.4.0"
