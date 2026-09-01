"""HeatSentry GATT v2 바이너리 패킷 인코더/디코더.

출처: HS-SIID-002 표4 (HeatSentry GATT v2), 표5 (공통 패킷 헤더와 HS_STATUS 24B),
COOL_CMD payload(12B), COOL_ACK payload(16B).

실제 BLE 스택이 없는 개발 단계이므로, firmware/simulator는 이 모듈로 만든 바이트를 그대로
게이트웨이에 보내고 게이트웨이는 이 모듈로 다시 파싱한다. 손목/허리 펌웨어를
C/C++로 옮길 때도 바이트 레이아웃은 이 파일이 기준이 된다(펌웨어측 대응은
firmware/api_contract.md와 firmware/protocol.h 참고).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

from common.crc16 import append_crc16, verify_crc16

PROTOCOL_VERSION = 2


class MsgType(IntEnum):
    STATUS = 0x01
    CMD = 0x10
    ACK = 0x11
    BELT_STATUS = 0x12
    SOS_EVENT = 0x13


class DeviceState(IntEnum):
    """HS_STATUS byte10 state enum. 그림2 통합 상태 전이."""

    BOOT = 0
    BASELINE = 1
    NORMAL = 2
    WARNING = 3
    COOLING = 4
    EMERGENCY = 5
    FAULT = 6


class StatusFlag(IntEnum):
    """HS_STATUS byte13 flags. 표5: fall/sos/limited/cooling."""

    FALL = 1 << 0
    SOS = 1 << 1
    SENSOR_LIMITED = 1 << 2
    COOLING = 1 << 3


class PacketError(ValueError):
    """protocol_version 불일치, payload_len 불일치, CRC 오류 등."""


def _check_common_header(protocol_version: int, msg_type: int) -> None:
    if protocol_version != PROTOCOL_VERSION:
        # 호환성 원칙(SIID p5): 수신 장치는 protocol_version을 먼저 확인한다.
        raise PacketError(
            f"unsupported protocol_version={protocol_version} (expected {PROTOCOL_VERSION})"
        )


# ---------------------------------------------------------------------------
# HS_STATUS (24B) — 손목/허리 -> 게이트웨이/상대 노드
# ---------------------------------------------------------------------------

# 헤더(14B) + payload(8B) + crc16(2B) = 24B
_HS_STATUS_HEADER = struct.Struct("<BBHIHBBBB")  # 14 bytes
# B protocol_version, B msg_type, H payload_len, I monotonic_ms, H sequence,
# B state, B risk_index, B sensor_quality, B flags
_HS_STATUS_WRIST_PAYLOAD = struct.Struct("<BHHBH")  # 8 bytes
# B heart_rate_bpm(0-255), H skin_temp_x100, H eda_norm_x1000, B battery_percent, H reserved


@dataclass
class HsStatus:
    monotonic_ms: int
    sequence: int
    state: DeviceState
    risk_index: int  # 0~100, 255=invalid
    sensor_quality: int  # 0~100
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
            raise PacketError(f"HS_STATUS must be 24 bytes, got {len(packet)}")
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
        _check_common_header(protocol_version, msg_type)
        if msg_type != MsgType.STATUS:
            raise PacketError(f"unexpected msg_type={msg_type} for HS_STATUS")
        if payload_len != 8:
            raise PacketError(f"unexpected payload_len={payload_len} for HS_STATUS")
        hr, skin_x100, eda_x1000, battery, _reserved = _HS_STATUS_WRIST_PAYLOAD.unpack(
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
# COOL_CMD (12B) — 손목 -> 허리
# 0 version | 1 level | 2-3 duration_s | 4-5 cmd_id | 6-7 sequence | 8 reason | 9 flags | 10-11 CRC16
# ---------------------------------------------------------------------------

_COOL_CMD_STRUCT = struct.Struct("<BBHHHBB")  # 10 bytes + crc16(2) = 12


class CoolReason(IntEnum):
    RISK_FSM = 0  # 표7 우선순위 3: RiskIndex 상태 전이
    COMMANDER = 1  # 우선순위 4: 지휘관 수동 냉각
    TEST = 2  # 우선순위 5: 시험 모드
    SAFETY_STOP = 3  # 우선순위 1: 수동 STOP/과전류/저온
    EMERGENCY = 4  # 우선순위 2: 수동 SOS/낙상+무동작+무응답


class CoolCmdFlag(IntEnum):
    TEST_MODE = 1 << 0
    SOS = 1 << 1


@dataclass
class CoolCmd:
    level: int  # fan percent 0/50/100
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
            raise PacketError(f"COOL_CMD must be 12 bytes, got {len(packet)}")
        if not verify_crc16(packet):
            raise PacketError("COOL_CMD CRC16 mismatch")
        version, level, duration_s, cmd_id, sequence, reason, flags = _COOL_CMD_STRUCT.unpack(
            packet[:10]
        )
        _check_common_header(version, MsgType.CMD)
        return cls(
            level=level,
            duration_s=duration_s,
            cmd_id=cmd_id,
            sequence=sequence,
            reason=CoolReason(reason),
            flags=flags,
        )


# ---------------------------------------------------------------------------
# COOL_ACK (16B) — 허리 -> 손목
# cmd_id | sequence | result | actual_pwm | current_mA | belt_temp_centiC | error_bits | reserved | CRC16
# ---------------------------------------------------------------------------

_COOL_ACK_STRUCT = struct.Struct("<HHBBHhHH")  # 14 bytes + crc16(2) = 16


class AckResult(IntEnum):
    OK = 0
    REJECTED_SAFETY = 1  # 과전류/저온 등으로 요청 거부
    IDEMPOTENT_REPEAT = 2  # 동일 cmd_id 재수신 -> 팬 재시작 없이 현재 결과만 ACK


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
            raise PacketError(f"COOL_ACK must be 16 bytes, got {len(packet)}")
        if not verify_crc16(packet):
            raise PacketError("COOL_ACK CRC16 mismatch")
        (
            cmd_id,
            sequence,
            result,
            actual_pwm,
            current_ma,
            belt_temp_centic,
            error_bits,
            _reserved,
        ) = _COOL_ACK_STRUCT.unpack(packet[:14])
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
# BELT_STATUS (20B) — 허리 -> 손목/게이트웨이
# 표4에는 길이만 확정(20B, "배터리·전압·온도·팬")되어 있고 바이트 단위 배치는
# 명시되어 있지 않다. 아래 레이아웃은 통합팀 CR 승인 전까지의 초안이며,
# 실제 배포 전 CR로 고정해야 한다 (SIID p13 "변경요청(CR) 필수 필드" 참고).
# ---------------------------------------------------------------------------

_BELT_STATUS_STRUCT = struct.Struct("<BHIBHhBHHB")  # 18 bytes + crc16(2) = 20
# B protocol_version, H sequence, I monotonic_ms, B battery_percent, H voltage_mv,
# h belt_temp_centiC, B fan_pwm_percent, H fan_rpm, H current_mA, B error_bits(하위 8종만)


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
            raise PacketError(f"BELT_STATUS must be 20 bytes, got {len(packet)}")
        if not verify_crc16(packet):
            raise PacketError("BELT_STATUS CRC16 mismatch")
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
        ) = _BELT_STATUS_STRUCT.unpack(packet[:18])
        _check_common_header(version, MsgType.BELT_STATUS)
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
