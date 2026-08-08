from algorithm.baseline import Baseline
from algorithm.risk_engine import RiskEngine, SensorSample
from common.errors import ErrorCode

BASELINE = Baseline(
    hr_median=100, hr_mad=5, hrv_median=45, skin_temp_median=36.0, eda_median=0.1, sample_count=180
)


def _sample(**overrides) -> SensorSample:
    base = dict(
        hr_bpm=100, hrv_rmssd=45, skin_temp_c=36.0, skin_temp_slope_c_per_min=0.0,
        eda_delta_norm=0.0, activity_load=0.1, env_heat_proxy=0.1,
    )
    base.update(overrides)
    return SensorSample(**base)


def test_resting_sample_gives_low_risk():
    engine = RiskEngine()
    result = engine.evaluate(_sample(), BASELINE)
    assert result.risk_index < 20
    assert result.sensor_limited is False
    assert result.hard_trigger is False


def test_risk_index_is_bounded_0_100():
    engine = RiskEngine()
    result = engine.evaluate(
        _sample(hr_bpm=300, skin_temp_slope_c_per_min=5, eda_delta_norm=5, activity_load=5, env_heat_proxy=5),
        BASELINE,
    )
    assert 0 <= result.risk_index <= 100


def test_low_ppg_quality_excludes_hr_and_hrv_features():
    # ALG-002: PPG Quality<70 -> HR 제외(E101), 가중치 재정규화
    engine = RiskEngine()
    result = engine.evaluate(_sample(hr_bpm=200, quality_ppg=50), BASELINE)
    assert ErrorCode.E101 in result.active_errors
    assert result.contributions["HR_dev"] == 0
    assert result.contributions["HRV_suppression"] == 0
    # HR_dev(0.25) + HRV_suppression(0.10) 제외 -> valid_weight = 0.65
    assert result.valid_weight < 0.70


def test_sensor_limited_when_valid_weight_below_060():
    # ALG-002: valid_weight < 0.60 -> SENSOR_LIMITED
    engine = RiskEngine()
    result = engine.evaluate(
        _sample(quality_ppg=30, quality_eda=10, imu_ok=False),  # HR/HRV/EDA/Activity 모두 제외
        BASELINE,
    )
    # 남는 것은 SkinTemp_slope(0.20) + EnvHeatProxy(0.20) = 0.40
    assert result.valid_weight < 0.60
    assert result.sensor_limited is True


def test_hard_trigger_on_manual_sos():
    engine = RiskEngine()
    result = engine.evaluate(_sample(manual_sos=True), BASELINE)
    assert result.hard_trigger is True


def test_hard_trigger_requires_all_three_fall_conditions():
    engine = RiskEngine()
    # 낙상만으로는 HardTrigger가 아니다 (무동작·무응답이 함께 있어야 함)
    result = engine.evaluate(_sample(fall_detected=True, no_motion=False, no_response=False), BASELINE)
    assert result.hard_trigger is False

    result2 = engine.evaluate(_sample(fall_detected=True, no_motion=True, no_response=True), BASELINE)
    assert result2.hard_trigger is True
