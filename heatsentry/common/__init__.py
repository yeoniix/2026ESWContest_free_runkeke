"""HeatSentry v2.0 공용 라이브러리.

HS-SIID-002 (시스템 통합·인터페이스 명세서 v2.0) 기준선을 코드로 옮긴 패키지.
손목/허리/환경 노드 시뮬레이터(heatsentry/simulator)와 게이트웨이(heatsentry/server)가 이 모듈을 함께 참조해
바이너리 패킷, 해시체인, 오류코드, 게이트웨이 데이터 계약이 항상 같은 정의를 쓰도록 한다.
"""

# 버전 상수는 각자 하나의 출처만 갖는다. 여기서 값을 다시 적으면 조용히 어긋난다.
#
#   PROTOCOL_VERSION      packets.py         — BLE/LoRa 패킷 헤더 버전
#   GATEWAY_SCHEMA_VERSION 이 파일           — 게이트웨이 데이터 계약 버전
#   RISK_CONFIG_VERSION   algorithm/risk_config.py
#       가중치·임계값이 바뀔 때 오른다. common은 algorithm에 의존하지 않는
#       하위 계층이므로 여기서 다시 내보내지 않는다 — 필요하면
#       `from heatsentry.algorithm.risk_config import RISK_CONFIG_VERSION`.
from heatsentry.common.packets import PROTOCOL_VERSION

GATEWAY_SCHEMA_VERSION = "2.0"

__all__ = ["PROTOCOL_VERSION", "GATEWAY_SCHEMA_VERSION"]
