"""통합 오류코드.

출처: HS-SIID-002 p8 표8 "통합 오류코드", 저하 모드 원칙 1~4.
각 코드가 RiskIndex 입력 중 어떤 항목의 가중치를 제외시키는지(quality gate)와
로컬/관제 동작 문구를 한곳에 모아, heatsentry/simulator와 heatsentry/server가 같은 정의를 참조하게 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorCode(str, Enum):
    E101 = "E101"  # PPG Quality<70 10초
    E102 = "E102"  # EDA 접촉 손실
    E103 = "E103"  # 피부온도 오류
    E104 = "E104"  # IMU 응답 없음
    E105 = "E105"  # 환경 센서 데이터 없음/저품질
    E201 = "E201"  # BLE 10초 손실
    E301 = "E301"  # 팬 과전류/정지
    E302 = "E302"  # 배터리 10% 이하
    E303 = "E303"  # 접촉부 저온
    E401 = "E401"  # 로그 저장 실패


@dataclass(frozen=True)
class ErrorInfo:
    code: ErrorCode
    condition: str
    local_action: str
    remote_display: str
    excludes_feature: str | None  # RiskIndex 특징 중 재정규화에서 제외되는 항목


ERROR_TABLE: dict[ErrorCode, ErrorInfo] = {
    ErrorCode.E101: ErrorInfo(
        ErrorCode.E101,
        "PPG Quality<70 10초",
        "HR 제외·SENSOR_LIMITED 가능",
        "노란 품질",
        excludes_feature="HR_dev",
    ),
    ErrorCode.E102: ErrorInfo(
        ErrorCode.E102,
        "EDA 접촉 손실",
        "EDA 가중치 제외",
        "회색 입력",
        excludes_feature="EDA_delta",
    ),
    ErrorCode.E103: ErrorInfo(
        ErrorCode.E103,
        "피부온도 오류",
        "온도 가중치 제외",
        "센서 오류",
        excludes_feature="SkinTemp_slope",
    ),
    ErrorCode.E104: ErrorInfo(
        ErrorCode.E104,
        "IMU 응답 없음",
        "낙상 비활성·위험표시",
        "기능 제한",
        excludes_feature="ActivityLoad",
    ),
    ErrorCode.E105: ErrorInfo(
        ErrorCode.E105,
        "환경 온습도 데이터 없음 또는 품질 미달",
        "EnvHeatProxy 가중치 제외",
        "환경 센서 오류",
        excludes_feature="EnvHeatProxy",
    ),
    ErrorCode.E201: ErrorInfo(
        ErrorCode.E201,
        "BLE 10초 손실",
        "재연결·팬 안전타이머",
        "통신 손실",
        excludes_feature=None,
    ),
    ErrorCode.E301: ErrorInfo(
        ErrorCode.E301,
        "팬 과전류/정지",
        "팬 OFF",
        "긴급 장치오류",
        excludes_feature=None,
    ),
    ErrorCode.E302: ErrorInfo(
        ErrorCode.E302,
        "배터리 10% 이하",
        "출력 제한",
        "저배터리",
        excludes_feature=None,
    ),
    ErrorCode.E303: ErrorInfo(
        ErrorCode.E303,
        "접촉부 저온",
        "팬 OFF·PCM 분리 안내",
        "안전 알림",
        excludes_feature=None,
    ),
    ErrorCode.E401: ErrorInfo(
        ErrorCode.E401,
        "로그 저장 실패",
        "RAM 큐·재시도",
        "무결성 경고",
        excludes_feature=None,
    ),
}

# 저하 모드 원칙 (SIID p8) — 코드 곳곳에서 이 상수를 참조해 동작을 결정한다.
MIN_VALID_WEIGHT = 0.60  # 미만이면 SENSOR_LIMITED (ALG-002)
BLE_COMMS_LOST_S = 10  # 10초 손실 시 COMMS_LOST
FAN_SAFETY_TIMER_S = 60  # 60초 후 팬 안전 타이머(20%로 하향)
FAN_SAFETY_LEVEL = 50
