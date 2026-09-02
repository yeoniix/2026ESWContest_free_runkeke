"""LoRa 수신기의 35바이트 ESP32 패킷을 관제 TelemetryV2로 변환한다.

시리얼/USB 수신기는 이 모듈에 ``payload``, RSSI, SNR만 전달하면 된다. RiskIndex
계산은 GatewayStore가 아닌 이 엣지 어댑터에서 수행하므로 저장소는 수신 데이터를
재판정하지 않는 책임 경계를 유지한다.

판정이 두 벌인 이유
-------------------
벨트 펌웨어(firmware/belt_heltec)는 LoRa가 끊겨도 팬과 장갑 OLED를 스스로
구동해야 하므로 자체 위험점수·상태기계를 갖고 있고, 그 결론을 패킷에 실어
보낸다. 이 어댑터는 같은 패킷으로 RiskIndex v0.3을 따로 계산한다. 두 판정은
임계값도 입력 특징도 달라 결과가 갈릴 수 있다.

어느 한쪽으로 덮어쓰지 않는다:

- ``state``/``risk_index``    게이트웨이의 RiskIndex v0.3 판정 (관제·분석용)
- ``raw.belt_state``/``raw.belt_cause``  벨트가 실제로 내린 판정.
  현장에서 팬을 돌리고 장갑 화면에 뜬 것은 이 값이다.
- 둘이 갈리면 ``active_errors``에 ``BELT_STATE_MISMATCH``를 남긴다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from heatsentry.algorithm.hardware_adapter import HardwareRiskAdapter
from heatsentry.algorithm.risk_config import HARDWARE_CONFIG, RiskConfig
from heatsentry.algorithm.fsm import HeatSentryFsm, ManualInputs
from heatsentry.common.glove_packets import (
    BeltStateCode,
    GloveTelemetryPacket,
    decode_glove_telemetry,
)
from heatsentry.common.schema import TelemetryV2

# 벨트의 상태 코드를 게이트웨이의 DeviceState 이름으로 옮긴 표.
# 두 체계는 단계 구분이 다르다 — 벨트는 팬 출력(50/100)으로, 게이트웨이는
# RiskIndex 지속시간(C1~C4)으로 나눈다. 아래는 "같은 뜻으로 볼 수 있는" 대응이며,
# 불일치 검출에만 쓰고 게이트웨이 판정을 덮어쓰는 데는 쓰지 않는다.
_BELT_TO_DEVICE_STATE = {
    BeltStateCode.BOOT: "BOOT",
    BeltStateCode.BASELINE: "BASELINE",
    BeltStateCode.NORMAL: "NORMAL",
    BeltStateCode.CAUTION: "WARNING",
    BeltStateCode.COOLING_50: "COOLING",
    BeltStateCode.DANGER: "COOLING",
    BeltStateCode.EMERGENCY: "EMERGENCY",
    BeltStateCode.SENSOR_CHECK: "FAULT",
}


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
    """수신기 프로세스에서 장치별로 하나만 생성해 재사용한다.

    기본 설정은 HARDWARE_CONFIG다 — 실물 패킷에 없는 HRV·IMU·환경 특징의
    가중치가 0이라, 살아있는 가중치 합이 설계상 결손 때문에 미달하는 일이 없다.
    """

    def __init__(self, config: RiskConfig = HARDWARE_CONFIG) -> None:
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
        # DHT 미탑재는 오류가 아니다 — 센서가 동작하지 않아 하드웨어에서 제거됐고,
        # HARDWARE_CONFIG가 EnvHeatProxy 가중치를 0으로 두어 설계에 반영돼 있다.

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
            # 두 판정이 갈리면 감춘다고 안전해지지 않는다. 현장 장치(벨트)와
            # 관제(RiskIndex v0.3)가 서로 다른 결론을 냈다는 사실 자체를 올린다.
            belt_equivalent = _BELT_TO_DEVICE_STATE.get(packet.belt_state) if packet.belt_state else None
            if belt_equivalent is not None and belt_equivalent != state:
                active_errors.append("BELT_STATE_MISMATCH")

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
                # 벨트는 팬 두 개를 개별 채널로 돌리고 1단계 냉각을 "듀티 50%"가 아니라
                # "팬 하나만 100%"로 구현한다. 패킷에는 켜짐 여부(FAN_ON) 하나만 오므로
                # 여기서 나오는 값은 0 또는 100뿐이고, 벨트의 냉각 1/2단계를 이 값으로는
                # 구분할 수 없다 — 구분이 필요하면 raw.belt_state를 본다.
                "actual_pwm": 100 if packet.fan_on else 0,
                "current_ma": 0,
            },
            contributions=contributions,
            active_errors=sorted(set(active_errors)),
            raw={
                "gsr": packet.gsr if glove_available else None,
                "gsr_diff": packet.gsr_diff if glove_available else None,
                "ir": packet.ir if glove_available else None,
                "air_temp_c": packet.air_temp_c,
                "humidity_percent": packet.humidity_percent,
                "finger_detected": packet.finger_detected,
                "glove_data": packet.glove_available,
                "dht_data": packet.dht_available,
                "belt_state": packet.belt_state.name if packet.belt_state else None,
                "belt_cause": packet.belt_cause.name if packet.belt_cause else None,
                "belt_fan_on": packet.fan_on,
                "gps_fix": packet.gps_fix,
                "latitude": packet.latitude if packet.gps_fix else None,
                "longitude": packet.longitude if packet.gps_fix else None,
            },
            radio={"rssi_dbm": rssi_dbm, "snr_db": snr_db},
            config_version=self.config.version,
            sequence=self._extended_sequence(packet),
        )
