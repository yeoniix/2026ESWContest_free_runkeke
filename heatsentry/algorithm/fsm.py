"""HeatSentry safety FSM.

DeviceState:
    BOOT / BASELINE / NORMAL / CAUTION /
    COOLING / EMERGENCY / SENSOR_CHECK

CoolingStage:
    C0 / C1 / C2 / C3 / C4

The generic Python FSM handles the risk-driven states after baseline.
BOOT / BASELINE / SENSOR_CHECK are selected by the caller depending on
initialization and sensor readiness.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from heatsentry.algorithm.risk_config import (
    FsmConfig,
    DEFAULT_CONFIG,
)
from heatsentry.algorithm.risk_engine import (
    RiskResult,
)
from heatsentry.common.packets import (
    CoolReason,
    DeviceState,
)


class HoldTimer:
    def __init__(self) -> None:
        self.value = 0.0

    def tick(
        self,
        condition: bool,
        dt_s: float,
    ) -> float:
        self.value = (
            self.value + dt_s
            if condition
            else 0.0
        )

        return self.value


@dataclass
class ManualInputs:
    safety_stop: bool = False
    manual_sos: bool = False
    commander_fan_percent: int | None = None
    test_mode: bool = False


@dataclass
class FsmOutput:
    device_state: DeviceState
    cooling_stage: str
    commanded_fan_percent: int
    cool_reason: CoolReason
    sos: bool

    caution_active: bool

    hard_trigger_latched: bool

    events: list[str] = field(
        default_factory=list
    )


class HeatSentryFsm:
    def __init__(
        self,
        config: FsmConfig = DEFAULT_CONFIG.fsm,
    ) -> None:
        self.config = config

        self.lowest_stage = config.stages[0].name
        self.highest_stage = config.stages[-1].name

        # 비상 단계 = 자동 해제 조건이 없는 최상단(기본 표의 C4).
        # 최상단에 해제 조건이 있으면 RiskIndex만으로는 비상에 들어가지 않는다.
        top = config.stages[-1]
        self.emergency_stage = (
            top
            if len(config.stages) >= 2 and top.exit_threshold is None
            else None
        )

        self.stage = self.lowest_stage
        self.caution_active = False

        self.emergency_latched = False
        self.emergency_reason: str | None = None

        self._t_enter: dict[int, HoldTimer] = {}
        self._t_exit: dict[int, HoldTimer] = {}

        for stage in config.stages:
            self._t_enter.setdefault(
                stage.enter_threshold,
                HoldTimer(),
            )

            if stage.exit_threshold is not None:
                self._t_exit.setdefault(
                    stage.exit_threshold,
                    HoldTimer(),
                )

        self._t_caution_enter = HoldTimer()
        self._t_caution_exit = HoldTimer()

        self.commander_recovery_confirm = False

    def confirm_recovery(self) -> None:
        self.commander_recovery_confirm = True

    def close_emergency(self) -> None:
        self.emergency_latched = False
        self.emergency_reason = None

        # 최상단 해제 직후 한 단계 아래를 유지한다
        self.stage = self.config.stages[-2].name if len(
            self.config.stages
        ) >= 2 else self.lowest_stage

    def update(
        self,
        risk: RiskResult,
        dt_s: float,
        manual: ManualInputs | None = None,
    ) -> FsmOutput:

        manual = manual or ManualInputs()
        cfg = self.config

        events: list[str] = []

        risk_index = (
            risk.risk_index
            if risk.risk_index != 255
            else 0
        )

        # ---------------------------------------------------------------
        # CAUTION hysteresis
        # ---------------------------------------------------------------
        self._t_caution_enter.tick(
            risk_index >= cfg.caution_enter,
            dt_s,
        )

        self._t_caution_exit.tick(
            risk_index < cfg.caution_exit,
            dt_s,
        )

        if (
            not self.caution_active
            and self._t_caution_enter.value
            >= cfg.caution_enter_hold_s
        ):
            self.caution_active = True
            events.append("CAUTION_ENTER")

        elif (
            self.caution_active
            and self._t_caution_exit.value
            >= cfg.caution_exit_hold_s
        ):
            self.caution_active = False
            events.append("CAUTION_EXIT")

        # ---------------------------------------------------------------
        # Cooling stage timers
        # ---------------------------------------------------------------
        for threshold, timer in self._t_enter.items():
            timer.tick(
                risk_index >= threshold,
                dt_s,
            )

        for threshold, timer in self._t_exit.items():
            timer.tick(
                risk_index < threshold,
                dt_s,
            )

        candidate = cfg.stages[0].name

        for stage in cfg.stages[1:]:
            held = self._t_enter[
                stage.enter_threshold
            ].value

            if (
                risk_index >= stage.enter_threshold
                and held >= stage.enter_hold_s
            ):
                candidate = stage.name

        # ---------------------------------------------------------------
        # Emergency latch
        # Hard trigger or manual SOS.
        # Risk >=95 becomes candidate C4 and is also latched here so that
        # C4 has no automatic release.
        # ---------------------------------------------------------------
        hard_trigger = (
            risk.hard_trigger
            or manual.manual_sos
        )

        emergency_stage = self.emergency_stage

        risk_c4 = (
            emergency_stage is not None
            and risk_index
            >= emergency_stage.enter_threshold
        )

        if (
            (hard_trigger or risk_c4)
            and not self.emergency_latched
        ):
            self.emergency_latched = True

            if manual.manual_sos:
                self.emergency_reason = "manual_sos"
            elif risk.hard_trigger:
                self.emergency_reason = "hard_trigger"
            else:
                self.emergency_reason = "risk_c4"

            events.append("EMERGENCY_ENTER")

        if self.emergency_latched:
            self.stage = (
                emergency_stage.name
                if emergency_stage is not None
                else self.highest_stage
            )

        else:
            current_idx = cfg.stage_index(
                self.stage
            )

            candidate_idx = cfg.stage_index(
                candidate
            )

            if candidate_idx > current_idx:
                self.stage = candidate
                events.append(
                    f"COOLING_{self.stage}"
                )

            else:
                current = cfg.stages[
                    current_idx
                ]

                if (
                    current.exit_threshold is not None
                    and self._t_exit[
                        current.exit_threshold
                    ].value >= current.exit_hold_s
                    and (
                        self.commander_recovery_confirm
                        or not current.exit_requires_commander
                    )
                ):
                    if current.exit_requires_commander:
                        self.commander_recovery_confirm = False

                    self.stage = cfg.stages[
                        current_idx - 1
                    ].name

                    events.append(
                        f"COOLING_{self.stage}"
                    )

        # ---------------------------------------------------------------
        # Command arbitration
        # ---------------------------------------------------------------
        risk_fan = cfg.stage(
            self.stage
        ).fan_percent

        commanded_fan = risk_fan
        reason = CoolReason.RISK_FSM

        if self.emergency_latched:
            commanded_fan = 100
            reason = CoolReason.EMERGENCY

        elif manual.commander_fan_percent is not None:
            commanded_fan = max(
                risk_fan,
                min(
                    100,
                    max(
                        0,
                        manual.commander_fan_percent,
                    ),
                ),
            )

            reason = CoolReason.COMMANDER

        if manual.test_mode:
            reason = CoolReason.TEST

        if manual.safety_stop:
            commanded_fan = 0
            reason = CoolReason.SAFETY_STOP
            events.append("SAFETY_STOP")

        # ---------------------------------------------------------------
        # Unified DeviceState
        # ---------------------------------------------------------------
        if self.emergency_latched:
            device_state = DeviceState.EMERGENCY

        elif self.stage != self.lowest_stage:
            device_state = DeviceState.COOLING

        elif self.caution_active:
            device_state = DeviceState.CAUTION

        else:
            device_state = DeviceState.NORMAL

        return FsmOutput(
            device_state=device_state,
            cooling_stage=self.stage,
            commanded_fan_percent=commanded_fan,
            cool_reason=reason,
            sos=self.emergency_latched,
            caution_active=self.caution_active,
            hard_trigger_latched=self.emergency_latched,
            events=events,
        )
