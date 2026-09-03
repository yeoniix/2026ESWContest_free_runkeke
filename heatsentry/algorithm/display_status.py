"""Small OLED/LCD display text mapper."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DisplayStatus:
    line1: str
    line2: str


def select_display_cause(
    contributions: dict[str, float],
) -> str:

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

    name, value = max(
        contributions.items(),
        key=lambda item: item[1],
    )

    if value <= 0:
        return "CHECK BODY"

    return labels.get(
        name,
        "CHECK BODY",
    )


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

    if (
        state == "EMERGENCY"
        or cooling_stage == "C4"
    ):
        return DisplayStatus(
            "EMERGENCY",
            "SOS FAN 100%",
        )

    if (
        state == "SENSOR_CHECK"
        or not finger_detected
        or (
            hr_bpm is not None
            and hr_bpm <= 0
        )
    ):
        return DisplayStatus(
            "SENSOR CHECK",
            "WEAR GLOVE",
        )

    if state == "BOOT":
        return DisplayStatus(
            "HEATSENTRY",
            "STARTING",
        )

    if state == "BASELINE":
        return DisplayStatus(
            "BASELINE",
            "STAY STILL",
        )

    if (
        state == "COOLING"
        and cooling_stage == "C3"
    ):
        return DisplayStatus(
            "HIGH RISK",
            "FAN 100%",
        )

    if (
        state == "COOLING"
        and cooling_stage == "C2"
    ):
        return DisplayStatus(
            "DANGER",
            f"FAN 100% {cause}",
        )

    if (
        state == "COOLING"
        and cooling_stage == "C1"
    ):
        return DisplayStatus(
            "COOLING",
            f"FAN 50% {cause}",
        )

    if state == "CAUTION":
        return DisplayStatus(
            "CAUTION",
            cause,
        )

    if state == "NORMAL":
        if (
            hr_bpm is not None
            and skin_temp_c is not None
        ):
            return DisplayStatus(
                "NORMAL",
                f"HR {hr_bpm:.0f} "
                f"T{skin_temp_c:.1f}C",
            )

        return DisplayStatus(
            "NORMAL",
            f"FAN {fan_percent}%",
        )

    return DisplayStatus(
        state,
        cause,
    )
