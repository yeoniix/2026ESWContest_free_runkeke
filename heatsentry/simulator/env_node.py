"""환경 노드(SU-E) 시뮬레이터.

출처: HS-PDD-002 p7 "환경 노드와 WBGT 표기 원칙". SHT41(온습도) 값은
EnvHeatProxy로만 부르고, WBGT라는 이름은 검증용 계측기(WBGT_ref)에만 쓴다.
RiskEngine에는 항상 EnvHeatProxy(0~1)만 들어가고 WBGT_ref는 시험 로그
비교용으로만 존재한다 — 둘을 절대 같은 값으로 취급하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EnvReading:
    temp_c: float
    rh_percent: float
    env_heat_proxy: float  # 0~1, RiskEngine 입력
    wbgt_ref_c: float | None  # 검증용 계측기 값(시험 로그 비교 전용, 있을 때만)


class EnvNode:
    """SHT41 기반 EnvHeatProxy 생성. RadiantProxy(흑구온도)는 P1 범위 밖이라 생략."""

    def __init__(self, base_temp_c: float = 29.0, base_rh: float = 65.0) -> None:
        self.base_temp_c = base_temp_c
        self.base_rh = base_rh

    def read(self, heat_load: float = 0.0, wbgt_ref_c: float | None = None) -> EnvReading:
        """heat_load(0~1)는 시나리오가 "더 더운 훈련장" 상황을 만들 때 쓰는 배율이다."""
        temp_c = self.base_temp_c + heat_load * 6.0
        rh = min(95.0, self.base_rh + heat_load * 10.0)

        # 정식 WBGT 공식이 아니라, 상대적 열부하 추세만 나타내는 대체지표다.
        # (건구온도만으로는 WBGT를 낼 수 없다 — PDD p7 "온습도 센서 하나로 계산한
        # 값은 규격상 WBGT가 아니다".)
        proxy = (temp_c - 20.0) / 20.0 + (rh - 40.0) / 200.0
        env_heat_proxy = max(0.0, min(1.0, proxy))

        return EnvReading(
            temp_c=round(temp_c, 2),
            rh_percent=round(rh, 1),
            env_heat_proxy=round(env_heat_proxy, 4),
            wbgt_ref_c=wbgt_ref_c,
        )
