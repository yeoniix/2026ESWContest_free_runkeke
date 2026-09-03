"""실제 Heltec LoRa 35-byte TelemetryPacket 디코더.

Version 2 packet semantics:
    airTemp_x10:
        high byte = DeviceStateCode
        low byte  = BeltCauseCode

    humidity_x10:
        high byte = CoolingStageCode
        low byte  = RiskIndex

DeviceState:
    BOOT / BASELINE / NORMAL / CAUTION /
    COOLING / EMERGENCY / SENSOR_CHECK

CoolingStage:
    C0 / C1 / C2 / C3 / C4
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum, IntFlag


TELEMETRY_MAGIC = 0xA55A

TELEMETRY_PACKET = struct.Struct(
    "<HBBHBhHhIhHiiBhHB"
)


class DeviceStateCode(IntEnum):
    BOOT = 0
    BASELINE = 1
    NORMAL = 2
    CAUTION = 3
    COOLING = 4
    EMERGENCY = 5
    SENSOR_CHECK = 6


class CoolingStageCode(IntEnum):
    C0 = 0
    C1 = 1
    C2 = 2
    C3 = 3
    C4 = 4


class BeltCauseCode(IntEnum):
    NONE = 0
    HR_HIGH = 1
    HR_CHANGE = 2
    TEMP_UP = 3
    GSR_UP = 4
    HOT_ENV = 5
    ACTIVE = 6
    SENSOR = 7


class TelemetryFlags(IntFlag):
    GLOVE_DATA = 1 << 0
    DHT_DATA = 1 << 1
    GPS_FIX = 1 << 2
    FINGER_DETECTED = 1 << 3
    EMERGENCY = 1 << 4
    FAN_ON = 1 << 5


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

    state_cause_word: int
    stage_risk_word: int

    latitude: float
    longitude: float
    satellites: int
    altitude_m: float
    speed_kmh: float

    flags: TelemetryFlags

    @property
    def glove_available(self) -> bool:
        return bool(
            self.flags &
            TelemetryFlags.GLOVE_DATA
        )

    @property
    def finger_detected(self) -> bool:
        return bool(
            self.flags &
            TelemetryFlags.FINGER_DETECTED
        )

    @property
    def sensor_ready(self) -> bool:
        return (
            self.glove_available
            and self.finger_detected
            and self.bpm > 0
        )

    @property
    def dht_available(self) -> bool:
        return bool(
            self.flags &
            TelemetryFlags.DHT_DATA
        )

    @property
    def gps_fix(self) -> bool:
        return bool(
            self.flags &
            TelemetryFlags.GPS_FIX
        )

    @property
    def emergency_active(self) -> bool:
        return bool(
            self.flags &
            TelemetryFlags.EMERGENCY
        )

    @property
    def fan_on(self) -> bool:
        return bool(
            self.flags &
            TelemetryFlags.FAN_ON
        )

    @property
    def device_state(
        self,
    ) -> DeviceStateCode | None:
        raw = (
            self.state_cause_word >> 8
        ) & 0xFF

        try:
            return DeviceStateCode(raw)
        except ValueError:
            return None

    @property
    def belt_state(
        self,
    ) -> DeviceStateCode | None:
        """기존 호출부 호환용. device_state와 동일."""
        return self.device_state

    @property
    def belt_cause(
        self,
    ) -> BeltCauseCode | None:
        raw = (
            self.state_cause_word
            & 0xFF
        )

        try:
            return BeltCauseCode(raw)
        except ValueError:
            return None

    @property
    def cooling_stage(
        self,
    ) -> CoolingStageCode | None:
        raw = (
            self.stage_risk_word >> 8
        ) & 0xFF

        try:
            return CoolingStageCode(raw)
        except ValueError:
            return None

    @property
    def belt_risk_index(
        self,
    ) -> int | None:
        raw = (
            self.stage_risk_word
            & 0xFF
        )

        if 0 <= raw <= 100:
            return raw

        if raw == 255:
            return 255

        return None

    @property
    def air_temp_c(self) -> None:
        # Version2 실물 packet에서는 DHT 필드를 사용하지 않는다.
        return None

    @property
    def humidity_percent(self) -> None:
        return None


def decode_glove_telemetry(
    payload: bytes,
) -> GloveTelemetryPacket:

    if len(payload) != TELEMETRY_PACKET.size:
        raise ValueError(
            "TelemetryPacket must be "
            f"{TELEMETRY_PACKET.size} bytes, "
            f"got {len(payload)}"
        )

    (
        magic,
        version,
        node_id,
        sequence,
        bpm,
        skin_x100,
        gsr,
        gsr_diff,
        ir,
        state_cause_raw,
        stage_risk_raw,
        latitude_e7,
        longitude_e7,
        satellites,
        altitude_dm,
        speed_x10,
        raw_flags,
    ) = TELEMETRY_PACKET.unpack(
        payload
    )

    if magic != TELEMETRY_MAGIC:
        raise ValueError(
            "invalid TelemetryPacket magic: "
            f"0x{magic:04X}"
        )

    return GloveTelemetryPacket(
        version=version,
        node_id=node_id,
        sequence=sequence,
        bpm=bpm,
        skin_temp_c=skin_x100 / 100.0,
        gsr=gsr,
        gsr_diff=gsr_diff,
        ir=ir,
        state_cause_word=(
            state_cause_raw & 0xFFFF
        ),
        stage_risk_word=stage_risk_raw,
        latitude=(
            latitude_e7 / 10_000_000
        ),
        longitude=(
            longitude_e7 / 10_000_000
        ),
        satellites=satellites,
        altitude_m=altitude_dm / 10.0,
        speed_kmh=speed_x10 / 10.0,
        flags=TelemetryFlags(raw_flags),
    )
