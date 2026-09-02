"""RiskIndex v0.3 엔진.

출처: HS-PDD-002 p8 "위험도 엔진과 데이터 전략".

    RiskIndex = 100 * Sum(w_i * q_i * feature_i) / Sum(w_i * q_i)
    valid_weight = Sum(w_i * q_i)
    if valid_weight < 0.60: state = SENSOR_LIMITED
    HardTrigger = manual_sos OR (fall AND no_motion AND no_response)

ALG-001: "RiskIndex 0~100과 입력 품질·기여도를 1초마다 출력" — RiskResult에
contributions(설명 가능한 기여도)를 함께 담아 이 요구를 만족시킨다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from heatsentry.algorithm.baseline import Baseline
from heatsentry.algorithm.risk_config import RiskConfig, DEFAULT_CONFIG
from heatsentry.common.errors import ErrorCode

# 특징 정규화 포화 상수 — 문서에 정확한 값이 없어 통합팀이 정할 자리(설계 기본값).
HR_DEV_SATURATION_STD = 4.0  # 개인 기준 심박 표준편차의 몇 배에서 feature=1.0
HRV_SUPPRESSION_FULL_DROP = 1.0  # RMSSD가 baseline 대비 100% 감소하면 feature=1.0
SKIN_SLOPE_SATURATION_C_PER_MIN = 0.3  # PDD SkinTemp_slope 정의: "5분 피부온도 상승률"
EDA_DELTA_SATURATION = 1.0  # 호출측이 이미 0~1 델타로 정규화해 넘긴다고 가정


@dataclass
class SensorSample:
    """WristNode가 매 초 SensorTask/BioProcessTask 처리 결과로 만드는 입력.

    실제 펌웨어라면 100Hz PPG/50Hz IMU 등을 여기까지 미리 처리해 온다
    (PDD 표5 "신호 처리 주기" 참고). RiskEngine은 이미 1Hz로 정리된 값만 본다.
    """

    hr_bpm: float
    hrv_rmssd: float | None
    skin_temp_c: float
    skin_temp_slope_c_per_min: float
    eda_delta_norm: float  # 개인 기준 대비 변화량, 0~1로 이미 정규화됨
    activity_load: float | None  # IMU 기반 활동 강도 0~1
    env_heat_proxy: float | None  # EnvHeatProxy 0~1 (WBGT_ref와 별도, PDD p7)

    fall_detected: bool = False
    no_motion: bool = False
    no_response: bool = False
    manual_sos: bool = False

    quality_ppg: int = 100
    quality_eda: int = 100
    skin_temp_stale_s: float = 0.0
    imu_ok: bool = True
    quality_env: int = 100


@dataclass
class RiskResult:
    risk_index: int  # 0~100, invalid(모든 입력 제외)이면 255
    valid_weight: float
    sensor_limited: bool
    hard_trigger: bool
    contributions: dict[str, float]
    features: dict[str, float]
    active_errors: list[ErrorCode] = field(default_factory=list)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def compute_features(sample: SensorSample, baseline: Baseline) -> dict[str, float]:
    hr_z = (sample.hr_bpm - baseline.hr_median) / baseline.hr_mad
    hr_dev = _clamp01(hr_z / HR_DEV_SATURATION_STD)

    if sample.hrv_rmssd is not None and baseline.hrv_median > 0:
        hrv_drop_ratio = (baseline.hrv_median - sample.hrv_rmssd) / baseline.hrv_median
    else:
        hrv_drop_ratio = 0.0
    hrv_suppression = _clamp01(hrv_drop_ratio / HRV_SUPPRESSION_FULL_DROP)

    skin_slope = _clamp01(
        sample.skin_temp_slope_c_per_min / SKIN_SLOPE_SATURATION_C_PER_MIN
    )

    eda_delta = _clamp01(
        (sample.eda_delta_norm - baseline.eda_median) / EDA_DELTA_SATURATION
    )

    activity_load = _clamp01(sample.activity_load) if sample.activity_load is not None else 0.0
    env_heat_proxy = _clamp01(sample.env_heat_proxy) if sample.env_heat_proxy is not None else 0.0

    return {
        "HR_dev": hr_dev,
        "HRV_suppression": hrv_suppression,
        "SkinTemp_slope": skin_slope,
        "EDA_delta": eda_delta,
        "ActivityLoad": activity_load,
        "EnvHeatProxy": env_heat_proxy,
    }


def _quality_multipliers(sample: SensorSample, config: RiskConfig) -> tuple[dict[str, float], list[ErrorCode]]:
    gates = config.quality
    errors: list[ErrorCode] = []

    ppg_ok = sample.quality_ppg >= gates.ppg_quality_min
    if not ppg_ok:
        errors.append(ErrorCode.E101)
    q_hr = (sample.quality_ppg / 100.0) if ppg_ok else 0.0

    eda_ok = sample.quality_eda >= gates.eda_quality_min
    if not eda_ok:
        errors.append(ErrorCode.E102)
    q_eda = (sample.quality_eda / 100.0) if eda_ok else 0.0

    skin_ok = sample.skin_temp_stale_s <= gates.skin_temp_stale_s
    if not skin_ok:
        errors.append(ErrorCode.E103)
    q_skin = 1.0 if skin_ok else 0.0

    activity_ok = sample.imu_ok and sample.activity_load is not None
    if not activity_ok:
        errors.append(ErrorCode.E104)
    q_activity = 1.0 if activity_ok else 0.0

    hrv_ok = ppg_ok and sample.hrv_rmssd is not None
    q_hrv = (sample.quality_ppg / 100.0) if hrv_ok else 0.0

    env_ok = (
        sample.env_heat_proxy is not None
        and sample.quality_env >= gates.env_quality_min
    )
    if not env_ok:
        errors.append(ErrorCode.E105)
    q_env = (sample.quality_env / 100.0) if env_ok else 0.0

    return (
        {
            "HR_dev": q_hr,
            "HRV_suppression": q_hrv,
            "SkinTemp_slope": q_skin,
            "EDA_delta": q_eda,
            "ActivityLoad": q_activity,
            "EnvHeatProxy": q_env,
        },
        errors,
    )


class RiskEngine:
    def __init__(self, config: RiskConfig = DEFAULT_CONFIG) -> None:
        self.config = config

    def evaluate(self, sample: SensorSample, baseline: Baseline) -> RiskResult:
        weights = self.config.weights.as_dict()
        features = compute_features(sample, baseline)
        quality, active_errors = _quality_multipliers(sample, self.config)

        contributions: dict[str, float] = {}
        valid_weight = 0.0
        weighted_sum = 0.0
        for name, w in weights.items():
            q = quality[name]
            wq = w * q
            valid_weight += wq
            contribution = wq * features[name]
            weighted_sum += contribution
            contributions[name] = contribution

        sensor_limited = valid_weight < self.config.quality.min_valid_weight

        if valid_weight <= 0:
            risk_index = 255  # invalid
        else:
            risk_index = round(100 * weighted_sum / valid_weight)
            risk_index = max(0, min(100, risk_index))

        hard_trigger = sample.manual_sos or (
            sample.fall_detected and sample.no_motion and sample.no_response
        )

        return RiskResult(
            risk_index=risk_index,
            valid_weight=round(valid_weight, 4),
            sensor_limited=sensor_limited,
            hard_trigger=hard_trigger,
            contributions={k: round(v, 4) for k, v in contributions.items()},
            features={k: round(v, 4) for k, v in features.items()},
            active_errors=active_errors,
        )
