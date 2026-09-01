"""시험 시나리오 생성기.

HS-SIID-002 표1의 test_vector 원칙("결과 재현 시 고정")에 맞춰 난수를 쓰지
않는다 — 모든 값은 tick 번호의 결정적 함수다. HS-PDD-002 표12(T01~T10)와
HS-SIID-002 표12(T01~T12)에 이름을 맞췄다.

각 함수는 RawTick 리스트를 반환한다. baseline_ticks는 호출측 RiskConfig의
baseline.min_minutes*60에 맞춰 넘겨준다(기본 180, --fast면 훨씬 짧게).

임계값을 실제로 넘기기 위한 hold 구간 수치(HOLD_C1/HOLD_C2)는
algorithm.risk_engine을 직접 돌려 RiskIndex가 원하는 구간(80대/90대)에
오도록 맞춘 값이다 — RiskIndex v0.2 가중치가 바뀌면 이 값들도 다시 맞춰야
한다(risk_config_version이 오르면 test_vector id도 함께 올린다, 표1).
"""

from __future__ import annotations

from .wrist_node import RawTick

REST_HR = 100.0
REST_HRV = 45.0
REST_SKIN = 36.0
REST_EDA = 0.1
REST_ACTIVITY = 0.15
REST_ENV = 0.3


def _rest_tick(**overrides) -> RawTick:
    base = dict(
        hr_bpm=REST_HR,
        hrv_rmssd=REST_HRV,
        skin_temp_c=REST_SKIN,
        skin_temp_slope_c_per_min=0.0,
        eda_delta_norm=0.05,
        activity_load=REST_ACTIVITY,
        env_heat_proxy=REST_ENV,
    )
    base.update(overrides)
    return RawTick(**base)


def baseline_phase(ticks: int, quality_ppg: int = 95, quality_eda: int = 90) -> list[RawTick]:
    return [_rest_tick(quality_ppg=quality_ppg, quality_eda=quality_eda) for _ in range(ticks)]


# RiskIndex ~= 81 (C1: >=80 진입, C2 90에는 못 미침)
_HOLD_C1 = dict(hr_bpm=185.0, hrv_rmssd=8.0, skin_temp_c=37.0, skin_temp_slope_c_per_min=0.28,
                eda_delta_norm=0.9, activity_load=0.2, env_heat_proxy=0.85)
# RiskIndex ~= 93 (C2: >=90 진입, 60초 유지 시 C3)
_HOLD_C2 = dict(hr_bpm=192.0, hrv_rmssd=2.0, skin_temp_c=37.6, skin_temp_slope_c_per_min=0.30,
                eda_delta_norm=1.0, activity_load=0.55, env_heat_proxy=1.0)


def t01_baseline_stability(baseline_ticks: int) -> list[RawTick]:
    """T01: 기준선 안정 -> VALID. 이후 30틱 더 안정 상태를 유지해 NORMAL을 확인한다."""
    return baseline_phase(baseline_ticks) + baseline_phase(30)


def t02_quality_gate(baseline_ticks: int) -> list[RawTick]:
    """T02: PPG/EDA 품질 동시 저하 -> valid_weight<0.60 -> SENSOR_LIMITED."""
    degraded = [_rest_tick(hr_bpm=150, quality_ppg=50, quality_eda=20) for _ in range(20)]
    recovered = baseline_phase(15)
    return baseline_phase(baseline_ticks) + degraded + recovered


def _ramp(start: float, end: float, ticks: int) -> list[float]:
    if ticks <= 1:
        return [end] * max(ticks, 0)
    step = (end - start) / (ticks - 1)
    return [start + step * i for i in range(ticks)]


def _ramp_ticks(target: dict, rise_ticks: int) -> list[RawTick]:
    hr = _ramp(REST_HR, target["hr_bpm"], rise_ticks)
    hrv = _ramp(REST_HRV, target["hrv_rmssd"], rise_ticks)
    skin = _ramp(REST_SKIN, target["skin_temp_c"], rise_ticks)
    slope = _ramp(0.0, target["skin_temp_slope_c_per_min"], rise_ticks)
    eda = _ramp(0.05, target["eda_delta_norm"], rise_ticks)
    act = _ramp(REST_ACTIVITY, target["activity_load"], rise_ticks)
    env = _ramp(REST_ENV, target["env_heat_proxy"], rise_ticks)
    return [
        _rest_tick(hr_bpm=hr[i], hrv_rmssd=hrv[i], skin_temp_c=skin[i], skin_temp_slope_c_per_min=slope[i],
                   eda_delta_norm=eda[i], activity_load=act[i], env_heat_proxy=env[i])
        for i in range(rise_ticks)
    ]


def _hold_ticks(target: dict, ticks: int, **extra) -> list[RawTick]:
    return [_rest_tick(**target, **extra) for _ in range(ticks)]


def t03_risk_rise(baseline_ticks: int) -> list[RawTick]:
    """T03: RiskIndex >=80 10초 지속 -> C1 (CTL-001)."""
    return baseline_phase(baseline_ticks) + _ramp_ticks(_HOLD_C1, 40) + _hold_ticks(_HOLD_C1, 30)


def t04_ack_loss(baseline_ticks: int) -> list[RawTick]:
    """T04: ACK 손실. 냉각 진입 구간 전체에 drop_ack_attempts를 걸어 두면,
    실제로 명령이 발생하는 tick에서만 재전송 로직이 관찰된다(표4 정책 #1)."""
    rise = t03_risk_rise(baseline_ticks)
    for t in rise[baseline_ticks:]:
        t.drop_ack_attempts = 2  # 500ms 재전송 2회까지는 유실, 3번째(=허용 한도 내) 성공
    return rise


def t05_cooling_safety(baseline_ticks: int) -> list[RawTick]:
    """T05: 냉각 중 팬 과전류 -> 팬 OFF(E301)."""
    rise = t03_risk_rise(baseline_ticks)
    fault_start = len(rise) - 15
    for i in range(fault_start, len(rise)):
        rise[i].belt_overcurrent = True
    return rise


def t06_recovery(baseline_ticks: int) -> list[RawTick]:
    """T06: 90->70 재생 -> 30초 후 단계 하향(C2->C1, 이어서 C1->C0).

    fall 구간은 90틱: 임계값을 실제로 넘어선 뒤에도 하향에 필요한 유지시간
    (30초/30초)만큼 여유가 남도록 여유폭을 둔다.
    """
    rise = _ramp_ticks(_HOLD_C2, 30)
    hold = _hold_ticks(_HOLD_C2, 15)
    fall = list(reversed(_ramp_ticks(_HOLD_C2, 90)))  # C2 hold부터 REST까지 대칭 하강
    return baseline_phase(baseline_ticks) + rise + hold + fall


def t07_unrecovered(baseline_ticks: int) -> list[RawTick]:
    """T07: C2 임계 60초 이상 유지 -> C3, 지휘관 확인 후에만 하향.

    fall 구간은 100틱: 85 밑으로 내려간 뒤에도 60초 연속 유지 조건을 채울 수
    있도록 t06보다 더 길게 잡는다(C3 하향 조건이 더 오래 걸리므로).
    """
    rise = _ramp_ticks(_HOLD_C2, 20)
    hold = _hold_ticks(_HOLD_C2, 90)  # >=90 유지 60초 이상 -> C3 진입 보장
    fall = list(reversed(_ramp_ticks(_HOLD_C2, 100)))
    for i in (5,):
        fall[i].commander_confirm_recovery = True
    return baseline_phase(baseline_ticks) + rise + hold + fall


def t08_fall_emergency(baseline_ticks: int) -> list[RawTick]:
    """T08: 낙상+무동작+무응답 -> HardTrigger -> 즉시 EMERGENCY (SYS-006/COM-002)."""
    normal_walk = [_rest_tick(hr_bpm=120, activity_load=0.4, skin_temp_slope_c_per_min=0.05) for _ in range(15)]
    impact = [_rest_tick(hr_bpm=150, activity_load=0.9, fall=True, no_motion=False, no_response=False)]
    aftermath = [
        _rest_tick(hr_bpm=160, activity_load=0.0, fall=True, no_motion=True, no_response=True)
        for _ in range(30)
    ]
    return baseline_phase(baseline_ticks) + normal_walk + impact + aftermath


def t10_integration(baseline_ticks: int, cycles: int = 3) -> list[RawTick]:
    """T10: 통합 폐루프를 cycles회 반복해 "N회 연속 성공"을 흉내 낸다."""
    ticks = baseline_phase(baseline_ticks)
    for _ in range(cycles):
        ticks += t03_risk_rise(0)
        ticks += t06_recovery(0)
    return ticks


SCENARIOS = {
    "T01": t01_baseline_stability,
    "T02": t02_quality_gate,
    "T03": t03_risk_rise,
    "T04": t04_ack_loss,
    "T05": t05_cooling_safety,
    "T06": t06_recovery,
    "T07": t07_unrecovered,
    "T08": t08_fall_emergency,
    "T10": t10_integration,
}
