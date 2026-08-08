"""노드 -> 게이트웨이 수집 엔드포인트.

IF-04(노드->게이트웨이, 원래는 BLE GATT 1s/이벤트)의 소프트웨어 대체 경로다.
실제 BLE Central 스택이 붙기 전까지 node_sim(손목/허리/환경 노드 시뮬레이터)이
여기로 HTTP POST를 보낸다. 사람이 쓰는 /api/v2/* 와 달리 역할(X-HS-Role) 검사를
하지 않는다 — 이 경로는 장치 자신이 호출하는 것이지 사용자가 호출하는 게 아니다.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from common.schema import TelemetryV2

router = APIRouter(prefix="/ingest", tags=["ingest"])


class EventIn(BaseModel):
    device_id: str
    monotonic_ms: int
    event_type: str
    reason: str = ""
    payload: dict = {}


class CommandAckIn(BaseModel):
    cmd_id: int
    device_id: str
    requested_level: int
    requested_reason: str
    actual_pwm: int
    current_ma: int
    result: str
    retries: int = 0


@router.post("/telemetry")
async def ingest_telemetry(telemetry: TelemetryV2, request: Request):
    await request.app.state.store.ingest_telemetry(telemetry)
    return {"status": "ok", "device_id": telemetry.device_id, "sequence": telemetry.sequence}


@router.post("/event")
async def ingest_event(event: EventIn, request: Request):
    record = await request.app.state.store.add_event(
        device_id=event.device_id,
        monotonic_ms=event.monotonic_ms,
        event_type=event.event_type,
        reason=event.reason,
        payload=event.payload,
    )
    return {"status": "ok", "seq": record["seq"], "event_hash": record["event_hash"]}


@router.post("/command_ack")
async def ingest_command_ack(record: CommandAckIn, request: Request):
    await request.app.state.store.record_command_ack(record.model_dump())
    return {"status": "ok"}
