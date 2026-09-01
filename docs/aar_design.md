# 데이터 저장·무결성·AAR 설계

> 기준 문서: HS-SIID-002 v2.0 "데이터 저장·무결성·개인정보". 구현: `common/hash_chain.py`,
> `server/app/db.py`, `server/app/state.py`, `server/app/routes_api_v2.py`(`/api/v2/export`).
>
> 옛 기획(README 구버전)의 "AAR 안전 로그 분석" 개념을 그대로 계승하되, 저장 대상을
> GPS 분대 좌표가 아니라 손목/허리 폐루프 이벤트로 바꿨다.

## 보존 정책

| 레코드 | 보존 | 필수 필드 | 이 저장소의 테이블 |
| --- | --- | --- | --- |
| Telemetry | 로컬 24~72h | 신호·품질·상태·버전 | `telemetry` (`server/app/db.py`) |
| Event | 대회 전 기간 | seq·utc·원인·이전해시 | `events` (해시체인 적용) |
| Command/ACK | 대회 전 기간 | cmd_id·요청·실제값 | `command_acks` |
| User action | 대회 전 기간 | 역할·확인·사유 | `user_actions` |
| Raw PPG/IMU | 시험 세션만 | 익명 장치 ID·동의 | 범위 밖(P1, 손목 노드 로컬 로그로만 존재 가정) |

`Telemetry`는 보존 기간이 짧아 별도 정리(retention job)가 필요하지만, MVP 단계에서는 수동으로
DB 파일을 정리하는 것으로 충분하다고 판단해 자동 삭제는 구현하지 않았다 — 필요해지면
`server/app/db.py`에 정리 작업을 추가한다.

## 해시체인

```
event_hash = SHA256(previous_hash || canonical_json(event_without_hash))
canonical_json: UTF-8, sorted keys, no whitespace, fixed decimal precision(6자리)
```

- 구현: `common/hash_chain.py`. `append_event()`로 체인에 이어붙이고, `verify_chain()`으로
  변조 여부와 최초 불일치 인덱스를 확인한다.
- `GatewayStore`(서버)는 재시작 시 DB의 마지막 `event_hash`를 이어받아 체인이 끊기지 않게 한다
  (`server/app/state.py`의 `GatewayStore.__init__`).
- DAT-001(T10) "로그 변조 -> 해시체인 불일치 검출"은 `tests/test_hash_chain.py`와
  `tests/test_gateway_api.py::test_tamper_detected_via_verify_chain`이 회귀 테스트로 고정한다.

## 감사 추적: Command/ACK, User action

- `firmware/simulator/wrist_node.py`가 COOL_CMD를 보낼 때마다 `command_ack` 레코드를 만들어
  `POST /ingest/command_ack`로 게이트웨이에 남긴다 — 재전송 횟수(`retries`)까지 포함해
  COM-001("냉각 명령 성공률 99% 이상, 재전송 포함")을 증명할 수 있는 원자료가 된다.
- 대시보드의 "확인"(`/api/v2/alerts/{id}/ack`)과 "응급 해제 기록"
  (`/api/v2/emergency/{id}/close`)은 각각 `user_actions` 테이블에 역할(role)·행위자(actor_id)·
  사유(reason)를 남긴다. 두 행위는 서로 다른 엔드포인트·다른 권한(commander)이며, 응급 해제는
  사유와 현장 확인자 ID가 없으면 400으로 거부된다(HMI-001).

## 내보내기 (AAR/시험성적서용)

`POST /api/v2/export` (tester 권한)는 이벤트 로그를 CSV 또는 JSON으로 내보낸다
(`server/app/routes_api_v2.py`). 대시보드의 EventLog 패널에서 버튼 클릭으로 바로 다운로드할 수
있다(`dashboard/src/components/EventLog.tsx`). 내보내기 자체도 `user_actions`에 기록된다.

AAR 화면(위험 이벤트 타임라인, 조치까지 걸린 시간, 통신 두절 구간)은 이 이벤트 로그 위에 별도
프론트엔드 뷰로 만들 수 있다 — 필요한 원자료(`event_type`, `gateway_utc`, `monotonic_ms`,
`reason`, `payload`)는 이미 갖춰져 있으므로, P1 이후 대시보드에 "AAR" 탭을 추가하는 정도로
확장 가능하다.

## 개인정보 최소화

- 대시보드 기본 화면은 `device_id`·위험 단계만 표시한다(`DeviceCard.tsx`). 위치 범주·실명 연계는
  이 저장소 범위에 없다(v2.0 ICD 자체가 GPS 좌표를 아키텍처에서 제외했다 — 옛 기획의 GPS 분대
  지도 기능은 v2.0에서 명시적으로 빠졌다).
- Raw PPG/IMU는 애초에 게이트웨이로 전송하지 않는다 — `TelemetryV2` 스키마(`common/schema.py`)에
  원시 파형 필드가 없다. 손목 노드가 로컬에만 보관한다는 전제다.
