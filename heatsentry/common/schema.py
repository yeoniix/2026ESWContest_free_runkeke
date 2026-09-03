"""HeatSentry Gateway schema v2.

DeviceState는 프로젝트 전체에서 아래 7개만 사용한다.

    BOOT
    BASELINE
    NORMAL
    CAUTION
    COOLING
    EMERGENCY
    SENSOR_CHECK

CoolingStage는 TelemetryV2.cooling.requested에 0~4(C0~C4)로 저장한다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


DeviceStateName = Literal[
    "BOOT",
    "BASELINE",
    "NORMAL",
    "CAUTION",
    "COOLING",
    "EMERGENCY",
    "SENSOR_CHECK",
]

ActivityName = Literal[
    "REST",
    "WALK",
    "RUN",
    "CRAWL",
    "STATIC",
    "UNKNOWN",
]

BeltCauseName = Literal[
    "NONE",
    "HR_HIGH",
    "HR_CHANGE",
    "TEMP_UP",
    "GSR_UP",
    "HOT_ENV",
    "ACTIVE",
    "SENSOR",
]


class QualityV2(BaseModel):
    ppg: int = Field(ge=0, le=100)
    skin: int = Field(ge=0, le=100)
    eda: int = Field(ge=0, le=100)
    imu: int = Field(ge=0, le=100)


class SignalsV2(BaseModel):
    hr_bpm: int
    skin_c: float
    activity: ActivityName


class CoolingV2(BaseModel):
    requested: int = Field(
        ge=0,
        le=4,
        description="CoolingStage: 0=C0 ... 4=C4",
    )

    actual_pwm: int = Field(
        ge=0,
        le=100,
    )

    current_ma: int = Field(
        ge=0,
    )


class RawGloveV2(BaseModel):
    """Heltec 35B 패킷의 원시/부가값."""

    gsr: int | None = None
    gsr_diff: int | None = None
    ir: int | None = None

    air_temp_c: float | None = None
    humidity_percent: float | None = None

    finger_detected: bool | None = None
    glove_data: bool | None = None
    dht_data: bool | None = None

    gps_fix: bool | None = None
    latitude: float | None = Field(
        default=None,
        ge=-90,
        le=90,
    )
    longitude: float | None = Field(
        default=None,
        ge=-180,
        le=180,
    )

    # 현장 Belt가 실제로 사용한 공통 DeviceState.
    # 상위 telemetry.state와 동일한 값이어야 한다.
    belt_state: DeviceStateName | None = None

    belt_cause: BeltCauseName | None = None
    belt_fan_on: bool | None = None


class RadioLinkV2(BaseModel):
    rssi_dbm: int | None = None
    snr_db: int | None = None


class TelemetryV2(BaseModel):
    schema_version: Literal["2.0"] = "2.0"

    gateway_utc: str
    device_id: str
    monotonic_ms: int

    state: DeviceStateName

    risk_index: int = Field(
        ge=0,
        le=255,
        description="0~100, 255=invalid",
    )

    valid_weight: float = Field(
        default=1.0,
        ge=0,
        le=1,
    )

    quality: QualityV2
    signals: SignalsV2
    cooling: CoolingV2

    contributions: dict[str, float] = Field(
        default_factory=dict
    )

    active_errors: list[str] = Field(
        default_factory=list
    )

    raw: RawGloveV2 | None = None
    radio: RadioLinkV2 | None = None

    config_version: str = "0.5.0"
    sequence: int


class EventRecord(BaseModel):
    seq: int
    gateway_utc: str
    monotonic_ms: int
    device_id: str
    event_type: str
    reason: str = ""
    payload: dict = Field(
        default_factory=dict
    )
    previous_hash: str | None = None
    event_hash: str | None = None


class CommandAckRecord(BaseModel):
    cmd_id: int
    device_id: str
    requested_level: int
    requested_reason: str
    actual_pwm: int
    current_ma: int
    result: str
    retries: int = 0
    gateway_utc: str


class UserActionRecord(BaseModel):
    role: Literal[
        "observer",
        "commander",
        "tester",
        "maintainer",
    ]

    actor_id: str

    action: Literal[
        "ack",
        "emergency_close",
        "export",
        "config_update",
    ]

    target_id: str
    reason: str = ""
    gateway_utc: str
