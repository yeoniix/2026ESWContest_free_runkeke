"""허리 냉각 노드(SU-B) 시뮬레이터.

출처: HS-PDD-002 p6 "허리 냉각 노드 상세 설계"(Fail-safe), HS-SIID-002 p4
"연결·재전송 정책"(idempotent ACK), p8 표8 오류코드(E301/E302/E303).

SU-B 책임: "팬·PCM·전력·안전 정지·ACK". 하지 않는 일: "위험도 최종 판정" —
그래서 이 클래스는 RiskIndex나 FSM을 전혀 모른다. 오직 COOL_CMD를 받아
안전 규칙을 적용하고 COOL_ACK을 돌려주는 일만 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from common.errors import ErrorCode, FAN_SAFETY_LEVEL, FAN_SAFETY_TIMER_S
from common.packets import AckResult, CoolAck, CoolCmd


@dataclass
class BeltNode:
    device_id: str = "HS-B-001"
    battery_percent: int = 100
    belt_temp_centic: int = 3200  # 32.00C
    voltage_mv: int = 7400

    fan_pwm_percent: int = 0
    current_ma: int = 0

    overcurrent_fault: bool = False  # 시나리오가 켜는 고장 주입
    low_temp_fault: bool = False
    manual_stop_active: bool = False

    _processed_cmds: dict[int, CoolAck] = field(default_factory=dict)
    _since_last_cmd_s: float = 0.0
    _fan_safety_applied: bool = False

    def _compute_current_ma(self, pwm: int) -> int:
        return int(40 + pwm * 4.4)  # PDD 7.1 전력예산의 블로워 팬 100~300mA/PWM 단계별과 정합

    def press_physical_stop(self) -> None:
        """SIID/PDD "수동 제어: 2초 길게 누름, 즉시 팬 정지". SOS 상태는 유지된다."""
        self.manual_stop_active = True
        self.fan_pwm_percent = 0
        self.current_ma = 0

    def release_physical_stop(self) -> None:
        self.manual_stop_active = False

    def handle_cmd(self, cmd: CoolCmd, monotonic_ms: int) -> CoolAck:
        self._since_last_cmd_s = 0.0
        self._fan_safety_applied = False

        active_errors: list[ErrorCode] = []
        if self.overcurrent_fault:
            active_errors.append(ErrorCode.E301)
        if self.low_temp_fault:
            active_errors.append(ErrorCode.E303)
        if self.battery_percent <= 10:
            active_errors.append(ErrorCode.E302)

        if cmd.cmd_id in self._processed_cmds:
            # 표4 정책 #2: 동일 cmd_id 재수신 -> 팬 재시작 없이 현재 결과만 ACK.
            cached = self._processed_cmds[cmd.cmd_id]
            return CoolAck(
                cmd_id=cmd.cmd_id,
                sequence=cmd.sequence,
                result=AckResult.IDEMPOTENT_REPEAT,
                actual_pwm=cached.actual_pwm,
                current_ma=cached.current_ma,
                belt_temp_centic=self.belt_temp_centic,
                error_bits=_error_bits(active_errors),
            )

        if self.manual_stop_active:
            actual_pwm = 0
        elif self.overcurrent_fault:
            # E301: 팬 과전류/정지 -> 팬 OFF.
            actual_pwm = 0
        elif self.low_temp_fault:
            # E303: 접촉부 저온 -> 팬 OFF·PCM 분리 안내.
            actual_pwm = 0
        else:
            actual_pwm = max(0, min(100, cmd.level))

        self.fan_pwm_percent = actual_pwm
        self.current_ma = self._compute_current_ma(actual_pwm)

        result = (
            AckResult.REJECTED_SAFETY
            if (self.overcurrent_fault or self.low_temp_fault or self.manual_stop_active)
            else AckResult.OK
        )

        ack = CoolAck(
            cmd_id=cmd.cmd_id,
            sequence=cmd.sequence,
            result=result,
            actual_pwm=actual_pwm,
            current_ma=self.current_ma,
            belt_temp_centic=self.belt_temp_centic,
            error_bits=_error_bits(active_errors),
        )
        self._processed_cmds[cmd.cmd_id] = ack
        return ack

    def tick(self, dt_s: float, comms_ok: bool) -> list[str]:
        """매 초 호출. 허리 MCU는 손목과 별도 워치독을 갖는다(PDD "Watchdog·안전 타이머").

        comms_ok=False가 fan_safety_timer_s(60초)간 이어지면, 새 명령이 없어도
        스스로 팬을 20%로 낮춘다(Fail-safe). 반환값은 이번 tick에 새로 발생한
        사건 이름 목록이다.
        """
        events: list[str] = []
        if comms_ok:
            self._since_last_cmd_s = 0.0
            self._fan_safety_applied = False
        else:
            self._since_last_cmd_s += dt_s
            if (
                self._since_last_cmd_s >= FAN_SAFETY_TIMER_S
                and self.fan_pwm_percent > FAN_SAFETY_LEVEL
                and not self._fan_safety_applied
            ):
                self.fan_pwm_percent = FAN_SAFETY_LEVEL
                self.current_ma = self._compute_current_ma(FAN_SAFETY_LEVEL)
                self._fan_safety_applied = True
                events.append("FAN_SAFETY_TIMER")
        return events


def _error_bits(errors: list[ErrorCode]) -> int:
    """u8 error_bits: E301=bit0, E302=bit1, E303=bit2 (BELT_STATUS/COOL_ACK 공용, 허리 관련 오류만)."""
    mapping = {ErrorCode.E301: 0, ErrorCode.E302: 1, ErrorCode.E303: 2}
    bits = 0
    for e in errors:
        bits |= 1 << mapping[e]
    return bits
