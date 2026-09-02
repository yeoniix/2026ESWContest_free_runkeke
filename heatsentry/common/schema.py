"""게이트웨이 데이터 계약 (HS-SIID-002 p6) 및 저장 레코드 스키마 (p9 표9).

이 파일의 TelemetryV2가 ICD 예시 JSON과 1:1로 대응한다:

    {
      "schema_version": "2.0",
      "gateway_utc": "2026-08-08T12:00:00.250Z",
      "device_id": "HS-W-001",
      "monotonic_ms": 184225,
      "state": "COOLING",
      "risk_index": 88,
      "quality": {"ppg": 82, "skin": 96, "eda": 55, "imu": 100},
      "signals": {"hr_bpm": 148, "skin_c": 35.72, "activity": "RUN"},
      "cooling": {"requested": 2, "actual_pwm": 60, "current_ma": 284},
    "config_version": "0.4.0",
      "sequence": 1842
    }
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DeviceStateName = Literal[
    "BOOT", "BASELINE", "NORMAL", "CAUTION", "COOLING", "EMERGENCY", "SENSOR_CHECK"
]
ActivityName = Literal["REST", "WALK", "RUN", "CRAWL", "STATIC", "UNKNOWN"]

# 벨트 펌웨어(firmware/belt_heltec)의 StateCode/CauseCode 이름.
# 값 정의는 heatsentry/common/glove_packets.py의 BeltStateCode/BeltCauseCode.
BeltStateName = Literal[
    "BOOT", "BASELINE", "NORMAL", "CAUTION", "COOLING_50", "DANGER",
    "EMERGENCY", "SENSOR_CHECK",
]
BeltCauseName = Literal[
    "NONE", "HR_HIGH", "HR_CHANGE", "TEMP_UP", "GSR_UP", "HOT_ENV",
    "ACTIVE", "SENSOR",
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
    requested: int = Field(ge=0, le=4, description="냉각 단계 C0~C4")
    actual_pwm: int = Field(ge=0, le=100)
    current_ma: int = Field(ge=0)


class RawGloveV2(BaseModel):
    """실제 Heltec 35B 패킷에서 온 원시값. 상태 계산 전에도 관제에 표시한다."""

    gsr: int | None = None
    gsr_diff: int | None = None
    ir: int | None = None
    air_temp_c: float | None = None       # DHT 미탑재 시 None
    humidity_percent: float | None = None  # DHT 미탑재 시 None
    finger_detected: bool | None = None
    glove_data: bool | None = None
    dht_data: bool | None = None
    gps_fix: bool | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    # 벨트 펌웨어가 자체 임계값으로 내린 판정. 게이트웨이의 RiskIndex v0.3 판정
    # (상위 state 필드)과 기준이 다르므로 덮어쓰지 않고 나란히 싣는다.
    # 현장 장치가 실제로 한 행동은 이쪽이다 — 팬과 장갑 OLED를 이 값이 구동한다.
    belt_state: BeltStateName | None = None
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
    risk_index: int = Field(ge=0, le=255, description="0~100, 255=invalid")
    valid_weight: float = Field(default=1.0, ge=0, le=1)
    quality: QualityV2
    signals: SignalsV2
    cooling: CoolingV2
    contributions: dict[str, float] = Field(default_factory=dict)
    active_errors: list[str] = Field(default_factory=list)
    raw: RawGloveV2 | None = None
    radio: RadioLinkV2 | None = None
    config_version: str = "0.4.0"
    sequence: int


class EventRecord(BaseModel):
    """Event 레코드 (대회 전 기간 보존). 감사·시연 목적."""

    seq: int
    gateway_utc: str
    monotonic_ms: int
    device_id: str
    event_type: str  # e.g. STATE_CHANGE, COOLING_START, SOS, ACK_TIMEOUT, ERROR
    reason: str = ""
    payload: dict = Field(default_factory=dict)
    previous_hash: str | None = None
    event_hash: str | None = None


class CommandAckRecord(BaseModel):
    """Command/ACK 레코드 (대회 전 기간 보존). 폐루프 증명 목적."""

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
    """User action 레코드 (대회 전 기간 보존). 책임 추적 목적."""

    role: Literal["observer", "commander", "tester", "maintainer"]
    actor_id: str
    action: Literal["ack", "emergency_close", "export", "config_update"]
    target_id: str
    reason: str = ""
    gateway_utc: str
