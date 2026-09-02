"""LoRa 수신기의 35바이트 ESP32 패킷을 관제 TelemetryV2로 변환한다.

시리얼/USB 수신기는 이 모듈에 ``payload``, RSSI, SNR만 전달하면 된다. RiskIndex
계산은 GatewayStore가 아닌 이 엣지 어댑터에서 수행하므로 저장소는 수신 데이터를
재판정하지 않는 책임 경계를 유지한다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from algorithm.hardware_adapter import HardwareRiskAdapter
from algorithm.risk_config import DEFAULT_CONFIG, RiskConfig
from algorithm.fsm import HeatSentryFsm, ManualInputs
from common.glove_packets import GloveTelemetryPacket, decode_glove_telemetry
from common.schema import TelemetryV2

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class _SequenceState:
    last_raw: int | None = None
    wrap_count: int = 0

    def extend(self, raw_sequence: int) -> int:
        if self.last_raw is not None and self.last_raw > 60_000 and raw_sequence < 1_000:
            self.wrap_count += 1
        self.last_raw = raw_sequence
        return self.wrap_count * 65_536 + raw_sequence


@dataclass
class _DevicePipeline:
    risk_adapter: HardwareRiskAdapter
    fsm: HeatSentryFsm
    last_monotonic_ms: int | None = None


class LoRaTelemetryAdapter:
    """수신기 프로세스에서 장치별로 하나만 생성해 재사용한다."""

    def __init__(self, config: RiskConfig = DEFAULT_CONFIG) -> None:
        self.config = config
        self._sequences: dict[int, _SequenceState] = {}
        self._pipelines: dict[int, _DevicePipeline] = {}

    def _pipeline(self, packet: GloveTelemetryPacket) -> _DevicePipeline:
        return self._pipelines.setdefault(
            packet.node_id,
            _DevicePipeline(HardwareRiskAdapter(self.config), HeatSentryFsm(self.config.fsm)),
        )

    def _extended_sequence(self, packet: GloveTelemetryPacket) -> int:
        state = self._sequences.setdefault(packet.node_id, _SequenceState())
        return state.extend(packet.sequence)

    def convert(
        self,
        payload: bytes,
        *,
        rssi_dbm: int | None = None,
        snr_db: int | None = None,
        monotonic_ms: int | None = None,
    ) -> TelemetryV2:
        packet = decode_glove_telemetry(payload)
        monotonic_ms = monotonic_ms if monotonic_ms is not None else int(time.monotonic() * 1000)
        pipeline = self._pipeline(packet)
        reading = pipeline.risk_adapter.update(packet, monotonic_ms)

        if pipeline.last_monotonic_ms is None:
            dt_s = 1.0
        else:
            dt_s = max(0.0, (monotonic_ms - pipeline.last_monotonic_ms) / 1000.0)
        pipeline.last_monotonic_ms = monotonic_ms

        active_errors: list[str] = []
        if not packet.sensor_ready:
            active_errors.append("SENSOR_CHECK")
        if not packet.dht_available:
            active_errors.append("DHT_INVALID")

        if packet.emergency_active:
            state = "EMERGENCY"
            risk_index = 255 if reading.risk is None else reading.risk.risk_index
            valid_weight = 0.0 if reading.risk is None else reading.risk.valid_weight
            contributions = {} if reading.risk is None else reading.risk.contributions
            requested = self.config.fsm.stage_index("C4")
        elif not packet.sensor_ready:
            state = "FAULT"
            risk_index = 255
            valid_weight = 0.0
            contributions = {}
            requested = 0
        elif reading.risk is None:
            state = "BASELINE"
            risk_index = 255
            valid_weight = 0.0
            contributions = {}
            requested = 0
        else:
            fsm_out = pipeline.fsm.update(
                reading.risk,
                dt_s,
                ManualInputs(manual_sos=packet.emergency_active),
            )
            state = fsm_out.device_state.name
            risk_index = reading.risk.risk_index
            valid_weight = reading.risk.valid_weight
            contributions = reading.risk.contributions
            requested = self.config.fsm.stage_index(fsm_out.cooling_stage)
            active_errors.extend(error.value for error in reading.risk.active_errors)
            if reading.risk.sensor_limited:
                active_errors.append("SENSOR_LIMITED")

        glove_available = packet.glove_available
        return TelemetryV2(
            gateway_utc=_utc_now(),
            device_id=f"HS-W-{packet.node_id:03d}",
            monotonic_ms=monotonic_ms,
            state=state,
            risk_index=risk_index,
            valid_weight=valid_weight,
            quality={key: reading.quality[key] for key in ("ppg", "skin", "eda", "imu")},
            signals={
                "hr_bpm": packet.bpm if glove_available else 0,
                "skin_c": packet.skin_temp_c if glove_available else 0.0,
                "activity": "UNKNOWN",
            },
            cooling={
                "requested": requested,
                "actual_pwm": 100 if packet.fan_on else 0,
                "current_ma": 0,
            },
            contributions=contributions,
            active_errors=sorted(set(active_errors)),
            raw={
                "gsr": packet.gsr if glove_available else None,
                "gsr_diff": packet.gsr_diff if glove_available else None,
                "ir": packet.ir if glove_available else None,
                "air_temp_c": packet.air_temp_c if packet.dht_available else None,
                "humidity_percent": packet.humidity_percent if packet.dht_available else None,
                "finger_detected": packet.finger_detected,
                "glove_data": packet.glove_available,
                "dht_data": packet.dht_available,
                "gps_fix": packet.gps_fix,
                "latitude": packet.latitude if packet.gps_fix else None,
                "longitude": packet.longitude if packet.gps_fix else None,
            },
            radio={"rssi_dbm": rssi_dbm, "snr_db": snr_db},
            config_version=self.config.version,
            sequence=self._extended_sequence(packet),
        )
