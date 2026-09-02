"""현재 Heltec LoRa 하드웨어의 35바이트 TelemetryPacket 디코더.

바이트 레이아웃의 1차 소스는 firmware/belt_heltec/belt_heltec.ino의
``struct TelemetryPacket``이다. 이 파일은 그 구조체를 그대로 푼다.

현재 펌웨어에서는 DHT를 사용하지 않으므로 기존 DHT 필드 두 개를 재활용한다.

    airTemp_x10   = (state << 8) | cause
    humidity_x10 = belt RiskIndex

- state / cause는 장갑 OLED에 보내는 DisplayPacket과 같은 코드 체계다.
- belt RiskIndex는 벨트가 실제 팬/OLED FSM에 사용한 0~100 위험도다.
- RiskIndex 255는 BOOT / BASELINE / SENSOR_CHECK 등 아직 계산 불가 상태다.
- flags의 DHT_DATA 비트는 현재 펌웨어에서는 세우지 않는다.

DHT_DATA 플래그가 켜져 있는 구형 패킷은 기존 의미(기온/습도)로 해석한다.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum, IntFlag


TELEMETRY_MAGIC = 0xA55A

# C++ packed TelemetryPacket과 정확히 동일한 35 bytes
#
# uint16_t magic
# uint8_t  version
# uint8_t  nodeId
# uint16_t seq
# uint8_t  bpm
# int16_t  skinTemp_x100
# uint16_t gsr
# int16_t  gsrDiff
# uint32_t ir
# int16_t  airTemp_x10
# uint16_t humidity_x10
# int32_t  latitude_e7
# int32_t  longitude_e7
# uint8_t  satellites
# int16_t  altitude_dm
# uint16_t speed_x10
# uint8_t  flags
TELEMETRY_PACKET = struct.Struct("<HBBHBhHhIhHiiBhHB")


class BeltStateCode(IntEnum):
    """벨트가 판정해 장갑 OLED와 관제로 보내는 상태 코드."""

    BOOT = 0
    BASELINE = 1
    NORMAL = 2
    CAUTION = 3
    COOLING_50 = 4
    DANGER = 5
    EMERGENCY = 6
    SENSOR_CHECK = 7


class BeltCauseCode(IntEnum):
    """벨트가 고른 위험 판단의 주 원인."""

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

    # airTemp_x10 자리의 16비트 원본.
    # DHT_DATA=0인 현재 펌웨어에서는 high byte=state, low byte=cause.
    belt_status_word: int

    # DHT_DATA=0인 현재 펌웨어에서는 Belt RiskIndex(0~100, 255=invalid).
    humidity_raw_x10: int

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

    # ------------------------------------------------------------------
    # 구형 DHT 패킷 해석
    # ------------------------------------------------------------------
    @property
    def air_temp_c(self) -> float | None:
        """DHT_DATA 플래그가 있을 때만 유효한 환경 온도."""
        return self.belt_status_word / 10.0 if self.dht_available else None

    @property
    def humidity_percent(self) -> float | None:
        """DHT_DATA 플래그가 있을 때만 유효한 환경 습도."""
        return self.humidity_raw_x10 / 10.0 if self.dht_available else None

    # ------------------------------------------------------------------
    # 현재 Belt 펌웨어 해석
    # ------------------------------------------------------------------
    @property
    def belt_risk_index(self) -> int | None:
        """벨트가 실제 FSM에 사용한 RiskIndex.

        현재 DHT 미탑재 펌웨어에서는 humidity_x10 자리를 재활용한다.

        0~100 : 유효한 RiskIndex
        255   : BOOT / BASELINE / SENSOR_CHECK 등 아직 계산 불가
        None  : DHT 패킷이거나 정의되지 않은 값
        """
        if self.dht_available:
            return None

        raw = int(self.humidity_raw_x10)

        if 0 <= raw <= 100:
            return raw

        if raw == 255:
            return 255

        return None

    @property
    def belt_state(self) -> BeltStateCode | None:
        """벨트 펌웨어가 실제로 내린 상태."""
        if self.dht_available:
            return None

        raw = (self.belt_status_word >> 8) & 0xFF

        try:
            return BeltStateCode(raw)
        except ValueError:
            return None

    @property
    def belt_cause(self) -> BeltCauseCode | None:
        """벨트가 실제로 고른 주 원인."""
        if self.dht_available:
            return None

        raw = self.belt_status_word & 0xFF

        try:
            return BeltCauseCode(raw)
        except ValueError:
            return None


def decode_glove_telemetry(payload: bytes) -> GloveTelemetryPacket:
    """35바이트 LoRa payload를 GloveTelemetryPacket으로 디코딩한다."""

    if len(payload) != TELEMETRY_PACKET.size:
        raise ValueError(
            f"TelemetryPacket must be {TELEMETRY_PACKET.size} bytes, "
            f"got {len(payload)}"
        )

    values = TELEMETRY_PACKET.unpack(payload)

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
        air_x10,
        humidity_x10,
        latitude_e7,
        longitude_e7,
        satellites,
        altitude_dm,
        speed_x10,
        raw_flags,
    ) = values

    if magic != TELEMETRY_MAGIC:
        raise ValueError(
            f"invalid TelemetryPacket magic: 0x{magic:04X}"
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

        # C++에서는 int16_t지만 현재 펌웨어는 상태/원인 16bit word로 사용.
        belt_status_word=air_x10 & 0xFFFF,

        humidity_raw_x10=humidity_x10,

        latitude=latitude_e7 / 10_000_000,
        longitude=longitude_e7 / 10_000_000,
        satellites=satellites,
        altitude_m=altitude_dm / 10.0,
        speed_kmh=speed_x10 / 10.0,
        flags=TelemetryFlags(raw_flags),
    )
