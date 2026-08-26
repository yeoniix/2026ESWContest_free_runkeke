"""손목 센서 노드(SU-W) 시뮬레이터.

출처: HS-PDD-002 "손목 센서 노드 상세 설계", HS-SIID-002 "상태기계와 명령 중재".

SU-W 책임: "센서 품질·RiskIndex·상태·냉각 명령". 이 클래스가 BaselineBuilder,
RiskEngine, HeatSentryFsm을 소유하고 매 tick(1Hz, ALG-001)마다:
  1) 기준선이 없으면 기준선을 쌓고,
  2) 있으면 RiskIndex를 계산하고,
  3) FSM으로 냉각 단계를 정하고,
  4) 필요하면 COOL_CMD를 허리(BeltNode)에 보내 ACK을 받는다(재전송 포함).
게이트웨이(server)에는 이미 판정이 끝난 결과만 보낸다 — SU-G는 재판정하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from algorithm.baseline import Baseline, BaselineBuilder, BaselineSample
from algorithm.display_status import make_display_status, select_display_cause
from algorithm.fsm import HeatSentryFsm, ManualInputs
from algorithm.risk_config import RiskConfig, DEFAULT_CONFIG
from algorithm.risk_engine import RiskEngine, SensorSample
from common.packets import CoolCmd, CoolReason, DeviceState
from node_sim.belt_node import BeltNode

_STAGE_INDEX = {"C0": 0, "C1": 1, "C2": 2, "C3": 3, "C4": 4}

# 문서에 정확한 규칙이 없어 통합팀이 정할 자리(설계 기본값): 활동 라벨 경계.
_ACTIVITY_THRESHOLDS = (0.15, "REST"), (0.4, "WALK"), (0.75, "RUN")


@dataclass
class RawTick:
    """시나리오 생성기가 매 초 만드는 원시 입력. node_sim/scenarios.py 참고."""

    hr_bpm: float
    hrv_rmssd: float
    skin_temp_c: float
    skin_temp_slope_c_per_min: float
    eda_delta_norm: float
    activity_load: float
    env_heat_proxy: float

    fall: bool = False
    no_motion: bool = False
    no_response: bool = False
    manual_sos: bool = False

    quality_ppg: int = 100
    quality_eda: int = 100
    skin_temp_stale_s: float = 0.0
    imu_ok: bool = True
    # IR/Finger 센서에서 얻은 장갑 착용 여부. 실제 LoRa 패킷의 Finger 값과 연결한다.
    finger_detected: bool = True

    comms_ok: bool = True
    commander_fan_percent: int | None = None
    test_mode: bool = False

    # T04(ACK 손실) 시험용: 이번 tick에서 belt에 명령을 보낼 때 몇 번째 시도까지
    # 일부러 유실시킬지. 0이면 정상 전달.
    drop_ack_attempts: int = 0

    # T05(냉각 안전) 시험용: 허리 쪽 고장 주입. run_demo가 tick 전에 belt에 반영한다.
    belt_overcurrent: bool = False
    belt_low_temp: bool = False
    belt_physical_stop: bool = False

    # T07(미회복) 시험용: 지휘관이 "회복 추세 확인"을 눌렀다는 신호(C3->C2 하향 조건).
    commander_confirm_recovery: bool = False


def _activity_label(raw: RawTick) -> str:
    if raw.fall and raw.no_motion:
        return "STATIC"
    for threshold, label in _ACTIVITY_THRESHOLDS:
        if raw.activity_load < threshold:
            return label
    return "CRAWL"


class WristNode:
    def __init__(
        self,
        belt: BeltNode,
        device_id: str = "HS-W-001",
        config: RiskConfig = DEFAULT_CONFIG,
    ) -> None:
        self.device_id = device_id
        self.belt = belt
        self.config = config
        self.risk_engine = RiskEngine(config)
        self.fsm = HeatSentryFsm(config.fsm)
        self.baseline_builder = BaselineBuilder(config.baseline)
        self.baseline: Baseline | None = None

        self.monotonic_ms = 0
        self.sequence = 0
        self._cmd_id_counter = 0
        self._last_sent_fan: int | None = None
        self.battery_percent = 100

    def _next_cmd_id(self) -> int:
        self._cmd_id_counter += 1
        return self._cmd_id_counter

    def _send_cool_cmd(self, level: int, reason: CoolReason, raw: RawTick) -> tuple[dict | None, list[dict]]:
        """SIID p4 "연결·재전송 정책" #1: 500ms 이내 ACK 없으면 최대 3회 재전송.

        시뮬레이션에서는 실제 500ms를 기다리지 않고, drop_ack_attempts로 지정된
        횟수만큼 "허리에 패킷이 도달하지 못했다"고 간주한 뒤 다시 시도한다.
        """
        events: list[dict] = []
        cmd_id = self._next_cmd_id()
        max_retries = self.config.fsm.ack_max_retries

        if not raw.comms_ok:
            events.append({"event_type": "COMMS_LOST", "reason": "E201", "payload": {"cmd_id": cmd_id}})
            return None, events

        cmd = CoolCmd(
            level=level,
            duration_s=30,
            cmd_id=cmd_id,
            sequence=self.sequence,
            reason=reason,
        )

        attempts = 0
        for attempt in range(max_retries + 1):
            attempts = attempt + 1
            if attempt < raw.drop_ack_attempts:
                events.append(
                    {
                        "event_type": "ACK_TIMEOUT",
                        "reason": f"attempt {attempts} lost (simulated)",
                        "payload": {"cmd_id": cmd_id, "attempt": attempts},
                    }
                )
                continue
            ack = self.belt.handle_cmd(cmd, self.monotonic_ms)
            record = {
                "cmd_id": cmd_id,
                "device_id": self.device_id,
                "requested_level": level,
                "requested_reason": reason.name,
                "actual_pwm": ack.actual_pwm,
                "current_ma": ack.current_ma,
                "result": ack.result.name,
                "retries": attempts - 1,
            }
            if attempts > 1:
                events.append(
                    {
                        "event_type": "ACK_RETRY_SUCCESS",
                        "reason": f"succeeded on attempt {attempts}",
                        "payload": {"cmd_id": cmd_id, "attempts": attempts},
                    }
                )
            return record, events

        # 표4 정책 #3 계열: 최종 실패 -> 통신 오류 경고 + 게이트웨이에 직접 SOS 시도
        # (v1.0 SIDD p11 "3회 실패 시 손목에서 통신 오류를 경고하고 게이트웨이에
        # 직접 SOS를 시도한다"; v2.0에서도 안전 원칙은 유지).
        events.append(
            {
                "event_type": "COOL_CMD_FAILED",
                "reason": f"no ACK after {attempts} attempts",
                "payload": {"cmd_id": cmd_id, "level": level},
            }
        )
        return None, events

    def tick(self, raw: RawTick, dt_s: float = 1.0) -> dict:
        """한 틱을 처리하고 (telemetry, node_events, command_ack_record)를 반환한다."""
        events: list[dict] = []

        if self.baseline is None:
            self.baseline_builder.add_sample(
                BaselineSample(
                    hr_bpm=raw.hr_bpm,
                    hrv_rmssd=raw.hrv_rmssd,
                    skin_temp_c=raw.skin_temp_c,
                    eda_norm=raw.eda_delta_norm,
                    quality_ppg=raw.quality_ppg,
                    quality_eda=raw.quality_eda,
                ),
                dt_s=dt_s,
            )
            if self.baseline_builder.is_ready():
                self.baseline = self.baseline_builder.build()
                events.append({"event_type": "BASELINE_READY", "reason": "", "payload": {}})
            elif self.baseline_builder.is_expired():
                # PDD p5 "기준선이 생성되지 않으면 제한 모드로 동작하고 재착용 요청".
                self.baseline = self.baseline_builder.build() or Baseline(
                    hr_median=100, hr_mad=10, hrv_median=30, skin_temp_median=36.0,
                    eda_median=0.2, sample_count=0,
                )
                events.append({"event_type": "BASELINE_FAILED", "reason": "재착용 요청", "payload": {}})

        command_ack_record: dict | None = None

        if self.baseline is None:
            device_state = DeviceState.BASELINE
            risk_index = 255
            valid_weight = 0.0
            sensor_limited = True
            contributions: dict[str, float] = {}
            active_errors: list[str] = []
            cooling_stage = "C0"
            commanded_fan = 0
            quality = {"ppg": raw.quality_ppg, "skin": 100, "eda": raw.quality_eda, "imu": 100 if raw.imu_ok else 0}
        else:
            sample = SensorSample(
                hr_bpm=raw.hr_bpm,
                hrv_rmssd=raw.hrv_rmssd,
                skin_temp_c=raw.skin_temp_c,
                skin_temp_slope_c_per_min=raw.skin_temp_slope_c_per_min,
                eda_delta_norm=raw.eda_delta_norm,
                activity_load=raw.activity_load,
                env_heat_proxy=raw.env_heat_proxy,
                fall_detected=raw.fall,
                no_motion=raw.no_motion,
                no_response=raw.no_response,
                manual_sos=raw.manual_sos,
                quality_ppg=raw.quality_ppg,
                quality_eda=raw.quality_eda,
                skin_temp_stale_s=raw.skin_temp_stale_s,
                imu_ok=raw.imu_ok,
            )
            risk = self.risk_engine.evaluate(sample, self.baseline)

            if raw.commander_confirm_recovery:
                self.fsm.confirm_recovery()

            manual = ManualInputs(
                safety_stop=self.belt.overcurrent_fault or self.belt.low_temp_fault or self.belt.manual_stop_active,
                manual_sos=raw.manual_sos,
                commander_fan_percent=raw.commander_fan_percent,
                test_mode=raw.test_mode,
            )
            fsm_out = self.fsm.update(risk, dt_s, manual)
            for e in fsm_out.events:
                events.append({"event_type": e, "reason": fsm_out.cool_reason.name, "payload": {"risk_index": risk.risk_index}})

            device_state = fsm_out.device_state
            risk_index = risk.risk_index
            valid_weight = risk.valid_weight
            sensor_limited = risk.sensor_limited
            contributions = risk.contributions
            active_errors = [e.value for e in risk.active_errors]
            cooling_stage = fsm_out.cooling_stage
            commanded_fan = fsm_out.commanded_fan_percent

            if commanded_fan != self._last_sent_fan:
                command_ack_record, cmd_events = self._send_cool_cmd(commanded_fan, fsm_out.cool_reason, raw)
                events.extend(cmd_events)
                self._last_sent_fan = commanded_fan

            quality = {
                "ppg": raw.quality_ppg,
                "skin": 0 if raw.skin_temp_stale_s > self.config.quality.skin_temp_stale_s else 100,
                "eda": raw.quality_eda,
                "imu": 100 if raw.imu_ok else 0,
            }

        # 허리는 손목이 명령을 안 보내는 틱에도 자체 워치독으로 계속 동작한다.
        belt_events = self.belt.tick(dt_s, comms_ok=raw.comms_ok)
        for be in belt_events:
            events.append({"event_type": be, "reason": "", "payload": {}})

        telemetry = {
            "schema_version": "2.0",
            "gateway_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z",
            "device_id": self.device_id,
            "monotonic_ms": self.monotonic_ms,
            "state": device_state.name,
            "risk_index": risk_index,
            "valid_weight": round(valid_weight, 4),
            "quality": quality,
            "signals": {
                "hr_bpm": round(raw.hr_bpm),
                "skin_c": round(raw.skin_temp_c, 2),
                "activity": _activity_label(raw),
            },
            "cooling": {
                "requested": _STAGE_INDEX[cooling_stage],
                "actual_pwm": self.belt.fan_pwm_percent,
                "current_ma": self.belt.current_ma,
            },
            "contributions": contributions,
            "active_errors": active_errors,
            "config_version": self.config.version,
            "sequence": self.sequence,
        }
        # 실제 장갑 펌웨어는 이 두 문구를 I2C LCD/OLED에 그대로 출력하면 된다.
        # 현재 API 스키마는 호환성을 위해 화면 문구를 저장하지 않는다.
        display = make_display_status(
            device_state.name,
            cooling_stage,
            commanded_fan,
            cause=select_display_cause(contributions),
            finger_detected=raw.finger_detected,
            hr_bpm=raw.hr_bpm,
            skin_temp_c=raw.skin_temp_c,
        )
        if sensor_limited and device_state != DeviceState.BASELINE:
            telemetry["active_errors"] = list(set(telemetry["active_errors"] + ["SENSOR_LIMITED"]))

        self.monotonic_ms += int(dt_s * 1000)
        self.sequence += 1

        return {
            "telemetry": telemetry,
            "events": events,
            "command_ack": command_ack_record,
            "display": {"line1": display.line1, "line2": display.line2},
        }
