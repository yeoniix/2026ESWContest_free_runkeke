"""현재 ESP32 LoRa 패킷을 RiskIndex 입력으로 변환한다.

실물 35바이트 패킷에는 6특징 중 3개가 없다 — HRV(패킷에 RMSSD 필드 없음),
ActivityLoad(IMU 미탑재), EnvHeatProxy(DHT 온습도 센서가 동작하지 않아
하드웨어에서 제거됨). 이 어댑터는 없는 값을 0으로 가정하지 않고, 남은
3특징(HR 편차·피부온도 상승률·GSR 변화)에 가중치를 재분배한 HARDWARE_CONFIG를
쓴다. 자세한 근거는 risk_config.py의 HARDWARE_WEIGHTS 주석 참고.

벨트 펌웨어는 자체 임계값으로 별도의 상태 판정을 하고 그 결과를 패킷에 실어
보낸다(GloveTelemetryPacket.belt_state). 이 어댑터가 계산하는 RiskIndex v0.3과는
판정 기준이 다르므로, 둘은 서로를 덮어쓰지 않고 나란히 관제로 올라간다.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from heatsentry.algorithm.baseline import Baseline, BaselineBuilder, BaselineSample
from heatsentry.algorithm.risk_config import HARDWARE_CONFIG, RiskConfig
from heatsentry.algorithm.risk_engine import RiskEngine, RiskResult, SensorSample
from heatsentry.common.glove_packets import GloveTelemetryPacket

GSR_DIFF_FULL_SCALE = 300.0
SLOPE_WINDOW_MS = 60_000


@dataclass(frozen=True)
class HardwareRiskReading:
    """한 LoRa 패킷에서 만든 RiskIndex 판정 결과."""

    sample: SensorSample
    risk: RiskResult | None
    baseline_ready: bool
    quality: dict[str, int]


def env_heat_proxy(air_temp_c: float, humidity_percent: float) -> float:
    """온습도만으로 만든 상대 열부하이며 WBGT로 표시하지 않는다.

    현재 벨트 하드웨어에는 DHT가 없어 이 함수를 타지 않는다. 환경 센서가
    다시 붙거나 SU-E 환경 노드 값이 주입되면 그대로 재사용한다.
    """
    proxy = (air_temp_c - 20.0) / 20.0 + (humidity_percent - 40.0) / 200.0
    return max(0.0, min(1.0, proxy))


def normalize_gsr_diff(gsr_diff: int) -> float:
    """장갑 부팅 시 보정한 GSR 차이를 0~1 범위로 정규화한다."""
    return max(0.0, min(1.0, gsr_diff / GSR_DIFF_FULL_SCALE))


class HardwareRiskAdapter:
    """35바이트 ESP32 데이터용 기준선·추세·RiskIndex 상태 보관 객체."""

    def __init__(self, config: RiskConfig = HARDWARE_CONFIG) -> None:
        self.config = config
        self.engine = RiskEngine(config)
        self.baseline_builder = BaselineBuilder(config.baseline)
        self.baseline: Baseline | None = None
        self._skin_history: deque[tuple[int, float]] = deque()
        self._last_monotonic_ms: int | None = None

    def _skin_slope(self, skin_temp_c: float, monotonic_ms: int, skin_valid: bool) -> float:
        if not skin_valid:
            self._skin_history.clear()
            return 0.0

        self._skin_history.append((monotonic_ms, skin_temp_c))
        cutoff = monotonic_ms - SLOPE_WINDOW_MS
        while len(self._skin_history) > 1 and self._skin_history[0][0] < cutoff:
            self._skin_history.popleft()

        first_ms, first_temp = self._skin_history[0]
        elapsed_ms = monotonic_ms - first_ms
        if elapsed_ms <= 0:
            return 0.0
        return (skin_temp_c - first_temp) * 60_000.0 / elapsed_ms

    def update(
        self,
        packet: GloveTelemetryPacket,
        monotonic_ms: int,
    ) -> HardwareRiskReading:
        """패킷 수신 시 호출한다. 기준선 전에는 ``risk``가 ``None``이다."""
        glove_valid = packet.glove_available and packet.finger_detected and 45 <= packet.bpm <= 180
        dht_valid = packet.dht_available
        ppg_quality = 100 if glove_valid else 0
        eda_quality = 100 if glove_valid else 0
        skin_slope = self._skin_slope(packet.skin_temp_c, monotonic_ms, glove_valid)

        # DHT가 다시 붙으면 air_temp_c/humidity_percent가 값을 돌려주므로
        # 환경 열부하가 자동으로 살아난다. 현재 펌웨어에서는 둘 다 None이다.
        if dht_valid and packet.air_temp_c is not None and packet.humidity_percent is not None:
            env_proxy = env_heat_proxy(packet.air_temp_c, packet.humidity_percent)
        else:
            env_proxy = None

        sample = SensorSample(
            hr_bpm=float(packet.bpm),
            hrv_rmssd=None,
            skin_temp_c=packet.skin_temp_c,
            skin_temp_slope_c_per_min=skin_slope,
            eda_delta_norm=normalize_gsr_diff(packet.gsr_diff),
            activity_load=None,
            env_heat_proxy=env_proxy,
            manual_sos=packet.emergency_active,
            quality_ppg=ppg_quality,
            quality_eda=eda_quality,
            skin_temp_stale_s=0.0 if glove_valid else self.config.quality.skin_temp_stale_s + 1.0,
            imu_ok=False,
            quality_env=100 if dht_valid else 0,
        )

        if self._last_monotonic_ms is None:
            dt_s = 1.0
        else:
            dt_s = max(0.0, (monotonic_ms - self._last_monotonic_ms) / 1000.0)
        self._last_monotonic_ms = monotonic_ms

        if self.baseline is None:
            self.baseline_builder.add_sample(
                BaselineSample(
                    hr_bpm=sample.hr_bpm,
                    hrv_rmssd=None,
                    skin_temp_c=sample.skin_temp_c,
                    eda_norm=sample.eda_delta_norm,
                    quality_ppg=sample.quality_ppg,
                    quality_eda=sample.quality_eda,
                ),
                dt_s=dt_s,
            )
            if self.baseline_builder.is_ready() or self.baseline_builder.is_expired():
                self.baseline = self.baseline_builder.build()

        risk = self.engine.evaluate(sample, self.baseline) if self.baseline is not None else None
        quality = {
            "ppg": ppg_quality,
            "skin": 100 if glove_valid else 0,
            "eda": eda_quality,
            "imu": 0,
            "env": 100 if dht_valid else 0,
        }
        return HardwareRiskReading(
            sample=sample,
            risk=risk,
            baseline_ready=self.baseline is not None,
            quality=quality,
        )
