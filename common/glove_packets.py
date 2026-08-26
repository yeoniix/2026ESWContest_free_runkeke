"""현재 Heltec LoRa 하드웨어의 35바이트 TelemetryPacket 디코더."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntFlag

TELEMETRY_MAGIC = 0xA55A
TELEMETRY_PACKET = struct.Struct("<HBBHBhHhIhHiiBhHB")


class TelemetryFlags(IntFlag):
    GLOVE_DATA = 1 << 0
    DHT_DATA = 1 << 1
    GPS_FIX = 1 << 2
    FINGER_DETECTED = 1 << 3


@dataclass(frozen=True)
class GloveTelemetryPacket:
    version: int
    node_id: int
    sequence: int
    bpm: int
    skin_temp_c: float
    gsr: int
    gsr_diff: int
    ir: int
    air_temp_c: float
    humidity_percent: float
    latitude: float
    longitude: float
    satellites: int
    altitude_m: float
    speed_kmh: float
    flags: TelemetryFlags

    @property
    def glove_available(self) -> bool:
        return bool(self.flags & TelemetryFlags.GLOVE_DATA)

    @property
    def finger_detected(self) -> bool:
        return bool(self.flags & TelemetryFlags.FINGER_DETECTED)

    @property
    def sensor_ready(self) -> bool:
        return self.glove_available and self.finger_detected and self.bpm > 0


def decode_glove_telemetry(payload: bytes) -> GloveTelemetryPacket:
    if len(payload) != TELEMETRY_PACKET.size:
        raise ValueError(f"TelemetryPacket must be {TELEMETRY_PACKET.size} bytes, got {len(payload)}")
    values = TELEMETRY_PACKET.unpack(payload)
    (
        magic, version, node_id, sequence, bpm, skin_x100, gsr, gsr_diff, ir,
        air_x10, humidity_x10, latitude_e7, longitude_e7, satellites, altitude_dm,
        speed_x10, raw_flags,
    ) = values
    if magic != TELEMETRY_MAGIC:
        raise ValueError(f"invalid TelemetryPacket magic: 0x{magic:04X}")
    return GloveTelemetryPacket(
        version, node_id, sequence, bpm, skin_x100 / 100.0, gsr, gsr_diff, ir,
        air_x10 / 10.0, humidity_x10 / 10.0, latitude_e7 / 10_000_000,
        longitude_e7 / 10_000_000, satellites, altitude_dm / 10.0,
        speed_x10 / 10.0, TelemetryFlags(raw_flags),
    )
