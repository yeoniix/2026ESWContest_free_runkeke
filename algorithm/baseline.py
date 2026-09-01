"""개인 기준선(Baseline) 생성.

출처: HS-PDD-002 p5 "9.4 기준선 생성"(문서 내 번호는 SIDD 잔재이나 PDD 본문
"위험도 엔진과 데이터 전략" 절의 서술과 동일한 규칙), SYS-001.

- 착용 후 3~5분, PPG Quality>=70 & EDA Quality>=40인 구간만 사용
- 중앙값과 MAD(Median Absolute Deviation)로 이상치 배제
- 기준선이 만들어지지 않으면 제한 모드로 동작하고 재착용을 요청
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from algorithm.risk_config import BaselineConfig, DEFAULT_CONFIG


@dataclass(frozen=True)
class Baseline:
    hr_median: float
    hr_mad: float
    hrv_median: float
    skin_temp_median: float
    eda_median: float
    sample_count: int


@dataclass
class BaselineSample:
    hr_bpm: float
    hrv_rmssd: float
    skin_temp_c: float
    eda_norm: float
    quality_ppg: int
    quality_eda: int


def _median_mad(values: list[float]) -> tuple[float, float]:
    med = statistics.median(values)
    mad = statistics.median(abs(v - med) for v in values) if len(values) > 1 else 0.0
    return med, mad


class BaselineBuilder:
    """SensorTask가 3~5분간 축적한 표본으로 기준선을 만드는 상태 보관 객체.

    firmware/simulator의 WristNode가 BASELINE 상태일 때 매 초 add_sample()을 호출하고,
    is_ready()가 True가 되면 build()로 Baseline을 확정한다.
    """

    def __init__(self, config: BaselineConfig = DEFAULT_CONFIG.baseline) -> None:
        self._config = config
        self._samples: list[BaselineSample] = []
        self._elapsed_s = 0.0

    def add_sample(self, sample: BaselineSample, dt_s: float = 1.0) -> None:
        self._elapsed_s += dt_s
        if (
            sample.quality_ppg >= self._config.ppg_quality_min
            and sample.quality_eda >= self._config.eda_quality_min
        ):
            self._samples.append(sample)

    def is_ready(self) -> bool:
        return self._elapsed_s >= self._config.min_minutes * 60 and len(self._samples) >= 30

    def is_expired(self) -> bool:
        """max_minutes를 넘겼는데도 준비되지 않으면 제한 모드로 전환해야 한다."""
        return self._elapsed_s >= self._config.max_minutes * 60

    def build(self) -> Baseline | None:
        if not self._samples:
            return None
        hr_med, hr_mad = _median_mad([s.hr_bpm for s in self._samples])
        hrv_med, _ = _median_mad([s.hrv_rmssd for s in self._samples])
        skin_med, _ = _median_mad([s.skin_temp_c for s in self._samples])
        eda_med, _ = _median_mad([s.eda_norm for s in self._samples])
        return Baseline(
            hr_median=hr_med,
            hr_mad=max(hr_mad, 1.0),  # 0으로 나누기 방지 하한
            hrv_median=hrv_med,
            skin_temp_median=skin_med,
            eda_median=eda_med,
            sample_count=len(self._samples),
        )
