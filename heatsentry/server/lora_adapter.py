"""Heltec LoRa 35-byte packet -> TelemetryV2.

The Belt is the single source of truth for the real hardware.

The Gateway does NOT recalculate RiskIndex/FSM.
It forwards:
    DeviceState
    CoolingStage
    RiskIndex
    Cause
that the Belt actually used for fan/OLED control.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from heatsentry.common.glove_packets import (
    BeltCauseCode,
    CoolingStageCode,
    DeviceStateCode,
    GloveTelemetryPacket,
    decode_glove_telemetry,
)
from heatsentry.common.schema import TelemetryV2


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
    last_raw: int | None = None
    wrap_count: int = 0

    def extend(
        self,
        raw_sequence: int,
    ) -> int:

        if (
            self.last_raw is not None
            and self.last_raw > 60_000
            and raw_sequence < 1_000
        ):
            self.wrap_count += 1

        self.last_raw = raw_sequence

        return (
            self.wrap_count * 65_536
            + raw_sequence
        )


def _contributions(
    packet: GloveTelemetryPacket,
) -> dict[str, float]:

    cause = packet.belt_cause

    if cause is None:
        return {}

    key = _CAUSE_TO_CONTRIBUTION.get(
        cause
    )

    if key is None:
        return {}

    risk = packet.belt_risk_index

    value = (
        float(risk)
        if risk is not None
        and 0 <= risk <= 100
        else 1.0
    )

    return {
        key: value,
    }


def _fan_percent(
    packet: GloveTelemetryPacket,
) -> int:

    stage = packet.cooling_stage

    if stage is None:
        return (
            100
            if packet.fan_on
            else 0
        )

    if stage == CoolingStageCode.C0:
        return 0

    if stage == CoolingStageCode.C1:
        return 50

    if stage in (
        CoolingStageCode.C2,
        CoolingStageCode.C3,
        CoolingStageCode.C4,
    ):
        return 100

    return 0


class LoRaTelemetryAdapter:
    def __init__(
        self,
        *args,
        **kwargs,
    ) -> None:

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

        return state.extend(
            packet.sequence
        )

    def convert(
        self,
        payload: bytes,
        *,
        rssi_dbm: int | None = None,
        snr_db: int | None = None,
        monotonic_ms: int | None = None,
    ) -> TelemetryV2:

        packet = decode_glove_telemetry(
            payload
        )

        if monotonic_ms is None:
            monotonic_ms = int(
                time.monotonic() * 1000
            )

        active_errors: list[str] = []

        # ---------------------------------------------------------------
        # DeviceState: direct Belt state
        # ---------------------------------------------------------------
        device_state = packet.device_state

        if device_state is None:
            state_name = "SENSOR_CHECK"
            active_errors.append(
                "STATE_INVALID"
            )
        else:
            state_name = device_state.name

        # ---------------------------------------------------------------
        # CoolingStage: C0~C4 directly from Belt
        # ---------------------------------------------------------------
        stage = packet.cooling_stage

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
            risk_index = 255
            active_errors.append(
                "RISK_INVALID"
            )
        else:
            risk_index = belt_risk

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

        glove_available = (
            packet.glove_available
        )

        ppg_ok = (
            glove_available
            and packet.finger_detected
            and packet.bpm > 0
        )

        quality = {
            "ppg":
                100 if ppg_ok else 0,

            "skin":
                100 if glove_available else 0,

            "eda":
                100 if glove_available else 0,

            "imu":
                0,
        }

        return TelemetryV2(
            gateway_utc=_utc_now(),

            device_id=(
                f"HS-W-{packet.node_id:03d}"
            ),

            monotonic_ms=monotonic_ms,

            state=state_name,

            risk_index=risk_index,

            valid_weight=valid_weight,

            quality=quality,

            signals={
                "hr_bpm":
                    packet.bpm
                    if glove_available
                    else 0,

                "skin_c":
                    packet.skin_temp_c
                    if glove_available
                    else 0.0,

                "activity":
                    "UNKNOWN",
            },

            cooling={
                "requested":
                    requested_stage,

                "actual_pwm":
                    _fan_percent(packet),

                "current_ma":
                    0,
            },

            contributions=
                _contributions(packet),

            active_errors=
                sorted(
                    set(active_errors)
                ),

            raw={
                "gsr":
                    packet.gsr
                    if glove_available
                    else None,

                "gsr_diff":
                    packet.gsr_diff
                    if glove_available
                    else None,

                "ir":
                    packet.ir
                    if glove_available
                    else None,

                "air_temp_c":
                    None,

                "humidity_percent":
                    None,

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
                    else None,

                "belt_fan_on":
                    packet.fan_on,

                "gps_fix":
                    packet.gps_fix,

                "latitude":
                    packet.latitude
                    if packet.gps_fix
                    else None,

                "longitude":
                    packet.longitude
                    if packet.gps_fix
                    else None,
            },

            radio={
                "rssi_dbm":
                    rssi_dbm,

                "snr_db":
                    snr_db,
            },

            config_version=
                "belt-unified-state-v2",

            sequence=
                self._extended_sequence(
                    packet
                ),
        )
