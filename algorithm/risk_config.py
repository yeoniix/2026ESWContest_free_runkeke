"""RiskIndex v0.3 / FSM 설정값.

형상관리 원칙(HS-SIID-002 표1): risk_config_version은 가중치·임계값이 바뀔 때마다
증가한다. 이 파일 하나만 바꾸면 되도록 숫자를 전부 여기 모아둔다.

출처가 명시된 값은 그대로 옮긴 것이고, "설계 기본값(미확정)"이라고 적힌 값은
문서에 정확한 숫자가 없어 통합팀이 정해야 하는 자리다 — v1.0(HS-SIDD-001)의
히스테리시스 표를 이어받아 기본값을 채워 넣었으니, 실제 시험 데이터가 쌓이면
CR로 조정하고 risk_config_version을 올린다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

RISK_CONFIG_VERSION = "0.3.0"


@dataclass(frozen=True)
class RiskWeights:
    """PDD 표9 RiskIndex 기본 가중치. 합계 1.00."""

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
    """PDD p5 "센서 배치와 품질 게이트" 및 E101~E105."""

    ppg_quality_min: int = 70  # 미만이면 HR/HRV 제외 (E101)
    eda_quality_min: int = 40  # 미만이면 EDA 제외 (E102)
    skin_temp_stale_s: float = 3.0  # 이상이면 피부온도 제외 (E103)
    env_quality_min: int = 50  # DHT 등 환경 센서 품질 미달 시 EnvHeatProxy 제외 (E105)
    min_valid_weight: float = 0.60  # 미만이면 SENSOR_LIMITED (ALG-002)


@dataclass(frozen=True)
class BaselineConfig:
    """PDD p5 "기준선 생성" / SYS-001."""

    min_minutes: float = 3.0
    max_minutes: float = 5.0
    ppg_quality_min: int = 70
    eda_quality_min: int = 40


@dataclass(frozen=True)
class CoolingStageConfig:
    """SIID p7 표7 냉각 상태 기준 (=PDD p6 표7과 동일 수치).

    enter_hold_s: 진입 임계를 이 시간(초) 이상 유지해야 진입.
    exit_threshold / exit_hold_s: 회복 시 하향 조건(히스테리시스).
    fan_percent: 팬 PWM 목표값.
    """

    name: str
    enter_threshold: int
    enter_hold_s: float
    fan_percent: int
    exit_threshold: int | None
    exit_hold_s: float | None


@dataclass(frozen=True)
class FsmConfig:
    """그림2(통합 상태 전이)와 표7(냉각 상태 기준)을 하나로 합친 설정.

    WARNING 진입 임계값은 v2.0 문서에 숫자가 명시돼 있지 않다(그림에는 상자만
    있음). v1.0(HS-SIDD-001 9.5절)의 Attention(60)+Warning(75)을 WARNING 한
    단계로 합치면서, 진입은 완화된 쪽(60)을 기본값으로 채택했다 — 설계 기본값,
    CR 대상.
    """

    warning_enter: int = 60
    warning_enter_hold_s: float = 10.0
    warning_exit: int = 55
    warning_exit_hold_s: float = 30.0

    # CTL-001: "RiskIndex 80 이상 10초 지속 시 냉각 C1" — 문서 확정값.
    stages: tuple[CoolingStageConfig, ...] = field(
        default_factory=lambda: (
            CoolingStageConfig("C0", enter_threshold=0, enter_hold_s=0, fan_percent=0,
                                exit_threshold=None, exit_hold_s=None),
            CoolingStageConfig("C1", enter_threshold=80, enter_hold_s=10, fan_percent=50,
                                exit_threshold=70, exit_hold_s=30),
            CoolingStageConfig("C2", enter_threshold=90, enter_hold_s=10, fan_percent=100,
                                exit_threshold=80, exit_hold_s=30),
            CoolingStageConfig("C3", enter_threshold=90, enter_hold_s=60, fan_percent=100,
                                exit_threshold=85, exit_hold_s=60),
            CoolingStageConfig("C4", enter_threshold=95, enter_hold_s=0, fan_percent=100,
                                exit_threshold=None, exit_hold_s=None),
        )
    )

    emergency_threshold: int = 95  # C4 진입 임계 (HardTrigger와는 별개 경로)
    emergency_max_latency_s: float = 5.0  # COM-002/SYS-006: 낙상+무동작/SOS -> 5초 이내
    c2_unrecovered_s: float = 60.0  # C2 60초 미회복 -> C3

    # Fail-safe (SIID p4 "연결·재전송 정책" #4, PDD p6 "Fail-safe")
    ble_comms_lost_s: float = 10.0
    fan_safety_timer_s: float = 60.0
    fan_safety_level: int = 50

    # 명령 재전송 (SIID p4 #1, PDD 성공지표 #2)
    ack_timeout_ms: float = 500.0
    ack_max_retries: int = 3


@dataclass(frozen=True)
class RiskConfig:
    version: str = RISK_CONFIG_VERSION
    weights: RiskWeights = field(default_factory=RiskWeights)
    quality: QualityGates = field(default_factory=QualityGates)
    baseline: BaselineConfig = field(default_factory=BaselineConfig)
    fsm: FsmConfig = field(default_factory=FsmConfig)


DEFAULT_CONFIG = RiskConfig()
