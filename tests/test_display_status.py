from algorithm.display_status import make_display_status, select_display_cause


def test_display_shows_two_physical_fan_levels():
    assert make_display_status("COOLING", "C1", 50, cause="HR HIGH").line2 == "FAN 50% HR HIGH"
    assert make_display_status("COOLING", "C2", 100, cause="TEMP UP").line2 == "FAN 100% TEMP UP"


def test_emergency_overrides_other_display_details():
    display = make_display_status("EMERGENCY", "C4", 100)
    assert display.line1 == "EMERGENCY"
    assert "100%" in display.line2


def test_sensor_not_worn_has_priority_over_normal_reading():
    display = make_display_status("NORMAL", "C0", 0, finger_detected=False, hr_bpm=80)
    assert display.line1 == "SENSOR CHECK"
    assert display.line2 == "WEAR GLOVE"


def test_largest_risk_contribution_becomes_display_cause():
    cause = select_display_cause({"HR_dev": 0.1, "SkinTemp_slope": 0.16})
    assert cause == "TEMP UP"
