# HeatSentry

군 집단훈련 온열 위험 조기감지·자동냉각·안전 에스컬레이션 시스템

> **기준선 v2.0**: `HS-PDD-002`(제품개발 상세설계서), `HS-SIID-002`(시스템 통합·인터페이스 명세서).
> 이 저장소는 두 문서를 실행 가능한 코드로 옮긴 것이다. 자세한 설계 근거는 [docs/](docs/)와
> [firmware/api_contract.md](firmware/api_contract.md)를 참고한다.

HeatSentry는 질병을 진단하는 장비가 아니라, **손목 웨어러블의 생체신호 + 허리 능동 냉각 + 로컬
게이트웨이 + 관제 대시보드**를 하나의 폐루프로 묶어 온열 위험을 조기에 포착하고 자동 냉각·구조
절차를 연결하는 현장 안전 시스템이다.

```
센서 → RiskIndex → 자동 냉각 → 30초 재평가 → (미회복 시 상향) → SOS → 감사 로그
```

RiskIndex와 피부온도는 **의료 진단값이 아니다.** 열사병 의심 증상·의식 변화·무응답이 있으면 장치
점수와 무관하게 현장 응급절차가 항상 우선한다.

> 이전 버전(2026-07 이전, `HS-SIDD-001` v1.0)은 GPS 기반 분대 관제 컨셉이었다. v2.0에서는 개인
> 착용자의 손목+허리 폐루프와 로컬 관제로 범위를 좁히고 구체화했다 — 옛 설계는 git 이력에서 확인할
> 수 있다.

## 🧍🧍‍♀️ 멤버 구성

- 정여은(소프트웨어융합학과): 관제 대시보드·게이트웨이 서버 구축, RiskIndex/FSM 알고리즘 개발
- 박솔희(전자공학과)
- 이영재(전자공학과)
- 박주영(전자공학과)

## 아키텍처 한눈에 보기

| 서브시스템 | 책임 | 코드 |
| --- | --- | --- |
| SU-W 손목 노드 | 센서 품질·RiskIndex·상태·냉각 명령 | `algorithm/`, `node_sim/wrist_node.py` |
| SU-B 허리 노드 | 팬·PCM·전력·안전 정지·ACK | `node_sim/belt_node.py` |
| SU-E 환경 노드 | EnvHeatProxy(WBGT와는 별개 지표) | `node_sim/env_node.py` |
| SU-G 게이트웨이 | BLE 집계·저장·WebSocket | `server/` |
| SU-D 대시보드 | 경보·확인·로그·내보내기 | `dashboard/` |

실제 nRF52840 BLE 하드웨어가 아직 없는 개발 단계이므로, `node_sim/`이 손목·허리 노드의 판정·안전
로직을 소프트웨어로 그대로 재현하고 게이트웨이와 HTTP로 통신한다. 인터페이스 계약(바이트 레이아웃,
GATT 서비스, 오류코드)은 `common/`에 있고, 나중에 실물 BLE로 옮길 때도 그대로 재사용된다. 자세한
매핑은 [docs/architecture.md](docs/architecture.md) 참고.

## 저장소 구조

```
common/       바이너리 패킷(HS_STATUS/COOL_CMD/COOL_ACK), 해시체인, 오류코드, 게이트웨이 스키마
algorithm/    RiskIndex v0.2 엔진, 기준선(Baseline), 안전 상태기계(FSM), 설정값
server/       게이트웨이(FastAPI): REST v2 + WebSocket + 역할기반 확인 + SQLite 해시체인 로그
node_sim/     손목/허리/환경 노드 시뮬레이터 + 결정적 시험 시나리오(T01~T10)
tests/        pytest — 패킷, 해시체인, RiskIndex, FSM, 게이트웨이 API, 시나리오 통합 시험
dashboard/    React + TypeScript 관제 대시보드 (REST v2 + WebSocket)
docs/         제품 개념·아키텍처·알고리즘·시연 시나리오·데이터 설계 문서
firmware/     펌웨어 인터페이스 계약(ICD 요약, 실제 C/C++ 포팅 시 기준)
```

## 실행 방법

### 1) 게이트웨이 (FastAPI)

```bash
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r server/requirements.txt
uvicorn server.app.main:app --reload --port 8000
```

실장 환경에서는 장치별 비밀키를 반드시 등록한다. 키가 비어 있으면 시뮬레이터 호환을 위한
개발 모드이며 `/ingest/*` 인증이 수행되지 않는다.

```bash
export HEATSENTRY_DEVICE_KEYS='{"HS-W-001":"change-this-device-secret"}'
export HEATSENTRY_DEVICE_KEY='change-this-device-secret'  # node_sim 실행 터미널
export HEATSENTRY_CORS_ORIGINS='http://127.0.0.1:5173'
```

장치 키가 설정되면 모든 `/ingest/*` 요청은 `X-HS-Device-Key`가 일치해야 한다. 텔레메트리는
장치별 `sequence`가 증가할 때만 반영되므로, BLE/HTTP 재전송이 현재 상태나 감사 이벤트를
중복으로 덮어쓰지 않는다.

### 2) 손목+허리 노드 시뮬레이터

```bash
# 새 터미널, 같은 가상환경
python -m node_sim.run_demo --scenario T03 --fast
```

`--scenario`는 `T01`~`T08`, `T10` 중 하나(표는 [docs/demo_scenario.md](docs/demo_scenario.md)).
`--fast`는 3~5분 걸리는 기준선 측정을 6~9초로 줄이는 개발용 플래그이며 실제 시연에는 쓰지 않는다.

### 3) 대시보드 (React + Vite)

```bash
cd dashboard
npm install
npm run dev
```

브라우저에서 `http://localhost:5173`(vite 기본 포트)로 접속하면 실시간 장치 카드, 냉각 상태,
이벤트 로그(해시체인), 확인/응급 해제 콘솔이 표시된다. 우측 상단 역할 선택기로
observer/commander/tester/maintainer를 바꿔가며 권한 분리를 확인할 수 있다(HMI-001).

### 4) 테스트

```bash
# 파이썬 (common/algorithm/server/node_sim 전체)
pip install -r server/requirements.txt   # pytest 포함
pytest -q

# 대시보드 타입체크·린트·빌드
cd dashboard
npm run build
npx eslint .
```

## 핵심 설계 문서

- [docs/concept.md](docs/concept.md) — 제품 개념, 서브시스템 책임, 안전 경계
- [docs/architecture.md](docs/architecture.md) — 인터페이스 목록, 상태기계, 명령 중재, 코드 매핑
- [docs/ai_pipeline.md](docs/ai_pipeline.md) — RiskIndex v0.2 공식·가중치·품질 게이트·기준선
- [docs/demo_scenario.md](docs/demo_scenario.md) — 실행 방법, 시험 벡터 ↔ 시나리오 매핑, 140초 시연 대본
- [docs/aar_design.md](docs/aar_design.md) — 데이터 보존, 해시체인 무결성, 내보내기, 개인정보 최소화
- [firmware/api_contract.md](firmware/api_contract.md) — GATT 서비스, 패킷 바이트 레이아웃, 오류코드, 저하 모드

## 안전 경계 (요약)

1. 대시보드는 Emergency를 자동 해제할 수 없다 — 관제의 "해제" 버튼은 감사 기록만 남기고, 실제
   EMERGENCY 래치는 허리 노드의 물리 버튼(현장 확인)으로만 풀린다.
2. "알림 확인"과 "응급 해제"는 다른 버튼·다른 권한(commander)이다.
3. 자동 냉각(강제 대응)이 실패해도 수동 정지와 구조 절차는 항상 유지된다.
4. RiskIndex/피부온도는 의료 진단값이 아니다 — 현장 응급절차가 항상 장치 판정보다 우선한다.

## 개발 단계

| 단계 | 목표 | 상태 |
| --- | --- | --- |
| P0 기능증명 | 신호·팬 확인 | `node_sim/`으로 소프트웨어 상 완료 |
| P1 대회 MVP | 8주 폐루프 시연 | 본 커밋 기준 `algorithm/`+`server/`+`node_sim/`+`dashboard/` 폐루프 완성, 실물 BLE/하드웨어 통합은 다음 단계 |
| P2 현장 확장 | 다중 인원·장거리 | 범위 밖(LoRa/KR920, BLE Mesh, 다중 착용자) |

## 참고자료

부품 사양과 안전·환경 지표의 1차 출처는 `HS-PDD-002`/`HS-SIID-002` 문서의 참고자료 절(NIOSH
열 스트레스 권고, NIOSH/OSHA WBGT 안내, nRF52840/MAX86141/TMP117/ICM-42688-P/SHT41/INA260/
BQ24074/Raspberry Pi 5/Wio-E5 데이터시트)을 따른다. 구매·인증·현장 적용 전 최신 개정본을
재확인한다.
