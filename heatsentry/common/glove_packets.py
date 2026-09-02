"""현재 Heltec LoRa 하드웨어의 35바이트 TelemetryPacket 디코더.

바이트 레이아웃의 1차 소스는 firmware/belt_heltec/belt_heltec.ino의
``struct TelemetryPacket``이다. 이 파일은 그 구조체를 그대로 푼다.

주의 — ``airTemp_x10`` 필드는 용도가 바뀌었다. 벨트에서 DHT 온습도 센서가
동작하지 않아 제거되면서, 벨트 펌웨어는 이 16비트 자리를 자신이 판정한
상태·원인 코드를 관제로 올리는 데 재활용한다:

    airTemp_x10 = (state << 8) | cause        # DisplayPacket과 같은 코드 체계
    humidity_x10 = 0                          # 미사용
    flags의 DHT_DATA 비트는 세우지 않는다

따라서 DHT_DATA 플래그가 이 자리의 의미를 결정한다. 플래그가 서 있으면
옛 정의대로 기온/습도이고, 서 있지 않으면(현재 펌웨어) 벨트 상태·원인이다.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum, IntFlag

TELEMETRY_MAGIC = 0xA55A
TELEMETRY_PACKET = struct.Struct("<HBBHBhHhIhHiiBhHB")


class BeltStateCode(IntEnum):
    """벨트가 판정해 장갑 OLED와 관제로 보내는 상태 코드.

    firmware/glove_esp32/display_protocol.h의 ``enum StateCode``와 값이 같아야
    한다(tests/test_display_protocol_sync.py가 두 정의의 일치를 검사한다).
    이 코드 체계는 파이썬 FSM의 DeviceState와 단계 구분이 다르다 —
    벨트는 자체 임계값으로 판정하고, 파이썬은 RiskIndex v0.3으로 판정한다.
    """

    BOOT = 0
    BASELINE = 1
    NORMAL = 2
    CAUTION = 3
    COOLING_50 = 4
    DANGER = 5
    EMERGENCY = 6
    SENSOR_CHECK = 7


class BeltCauseCode(IntEnum):
    """벨트가 고른 위험 판단의 주 원인. display_protocol.h의 ``enum CauseCode``."""

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
    belt_status_word: int  # airTemp_x10 자리의 16비트 원본. 해석은 dht_available이 정한다
    humidity_raw_x10: int  # 현재 펌웨어에서는 항상 0
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

    @property
    def dht_available(self) -> bool:
        return bool(self.flags & TelemetryFlags.DHT_DATA)

    @property
    def gps_fix(self) -> bool:
        return bool(self.flags & TelemetryFlags.GPS_FIX)

    @property
    def emergency_active(self) -> bool:
        return bool(self.flags & TelemetryFlags.EMERGENCY)

    @property
    def fan_on(self) -> bool:
        return bool(self.flags & TelemetryFlags.FAN_ON)

    # --- airTemp_x10 자리의 두 가지 해석 -----------------------------------
    # DHT가 살아 있던 시절의 정의(기온/습도)와 현재 펌웨어의 정의(상태/원인).
    # 어느 쪽인지는 DHT_DATA 플래그가 결정하므로, 아닌 쪽은 None을 준다.

    @property
    def air_temp_c(self) -> float | None:
        """DHT가 붙어 있을 때만 유효한 기온. 현재 하드웨어에서는 항상 None."""
        return self.belt_status_word / 10.0 if self.dht_available else None

    @property
    def humidity_percent(self) -> float | None:
        """DHT가 붙어 있을 때만 유효한 습도. 현재 하드웨어에서는 항상 None."""
        return self.humidity_raw_x10 / 10.0 if self.dht_available else None

    @property
    def belt_state(self) -> BeltStateCode | None:
        """벨트 펌웨어가 자체 임계값으로 판정한 상태. DHT가 붙으면 None."""
        if self.dht_available:
            return None
        raw = (self.belt_status_word >> 8) & 0xFF
        try:
            return BeltStateCode(raw)
        except ValueError:
            return None

    @property
    def belt_cause(self) -> BeltCauseCode | None:
        """벨트가 고른 주 원인 코드. DHT가 붙으면 None."""
        if self.dht_available:
            return None
        try:
            return BeltCauseCode(self.belt_status_word & 0xFF)
        except ValueError:
            return None


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
        # 벨트가 int16으로 보내지만 상태·원인 워드로 쓸 때는 부호가 없다.
        air_x10 & 0xFFFF, humidity_x10, latitude_e7 / 10_000_000,
        longitude_e7 / 10_000_000, satellites, altitude_dm / 10.0,
        speed_x10 / 10.0, TelemetryFlags(raw_flags),
    )
