"""HeatSentry GATT v2 바이너리 패킷 인코더/디코더.

프로젝트 공통 DeviceState:
    BOOT / BASELINE / NORMAL / CAUTION /
    COOLING / EMERGENCY / SENSOR_CHECK

냉각 강도는 DeviceState와 별도인 C0~C4 단계로 관리한다.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

from heatsentry.common.crc16 import append_crc16, verify_crc16


PROTOCOL_VERSION = 2


class MsgType(IntEnum):
    STATUS = 0x01
    CMD = 0x10
    ACK = 0x11
    BELT_STATUS = 0x12
    SOS_EVENT = 0x13


class DeviceState(IntEnum):
    """프로젝트 전체 공통 DeviceState."""

    BOOT = 0
    BASELINE = 1
    NORMAL = 2
    CAUTION = 3
    COOLING = 4
    EMERGENCY = 5
    SENSOR_CHECK = 6


class StatusFlag(IntEnum):
    FALL = 1 << 0
    SOS = 1 << 1
    SENSOR_LIMITED = 1 << 2
    COOLING = 1 << 3


class PacketError(ValueError):
    pass


def _check_common_header(
    protocol_version: int,
    msg_type: int,
) -> None:
    if protocol_version != PROTOCOL_VERSION:
        raise PacketError(
            "unsupported protocol_version="
            f"{protocol_version} "
            f"(expected {PROTOCOL_VERSION})"
        )


# ---------------------------------------------------------------------------
# HS_STATUS 24B
# ---------------------------------------------------------------------------

_HS_STATUS_HEADER = struct.Struct("<BBHIHBBBB")
_HS_STATUS_WRIST_PAYLOAD = struct.Struct("<BHHBH")


@dataclass
class HsStatus:
    monotonic_ms: int
    sequence: int
    state: DeviceState
    risk_index: int
    sensor_quality: int
    flags: int
    heart_rate_bpm: int
    skin_temp_c: float
    eda_norm: float
    battery_percent: int

    def encode(self) -> bytes:
        payload = _HS_STATUS_WRIST_PAYLOAD.pack(
            min(self.heart_rate_bpm, 255),
            int(round(self.skin_temp_c * 100)) & 0xFFFF,
            int(round(self.eda_norm * 1000)) & 0xFFFF,
            self.battery_percent,
            0,
        )

        header = _HS_STATUS_HEADER.pack(
            PROTOCOL_VERSION,
            MsgType.STATUS,
            len(payload),
            self.monotonic_ms & 0xFFFFFFFF,
            self.sequence & 0xFFFF,
            int(self.state),
            self.risk_index,
            self.sensor_quality,
            self.flags,
        )

        return append_crc16(header + payload)

    @classmethod
    def decode(cls, packet: bytes) -> "HsStatus":
        if len(packet) != 24:
            raise PacketError(
                f"HS_STATUS must be 24 bytes, got {len(packet)}"
            )

        if not verify_crc16(packet):
            raise PacketError("HS_STATUS CRC16 mismatch")

        (
            protocol_version,
            msg_type,
            payload_len,
            monotonic_ms,
            sequence,
            state,
            risk_index,
            sensor_quality,
            flags,
        ) = _HS_STATUS_HEADER.unpack(packet[:14])

        _check_common_header(
            protocol_version,
            msg_type,
        )

        if msg_type != MsgType.STATUS:
            raise PacketError(
                f"unexpected msg_type={msg_type} for HS_STATUS"
            )

        if payload_len != 8:
            raise PacketError(
                f"unexpected payload_len={payload_len} for HS_STATUS"
            )

        (
            hr,
            skin_x100,
            eda_x1000,
            battery,
            _reserved,
        ) = _HS_STATUS_WRIST_PAYLOAD.unpack(
            packet[14:22]
        )

        return cls(
            monotonic_ms=monotonic_ms,
            sequence=sequence,
            state=DeviceState(state),
            risk_index=risk_index,
            sensor_quality=sensor_quality,
            flags=flags,
            heart_rate_bpm=hr,
            skin_temp_c=skin_x100 / 100.0,
            eda_norm=eda_x1000 / 1000.0,
            battery_percent=battery,
        )


# ---------------------------------------------------------------------------
# COOL_CMD 12B
# ---------------------------------------------------------------------------

_COOL_CMD_STRUCT = struct.Struct("<BBHHHBB")


class CoolReason(IntEnum):
    RISK_FSM = 0
    COMMANDER = 1
    TEST = 2
    SAFETY_STOP = 3
    EMERGENCY = 4


class CoolCmdFlag(IntEnum):
    TEST_MODE = 1 << 0
    SOS = 1 << 1


@dataclass
class CoolCmd:
    level: int
    duration_s: int
    cmd_id: int
    sequence: int
    reason: CoolReason
    flags: int = 0

    def encode(self) -> bytes:
        body = _COOL_CMD_STRUCT.pack(
            PROTOCOL_VERSION,
            self.level & 0xFF,
            self.duration_s & 0xFFFF,
            self.cmd_id & 0xFFFF,
            self.sequence & 0xFFFF,
            int(self.reason),
            self.flags & 0xFF,
        )

        return append_crc16(body)

    @classmethod
    def decode(cls, packet: bytes) -> "CoolCmd":
        if len(packet) != 12:
            raise PacketError(
                f"COOL_CMD must be 12 bytes, got {len(packet)}"
            )

        if not verify_crc16(packet):
            raise PacketError(
                "COOL_CMD CRC16 mismatch"
            )

        (
            version,
            level,
            duration_s,
            cmd_id,
            sequence,
            reason,
            flags,
        ) = _COOL_CMD_STRUCT.unpack(
            packet[:10]
        )

        _check_common_header(
            version,
            MsgType.CMD,
        )

        return cls(
            level=level,
            duration_s=duration_s,
            cmd_id=cmd_id,
            sequence=sequence,
            reason=CoolReason(reason),
            flags=flags,
        )


# ---------------------------------------------------------------------------
# COOL_ACK 16B
# ---------------------------------------------------------------------------

_COOL_ACK_STRUCT = struct.Struct("<HHBBHhHH")


class AckResult(IntEnum):
    OK = 0
    REJECTED_SAFETY = 1
    IDEMPOTENT_REPEAT = 2


@dataclass
class CoolAck:
    cmd_id: int
    sequence: int
    result: AckResult
    actual_pwm: int
    current_ma: int
    belt_temp_centic: int
    error_bits: int

    def encode(self) -> bytes:
        body = _COOL_ACK_STRUCT.pack(
            self.cmd_id & 0xFFFF,
            self.sequence & 0xFFFF,
            int(self.result),
            self.actual_pwm & 0xFF,
            self.current_ma & 0xFFFF,
            self.belt_temp_centic,
            self.error_bits & 0xFFFF,
            0,
        )

        return append_crc16(body)

    @classmethod
    def decode(cls, packet: bytes) -> "CoolAck":
        if len(packet) != 16:
            raise PacketError(
                f"COOL_ACK must be 16 bytes, got {len(packet)}"
            )

        if not verify_crc16(packet):
            raise PacketError(
                "COOL_ACK CRC16 mismatch"
            )

        (
            cmd_id,
            sequence,
            result,
            actual_pwm,
            current_ma,
            belt_temp_centic,
            error_bits,
            _reserved,
        ) = _COOL_ACK_STRUCT.unpack(
            packet[:14]
        )

        return cls(
            cmd_id=cmd_id,
            sequence=sequence,
            result=AckResult(result),
            actual_pwm=actual_pwm,
            current_ma=current_ma,
            belt_temp_centic=belt_temp_centic,
            error_bits=error_bits,
        )


# ---------------------------------------------------------------------------
# BELT_STATUS 20B
# ---------------------------------------------------------------------------

_BELT_STATUS_STRUCT = struct.Struct(
    "<BHIBHhBHHB"
)


@dataclass
class BeltStatus:
    monotonic_ms: int
    sequence: int
    battery_percent: int
    voltage_mv: int
    belt_temp_centic: int
    fan_pwm_percent: int
    fan_rpm: int
    current_ma: int
    error_bits: int

    def encode(self) -> bytes:
        body = _BELT_STATUS_STRUCT.pack(
            PROTOCOL_VERSION,
            self.sequence & 0xFFFF,
            self.monotonic_ms & 0xFFFFFFFF,
            self.battery_percent & 0xFF,
            self.voltage_mv & 0xFFFF,
            self.belt_temp_centic,
            self.fan_pwm_percent & 0xFF,
            self.fan_rpm & 0xFFFF,
            self.current_ma & 0xFFFF,
            self.error_bits & 0xFF,
        )

        return append_crc16(body)

    @classmethod
    def decode(cls, packet: bytes) -> "BeltStatus":
        if len(packet) != 20:
            raise PacketError(
                f"BELT_STATUS must be 20 bytes, got {len(packet)}"
            )

        if not verify_crc16(packet):
            raise PacketError(
                "BELT_STATUS CRC16 mismatch"
            )

        (
            version,
            sequence,
            monotonic_ms,
            battery_percent,
            voltage_mv,
            belt_temp_centic,
            fan_pwm_percent,
            fan_rpm,
            current_ma,
            error_bits,
        ) = _BELT_STATUS_STRUCT.unpack(
            packet[:18]
        )

        _check_common_header(
            version,
            MsgType.BELT_STATUS,
        )

        return cls(
            monotonic_ms=monotonic_ms,
            sequence=sequence,
            battery_percent=battery_percent,
            voltage_mv=voltage_mv,
            belt_temp_centic=belt_temp_centic,
            fan_pwm_percent=fan_pwm_percent,
            fan_rpm=fan_rpm,
            current_ma=current_ma,
            error_bits=error_bits,
        )
