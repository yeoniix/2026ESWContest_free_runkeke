"""RiskIndex / FSM configuration.

State naming is unified to:
    BOOT / BASELINE / NORMAL / CAUTION /
    COOLING / EMERGENCY / SENSOR_CHECK

Cooling intensity remains independent:
    C0 / C1 / C2 / C3 / C4
"""

from __future__ import annotations

from dataclasses import dataclass, field


RISK_CONFIG_VERSION = "0.4.0"


@dataclass(frozen=True)
class RiskWeights:
    HR_dev: float = 0.25
    HRV_suppression: float = 0.10
    SkinTemp_slope: float = 0.20
    EDA_delta: float = 0.10
    ActivityLoad: float = 0.15
    EnvHeatProxy: float = 0.20

    def as_dict(self) -> dict[str, float]:
        return {
            "HR_dev": self.HR_dev,
            "HRV_suppression": self.HRV_suppression,
            "SkinTemp_slope": self.SkinTemp_slope,
            "EDA_delta": self.EDA_delta,
            "ActivityLoad": self.ActivityLoad,
            "EnvHeatProxy": self.EnvHeatProxy,
        }


@dataclass(frozen=True)
class QualityGates:
    ppg_quality_min: int = 70
    eda_quality_min: int = 40
    skin_temp_stale_s: float = 3.0
    env_quality_min: int = 50
    min_valid_weight: float = 0.60


@dataclass(frozen=True)
class BaselineConfig:
    min_minutes: float = 3.0
    max_minutes: float = 5.0
    ppg_quality_min: int = 70
    eda_quality_min: int = 40


@dataclass(frozen=True)
class CoolingStageConfig:
    name: str
    enter_threshold: int
    enter_hold_s: float
    fan_percent: int
    exit_threshold: int | None
    exit_hold_s: float | None
    exit_requires_commander: bool = False


@dataclass(frozen=True)
class FsmConfig:
    """CAUTION + C0~C4 configuration."""

    # CAUTION:
    # Risk >= 60 for 10 sec
    # exit when Risk < 55 for 30 sec
    caution_enter: int = 60
    caution_enter_hold_s: float = 10.0
    caution_exit: int = 55
    caution_exit_hold_s: float = 30.0

    stages: tuple[CoolingStageConfig, ...] = field(
        default_factory=lambda: (
            CoolingStageConfig(
                "C0",
                enter_threshold=0,
                enter_hold_s=0,
                fan_percent=0,
                exit_threshold=None,
                exit_hold_s=None,
            ),
            CoolingStageConfig(
                "C1",
                enter_threshold=80,
                enter_hold_s=10,
                fan_percent=50,
                exit_threshold=70,
                exit_hold_s=30,
            ),
            CoolingStageConfig(
                "C2",
                enter_threshold=90,
                enter_hold_s=10,
                fan_percent=100,
                exit_threshold=80,
                exit_hold_s=30,
            ),
            CoolingStageConfig(
                "C3",
                enter_threshold=90,
                enter_hold_s=60,
                fan_percent=100,
                exit_threshold=85,
                exit_hold_s=60,
                exit_requires_commander=True,
            ),
            CoolingStageConfig(
                "C4",
                enter_threshold=95,
                enter_hold_s=0,
                fan_percent=100,
                exit_threshold=None,
                exit_hold_s=None,
            ),
        )
    )

    emergency_max_latency_s: float = 5.0

    ble_comms_lost_s: float = 10.0
    fan_safety_timer_s: float = 60.0
    fan_safety_level: int = 50

    ack_timeout_ms: float = 500.0
    ack_max_retries: int = 3

    @property
    def stage_names(self) -> tuple[str, ...]:
        return tuple(
            stage.name
            for stage in self.stages
        )

    def stage_index(
        self,
        name: str,
    ) -> int:
        return self.stage_names.index(name)

    def stage(
        self,
        name: str,
    ) -> CoolingStageConfig:
        return self.stages[
            self.stage_index(name)
        ]


@dataclass(frozen=True)
class RiskConfig:
    version: str = RISK_CONFIG_VERSION
    weights: RiskWeights = field(
        default_factory=RiskWeights
    )
    quality: QualityGates = field(
        default_factory=QualityGates
    )
    baseline: BaselineConfig = field(
        default_factory=BaselineConfig
    )
    fsm: FsmConfig = field(
        default_factory=FsmConfig
    )


DEFAULT_CONFIG = RiskConfig()


HARDWARE_WEIGHTS = RiskWeights(
    HR_dev=0.45,
    HRV_suppression=0.0,
    SkinTemp_slope=0.37,
    EDA_delta=0.18,
    ActivityLoad=0.0,
    EnvHeatProxy=0.0,
)

HARDWARE_CONFIG = RiskConfig(
    weights=HARDWARE_WEIGHTS
)
