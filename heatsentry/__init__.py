"""HeatSentry TAC — 온열 위험 조기감지·자동냉각·안전 에스컬레이션 시스템.

서브패키지 구성:

- ``heatsentry.common``     장치 간 계약: 바이너리 패킷, 오류코드, 해시체인, 게이트웨이 스키마
- ``heatsentry.algorithm``  RiskIndex 엔진, 개인 기준선, 안전 상태기계(FSM), 하드웨어 어댑터
- ``heatsentry.simulator``  손목/허리/환경 노드 시뮬레이터 (실물 ESP32 펌웨어의 레퍼런스 구현)
- ``heatsentry.server``     게이트웨이(FastAPI): REST v2 + WebSocket + 해시체인 감사 로그

임베디드 C/C++ 펌웨어는 파이썬 패키지가 아니므로 저장소 최상위 ``firmware/``에 둔다.
"""
