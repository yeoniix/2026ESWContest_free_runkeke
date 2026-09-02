"""작은 장갑 LCD/OLED에 표시할 짧고 결정적인 상태·원인 문구.

상태 판정(FSM)과 화면 문구를 분리해 두면, 화면이 바뀌어도 안전 제어 조건은
변하지 않는다. 영문 대문자는 대부분의 128x64 OLED 기본 글꼴에서 바로 표시된다.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DisplayStatus:
    line1: str
    line2: str


def select_display_cause(contributions: dict[str, float]) -> str:
    """RiskIndex에 가장 많이 기여한 유효 신호 하나를 화면용 원인으로 고른다."""
    labels = {
        "HR_dev": "HR HIGH",
        "HRV_suppression": "HR CHANGE",
        "SkinTemp_slope": "TEMP UP",
        "EDA_delta": "GSR UP",
        "EnvHeatProxy": "HOT ENV",
        "ActivityLoad": "ACTIVE",
    }
    if not contributions:
        return "CHECK BODY"
    name, value = max(contributions.items(), key=lambda item: item[1])
    return labels.get(name, "CHECK BODY") if value > 0 else "CHECK BODY"


def make_display_status(
    state: str,
    cooling_stage: str,
    fan_percent: int,
    *,
    cause: str = "CHECK BODY",
    finger_detected: bool = True,
    hr_bpm: float | None = None,
    skin_temp_c: float | None = None,
) -> DisplayStatus:
    """상태와 냉각 단계를 2줄 LCD 표시용으로 변환한다.

    상태는 사용자가 해야 할 행동이고, cause는 위험 판단의 가장 큰 원인이다.
    """
    if state == "EMERGENCY" or cooling_stage == "C4":
        return DisplayStatus("EMERGENCY", "SOS  FAN 100%")
    if not finger_detected or (hr_bpm is not None and hr_bpm <= 0):
        return DisplayStatus("SENSOR_CHECK", "WEAR GLOVE")
    if state == "BOOT":
        return DisplayStatus("HEATSENTRY", "STARTING")
    if state == "BASELINE":
        return DisplayStatus("BASELINE", "STAY STILL")
    if cooling_stage == "C3":
        return DisplayStatus("HIGH RISK", "FAN 100%")
    if cooling_stage == "C2":
        return DisplayStatus("DANGER", f"FAN 100% {cause}")
    if cooling_stage == "C1":
        return DisplayStatus("COOLING", f"FAN 50% {cause}")
    if state == "WARNING":
        return DisplayStatus("CAUTION", cause)
    if hr_bpm is not None and skin_temp_c is not None:
        return DisplayStatus("NORMAL", f"HR {hr_bpm:.0f} T{skin_temp_c:.1f}C")
    return DisplayStatus("NORMAL", f"FAN {fan_percent}%")
