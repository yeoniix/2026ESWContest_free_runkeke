"""LoRa 수신기의 35바이트 ESP32 패킷을 관제 TelemetryV2로 변환한다.
"""Heltec LoRa 35-byte packet -> TelemetryV2.

현재 실물 하드웨어에서는 BELT를 위험 판정의 단일 기준(Single Source of Truth)으로
사용한다.
The Belt is the single source of truth for the real hardware.

흐름:
    ESP32U 센서
        -> Belt baseline / RiskIndex / FSM
        -> 팬 제어
        -> 장갑 OLED 상태
        -> LoRa로 RiskIndex + State + Cause 송신
        -> Base / Gateway / Dashboard는 그대로 표시

따라서 이 어댑터는 더 이상 HardwareRiskAdapter / HeatSentryFsm으로
RiskIndex와 상태를 다시 계산하지 않는다.

현재 35바이트 패킷 재활용:
    airTemp_x10   : high byte = belt state, low byte = belt cause
    humidity_x10 : belt RiskIndex (0~100, 255=invalid)
The Gateway does NOT recalculate RiskIndex/FSM.
It forwards:
    DeviceState
    CoolingStage
    RiskIndex
    Cause
that the Belt actually used for fan/OLED control.
"""

from __future__ import annotations
@@ -27,74 +19,56 @@

from heatsentry.common.glove_packets import (
BeltCauseCode,
    BeltStateCode,
    CoolingStageCode,
    DeviceStateCode,
GloveTelemetryPacket,
decode_glove_telemetry,
)
from heatsentry.common.schema import TelemetryV2


# Belt 상태를 Dashboard TelemetryV2 state 이름으로 변환
_BELT_TO_DEVICE_STATE: dict[BeltStateCode, str] = {
    BeltStateCode.BOOT: "BOOT",
    BeltStateCode.BASELINE: "BASELINE",
    BeltStateCode.NORMAL: "NORMAL",
    BeltStateCode.CAUTION: "WARNING",
    BeltStateCode.COOLING_50: "COOLING",
    BeltStateCode.DANGER: "COOLING",
    BeltStateCode.EMERGENCY: "EMERGENCY",
    BeltStateCode.SENSOR_CHECK: "FAULT",
}


# Dashboard의 cooling.requested는 C0~C4 숫자
#
# 현재 Belt FSM:
# NORMAL / CAUTION -> C0
# COOLING_50       -> C1
# DANGER           -> C2
# EMERGENCY        -> C4
_BELT_TO_COOLING_STAGE: dict[BeltStateCode, int] = {
    BeltStateCode.BOOT: 0,
    BeltStateCode.BASELINE: 0,
    BeltStateCode.NORMAL: 0,
    BeltStateCode.CAUTION: 0,
    BeltStateCode.COOLING_50: 1,
    BeltStateCode.DANGER: 2,
    BeltStateCode.EMERGENCY: 4,
    BeltStateCode.SENSOR_CHECK: 0,
}


# Dashboard DeviceCard는 contributions에서 가장 큰 key를 골라
# "심박 상승 / 피부온도 상승 / GSR 변화 ..."를 표시한다.
_CAUSE_TO_CONTRIBUTION: dict[BeltCauseCode, str] = {
    BeltCauseCode.HR_HIGH: "HR_dev",
    BeltCauseCode.HR_CHANGE: "HRV_suppression",
    BeltCauseCode.TEMP_UP: "SkinTemp_slope",
    BeltCauseCode.GSR_UP: "EDA_delta",
    BeltCauseCode.HOT_ENV: "EnvHeatProxy",
    BeltCauseCode.ACTIVE: "ActivityLoad",
_CAUSE_TO_CONTRIBUTION: dict[
    BeltCauseCode,
    str,
] = {
    BeltCauseCode.HR_HIGH:
        "HR_dev",
    BeltCauseCode.HR_CHANGE:
        "HRV_suppression",
    BeltCauseCode.TEMP_UP:
        "SkinTemp_slope",
    BeltCauseCode.GSR_UP:
        "EDA_delta",
    BeltCauseCode.HOT_ENV:
        "EnvHeatProxy",
    BeltCauseCode.ACTIVE:
        "ActivityLoad",
}


def _utc_now() -> str:
return (
datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
        .isoformat(
            timespec="milliseconds"
        )
        .replace(
            "+00:00",
            "Z",
        )
)


@dataclass
class _SequenceState:
    """ESP32 uint16 sequence를 장시간 동작용 증가 sequence로 확장."""

last_raw: int | None = None
wrap_count: int = 0

    def extend(self, raw_sequence: int) -> int:
        # 65535 -> 0 wrap 감지
    def extend(
        self,
        raw_sequence: int,
    ) -> int:

if (
self.last_raw is not None
and self.last_raw > 60_000
@@ -104,89 +78,97 @@ def extend(self, raw_sequence: int) -> int:

self.last_raw = raw_sequence

        return self.wrap_count * 65_536 + raw_sequence
        return (
            self.wrap_count * 65_536
            + raw_sequence
        )


def _belt_contributions(
def _contributions(
packet: GloveTelemetryPacket,
) -> dict[str, float]:
    """벨트 Cause를 기존 Dashboard '판단 근거' 형식으로 변환."""

cause = packet.belt_cause

if cause is None:
return {}

    contribution_key = _CAUSE_TO_CONTRIBUTION.get(cause)
    key = _CAUSE_TO_CONTRIBUTION.get(
        cause
    )

    if contribution_key is None:
        # NONE / SENSOR는 위험 기여도 그래프용 원인이 아님
    if key is None:
return {}

risk = packet.belt_risk_index

    # DeviceCard에서는 상대적인 최대값만 사용한다.
    # 실제 Risk가 있으면 그 값을 쓰고, 없으면 1.0을 넣어 label만 유지한다.
    if risk is not None and 0 <= risk <= 100:
        value = float(risk)
    else:
        value = 1.0
    value = (
        float(risk)
        if risk is not None
        and 0 <= risk <= 100
        else 1.0
    )

return {
        contribution_key: value,
        key: value,
}


def _effective_fan_percent(
def _fan_percent(
packet: GloveTelemetryPacket,
) -> int:
    """대시보드에 표시할 전체 냉각 출력.

    현재 Belt 하드웨어 구현:
    - COOLING_50 : FAN1 100%, FAN2 0% -> 전체 냉각단계 50%
    - DANGER     : FAN1 100%, FAN2 100% -> 100%
    - EMERGENCY  : FAN1 100%, FAN2 100% -> 100%
    stage = packet.cooling_stage

    LoRa flags에는 FAN_ON 한 비트만 있으므로 Belt state와 함께 해석한다.
    """
    if stage is None:
        return (
            100
            if packet.fan_on
            else 0
        )

    if not packet.fan_on:
    if stage == CoolingStageCode.C0:
return 0

    state = packet.belt_state

    if state == BeltStateCode.COOLING_50:
    if stage == CoolingStageCode.C1:
return 50

    if state in (
        BeltStateCode.DANGER,
        BeltStateCode.EMERGENCY,
    if stage in (
        CoolingStageCode.C2,
        CoolingStageCode.C3,
        CoolingStageCode.C4,
):
return 100

    # 예상하지 못한 상태에서 FAN_ON이 들어온 경우에도
    # 실제 팬이 켜졌다는 사실은 보존한다.
    return 100
    return 0


class LoRaTelemetryAdapter:
    """35B LoRa packet을 Belt 판정 그대로 TelemetryV2로 변환한다."""
    def __init__(
        self,
        *args,
        **kwargs,
    ) -> None:

    def __init__(self, *args, **kwargs) -> None:
        # 기존 코드/테스트가 LoRaTelemetryAdapter(config=...) 형태로
        # 생성하더라도 깨지지 않도록 인자는 받아 두되 사용하지 않는다.
        self._sequences: dict[int, _SequenceState] = {}
        # Keep constructor compatibility with old callers.
        self._sequences: dict[
            int,
            _SequenceState,
        ] = {}

def _extended_sequence(
self,
packet: GloveTelemetryPacket,
) -> int:

state = self._sequences.setdefault(
packet.node_id,
_SequenceState(),
)

        return state.extend(packet.sequence)
        return state.extend(
            packet.sequence
        )

def convert(
self,
@@ -197,66 +179,73 @@ def convert(
monotonic_ms: int | None = None,
) -> TelemetryV2:

        packet = decode_glove_telemetry(payload)
        packet = decode_glove_telemetry(
            payload
        )

if monotonic_ms is None:
            monotonic_ms = int(time.monotonic() * 1000)
            monotonic_ms = int(
                time.monotonic() * 1000
            )

active_errors: list[str] = []

        # ==============================================================
        # 1. STATE
        # Gateway에서 재판정하지 않고 Belt state를 그대로 사용
        # ==============================================================
        belt_state = packet.belt_state
        # ---------------------------------------------------------------
        # DeviceState: direct Belt state
        # ---------------------------------------------------------------
        device_state = packet.device_state

        if belt_state is None:
            state = "FAULT"
            requested_stage = 0
            active_errors.append("BELT_STATE_INVALID")
        if device_state is None:
            state_name = "SENSOR_CHECK"
            active_errors.append(
                "STATE_INVALID"
            )
else:
            state = _BELT_TO_DEVICE_STATE[belt_state]
            requested_stage = _BELT_TO_COOLING_STAGE[belt_state]
            state_name = device_state.name

        # SENSOR_CHECK도 Belt가 결정한 경우에만 관제에 올린다.
        if belt_state == BeltStateCode.SENSOR_CHECK:
            active_errors.append("SENSOR_CHECK")
        # ---------------------------------------------------------------
        # CoolingStage: C0~C4 directly from Belt
        # ---------------------------------------------------------------
        stage = packet.cooling_stage

        # ==============================================================
        # 2. RISK INDEX
        # Belt가 실제 FSM에 사용한 값을 그대로 사용
        # ==============================================================
        if stage is None:
            requested_stage = 0
            active_errors.append(
                "COOLING_STAGE_INVALID"
            )
        else:
            requested_stage = int(stage)

        # ---------------------------------------------------------------
        # RiskIndex: direct Belt risk
        # ---------------------------------------------------------------
belt_risk = packet.belt_risk_index

if belt_risk is None:
            # 구형 패킷/DHT 패킷/잘못된 값
risk_index = 255

            if belt_state not in (
                BeltStateCode.BOOT,
                BeltStateCode.BASELINE,
                BeltStateCode.SENSOR_CHECK,
            ):
                active_errors.append("BELT_RISK_INVALID")

            active_errors.append(
                "RISK_INVALID"
            )
else:
risk_index = belt_risk

        # 0~100일 때만 유효한 실제 Risk
        if (
            state_name == "SENSOR_CHECK"
            or not packet.sensor_ready
        ):
            active_errors.append(
                "SENSOR_CHECK"
            )

valid_weight = (
1.0
if 0 <= risk_index <= 100
else 0.0
)

        # ==============================================================
        # 3. SENSOR QUALITY
        #
        # Gateway Risk 계산을 없앴으므로 HardwareRiskAdapter의 quality를
        # 더 이상 만들 수 없다. 현재 실제 패킷에서 확인 가능한 상태만
        # 단순 0/100으로 표현한다.
        # ==============================================================
        glove_available = packet.glove_available
        glove_available = (
            packet.glove_available
        )

ppg_ok = (
glove_available
@@ -265,123 +254,140 @@ def convert(
)

quality = {
            "ppg": 100 if ppg_ok else 0,
            "skin": 100 if glove_available else 0,
            "eda": 100 if glove_available else 0,
            # 현재 35B 패킷에는 IMU 데이터가 없음
            "imu": 0,
            "ppg":
                100 if ppg_ok else 0,

            "skin":
                100 if glove_available else 0,

            "eda":
                100 if glove_available else 0,

            "imu":
                0,
}

        # ==============================================================
        # 4. TelemetryV2 생성
        # ==============================================================
return TelemetryV2(
gateway_utc=_utc_now(),

            device_id=f"HS-W-{packet.node_id:03d}",
            device_id=(
                f"HS-W-{packet.node_id:03d}"
            ),

monotonic_ms=monotonic_ms,

            # ★ Belt의 실제 상태
            state=state,
            state=state_name,

            # ★ Belt의 실제 RiskIndex
risk_index=risk_index,

valid_weight=valid_weight,

quality=quality,

signals={
                "hr_bpm": (
                "hr_bpm":
packet.bpm
if glove_available
                    else 0
                ),
                "skin_c": (
                    else 0,

                "skin_c":
packet.skin_temp_c
if glove_available
                    else 0.0
                ),
                "activity": "UNKNOWN",
                    else 0.0,

                "activity":
                    "UNKNOWN",
},

cooling={
                # C0~C4
                "requested": requested_stage,
                "requested":
                    requested_stage,

                # 실제 하드웨어 냉각 표현
                "actual_pwm": _effective_fan_percent(packet),
                "actual_pwm":
                    _fan_percent(packet),

                # 현재 전류 센서 없음
                "current_ma": 0,
                "current_ma":
                    0,
},

            # Dashboard "판단 근거"도 Belt Cause를 사용
            contributions=_belt_contributions(packet),
            contributions=
                _contributions(packet),

            # BELT_STATE_MISMATCH는 더 이상 생성하지 않음
            active_errors=sorted(set(active_errors)),
            active_errors=
                sorted(
                    set(active_errors)
                ),

raw={
                "gsr": (
                "gsr":
packet.gsr
if glove_available
                    else None
                ),
                "gsr_diff": (
                    else None,

                "gsr_diff":
packet.gsr_diff
if glove_available
                    else None
                ),
                "ir": (
                    else None,

                "ir":
packet.ir
if glove_available
                    else None
                ),
                    else None,

                # 현재 DHT 미탑재이므로 보통 None
                "air_temp_c": packet.air_temp_c,
                "humidity_percent": packet.humidity_percent,
                "air_temp_c":
                    None,

                "finger_detected": packet.finger_detected,
                "glove_data": packet.glove_available,
                "dht_data": packet.dht_available,
                "humidity_percent":
                    None,

                # ★ 현장 Belt 판정
                "belt_state": (
                    packet.belt_state.name
                    if packet.belt_state is not None
                    else None
                ),
                "belt_cause": (
                "finger_detected":
                    packet.finger_detected,

                "glove_data":
                    packet.glove_available,

                "dht_data":
                    False,

                # This now matches top-level state exactly.
                "belt_state":
                    state_name,

                "belt_cause":
packet.belt_cause.name
if packet.belt_cause is not None
                    else None
                ),
                "belt_fan_on": packet.fan_on,
                    else None,

                # GPS
                "gps_fix": packet.gps_fix,
                "latitude": (
                "belt_fan_on":
                    packet.fan_on,

                "gps_fix":
                    packet.gps_fix,

                "latitude":
packet.latitude
if packet.gps_fix
                    else None
                ),
                "longitude": (
                    else None,

                "longitude":
packet.longitude
if packet.gps_fix
                    else None
                ),
                    else None,
},

radio={
                "rssi_dbm": rssi_dbm,
                "snr_db": snr_db,
                "rssi_dbm":
                    rssi_dbm,

                "snr_db":
                    snr_db,
},

            # Gateway Risk v0.3이 아니라 Belt Risk를 사용한다는 표시
            config_version="belt-risk-v1",
            config_version=
                "belt-unified-state-v2",

            sequence=self._extended_sequence(packet),
            sequence=
                self._extended_sequence(
                    packet
                ),
)
