"""안전 상태기계 + 명령 중재.

출처:
- HS-SIID-002 p7 그림2/표7 "상태기계와 명령 중재" (품질 게이트 -> 설명 가능한
  지수 -> 자동 개입 -> 사람 확인, 명령 중재 우선순위).
- HS-PDD-002 p6 표7 "냉각 상태 기준"(C0~C4), Fail-safe 규칙.

핵심 설계: RiskIndex 임계값별로 "몇 초 연속 그 임계값 이상이었는가"를 추적하는
HoldTimer만으로 C0~C4 승급/강등과 WARNING 진입/해제를 모두 표현한다. 같은 조건
(risk>=90)에서 파생되는 C2(10초)와 C3(60초)는 timer 하나를 공유해도 자연스럽게
동시에 계산된다 — 이는 90 이상이 60초 유지되면 그 안에 이미 10초 지점도 지났기
때문이다.

EMERGENCY(C4) 해제는 이 파일이 자동으로 하지 않는다("금지 사항: 대시보드가
Emergency를 자동 해제해서는 안 된다", SIID p7). close_emergency()는 서버의
/api/v2/emergency/{id}/close 핸들러가 현장 확인자 정보와 함께 명시적으로 호출할
때만 실행된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from algorithm.risk_config import FsmConfig, DEFAULT_CONFIG
from algorithm.risk_engine import RiskResult
from common.packets import CoolReason, DeviceState

_STAGE_ORDER = ["C0", "C1", "C2", "C3", "C4"]
# 실제 블로워의 저출력 구간은 체감 냉각 효과가 작으므로, 현장 제어는
# OFF -> 50% -> 100% 두 출력 단계로 단순화한다. C2/C3의 구분은 출력이 아니라
# 위험 지속 시간과 LCD/관제 경보 수준을 구분하기 위해 유지한다.
_STAGE_FAN = {"C0": 0, "C1": 50, "C2": 100, "C3": 100, "C4": 100}


class HoldTimer:
    """조건이 계속 참인 시간을 초 단위로 누적하고, 거짓이 되면 0으로 리셋한다."""

    def __init__(self) -> None:
        self.value = 0.0

    def tick(self, condition: bool, dt_s: float) -> float:
        self.value = self.value + dt_s if condition else 0.0
        return self.value


@dataclass
class ManualInputs:
    """명령 중재 표7의 우선순위 1/2/4/5 입력. 우선순위 3(RiskIndex)은 FSM이 스스로 계산한다."""

    safety_stop: bool = False  # 우선순위1: 수동 STOP·과전류·저온(허리에서 보고)
    manual_sos: bool = False  # 우선순위2 성분: 수동 SOS 버튼
    commander_fan_percent: int | None = None  # 우선순위4: 지휘관 수동 냉각(0/50/100)
    test_mode: bool = False  # 우선순위5


@dataclass
class FsmOutput:
    device_state: DeviceState
    cooling_stage: str  # C0~C4
    commanded_fan_percent: int
    cool_reason: CoolReason
    sos: bool
    warning_active: bool
    hard_trigger_latched: bool
    events: list[str] = field(default_factory=list)  # 이번 tick에 새로 발생한 사건


class HeatSentryFsm:
    def __init__(self, config: FsmConfig = DEFAULT_CONFIG.fsm) -> None:
        self.config = config
        self.stage = "C0"
        self.warning_active = False
        self.emergency_latched = False
        self.emergency_reason: str | None = None

        self._t_ge_60 = HoldTimer()
        self._t_lt_55 = HoldTimer()
        self._t_ge_80 = HoldTimer()
        self._t_lt_70 = HoldTimer()
        self._t_ge_90 = HoldTimer()
        self._t_lt_80 = HoldTimer()
        self._t_lt_85 = HoldTimer()

        self.commander_recovery_confirm = False  # C3->C2 하향 시 필요 (표7 "지휘관 확인")

    def confirm_recovery(self) -> None:
        """지휘관이 회복 추세를 확인했다는 표시. C3->C2 하향 조건에 쓰인다."""
        self.commander_recovery_confirm = True

    def close_emergency(self) -> None:
        """서버가 현장 확인자 ID·시각·사유를 검증한 뒤에만 호출해야 한다."""
        self.emergency_latched = False
        self.emergency_reason = None
        self.stage = "C3"  # 해제 직후에도 즉시 OFF로 점프하지 않고 한 단계 냉각 유지

    def update(
        self, risk: RiskResult, dt_s: float, manual: ManualInputs | None = None
    ) -> FsmOutput:
        manual = manual or ManualInputs()
        cfg = self.config
        events: list[str] = []
        risk_index = risk.risk_index if risk.risk_index != 255 else 0

        # --- WARNING 진입/해제 (히스테리시스) ---
        self._t_ge_60.tick(risk_index >= cfg.warning_enter, dt_s)
        self._t_lt_55.tick(risk_index < cfg.warning_exit, dt_s)
        if not self.warning_active and self._t_ge_60.value >= cfg.warning_enter_hold_s:
            self.warning_active = True
            events.append("WARNING_ENTER")
        elif self.warning_active and self._t_lt_55.value >= cfg.warning_exit_hold_s:
            self.warning_active = False
            events.append("WARNING_EXIT")

        # --- 냉각 단계 승급 후보 계산 (표7) ---
        self._t_ge_80.tick(risk_index >= 80, dt_s)
        self._t_lt_70.tick(risk_index < 70, dt_s)
        self._t_ge_90.tick(risk_index >= 90, dt_s)
        self._t_lt_80.tick(risk_index < 80, dt_s)
        self._t_lt_85.tick(risk_index < 85, dt_s)

        candidate = "C0"
        if self._t_ge_80.value >= 10:
            candidate = "C1"
        if self._t_ge_90.value >= 10:
            candidate = "C2"
        if self._t_ge_90.value >= cfg.c2_unrecovered_s:
            candidate = "C3"
        if risk_index >= cfg.emergency_threshold:
            candidate = "C4"

        hard_trigger = risk.hard_trigger or manual.manual_sos
        if hard_trigger and not self.emergency_latched:
            self.emergency_latched = True
            self.emergency_reason = "hard_trigger" if risk.hard_trigger else "manual_sos"
            events.append("EMERGENCY_ENTER")

        if self.emergency_latched:
            self.stage = "C4"
        else:
            current_idx = _STAGE_ORDER.index(self.stage)
            candidate_idx = _STAGE_ORDER.index(candidate)
            if candidate_idx > current_idx:
                self.stage = candidate
                events.append(f"COOLING_{self.stage}")
            elif candidate_idx <= current_idx:
                # 강등은 현재 단계 하나만, 각자의 해제 조건으로만 판단한다.
                if self.stage == "C1" and self._t_lt_70.value >= 30:
                    self.stage = "C0"
                    events.append("COOLING_C0")
                elif self.stage == "C2" and self._t_lt_80.value >= 30:
                    self.stage = "C1"
                    events.append("COOLING_C1")
                elif (
                    self.stage == "C3"
                    and self._t_lt_85.value >= 60
                    and self.commander_recovery_confirm
                ):
                    self.stage = "C2"
                    self.commander_recovery_confirm = False
                    events.append("COOLING_C2")
                # C4는 close_emergency()로만 벗어난다.

        # --- 명령 중재 (표7 우선순위) ---
        risk_fan = _STAGE_FAN[self.stage]
        commanded_fan = risk_fan
        reason = CoolReason.RISK_FSM

        if self.emergency_latched:
            commanded_fan = 100
            reason = CoolReason.EMERGENCY
        elif manual.commander_fan_percent is not None:
            # 우선순위4: 지휘관 수동 냉각은 안전 한계 내에서 RiskIndex 권고보다
            # 세게 틀 수는 있어도(보조 목적) 자동 판정을 아예 무시하진 않는다.
            commanded_fan = max(risk_fan, min(100, max(0, manual.commander_fan_percent)))
            reason = CoolReason.COMMANDER

        if manual.test_mode:
            reason = CoolReason.TEST

        if manual.safety_stop:
            # 우선순위1: 최우선. 팬 OFF, 논리적 stage/타이머는 보존한다.
            commanded_fan = 0
            reason = CoolReason.SAFETY_STOP
            events.append("SAFETY_STOP")

        if self.emergency_latched:
            device_state = DeviceState.EMERGENCY
        elif self.stage != "C0":
            device_state = DeviceState.COOLING
        elif self.warning_active:
            device_state = DeviceState.WARNING
        else:
            device_state = DeviceState.NORMAL

        return FsmOutput(
            device_state=device_state,
            cooling_stage=self.stage,
            commanded_fan_percent=commanded_fan,
            cool_reason=reason,
            sos=self.emergency_latched,
            warning_active=self.warning_active,
            hard_trigger_latched=self.emergency_latched,
            events=events,
        )
