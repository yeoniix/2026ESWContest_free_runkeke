"""HeatSentry v2.0 공용 라이브러리.

HS-SIID-002 (시스템 통합·인터페이스 명세서 v2.0) 기준선을 코드로 옮긴 패키지.
손목/허리/환경 노드 시뮬레이터(heatsentry/simulator)와 게이트웨이(heatsentry/server)가 이 모듈을 함께 참조해
바이너리 패킷, 해시체인, 오류코드, 게이트웨이 데이터 계약이 항상 같은 정의를 쓰도록 한다.
"""

PROTOCOL_VERSION = 2
RISK_CONFIG_VERSION = "0.3.0"
GATEWAY_SCHEMA_VERSION = "2.0"
