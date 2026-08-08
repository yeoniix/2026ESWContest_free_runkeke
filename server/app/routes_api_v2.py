"""로컬 API v2 (HS-SIID-002 p6 표6).

Endpoint                          방식      권한
/api/v2/devices                   GET       observer
/api/v2/events                    GET       observer
/api/v2/alerts/{id}/ack           POST      commander
/api/v2/emergency/{id}/close      POST      commander
/api/v2/export                    POST      tester
/api/v2/config                    PUT       maintainer (서명된 설정)

ack와 emergency/close는 둘 다 "기록"이지 장치 제어가 아니다 — HMI-001과
p7 "금지 사항"을 지키기 위해 실제 안전 상태(FSM)는 여기서 절대 바꾸지 않는다.
자세한 설계 의도는 server/app/state.py 상단 docstring 참고.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from server.app.auth import get_actor_id, require_roles
from server.app.state import now_utc

router = APIRouter(prefix="/api/v2", tags=["api-v2"])

CONFIG_SECRET = os.environ.get("HEATSENTRY_CONFIG_SECRET", "dev-only-insecure-secret")


@router.get("/devices")
async def list_devices(request: Request, _role: str = Depends(require_roles("observer", "commander", "tester", "maintainer"))):
    store = request.app.state.store
    return [t.model_dump() for t in store.devices.values()]


@router.get("/events")
async def list_events(
    request: Request,
    device_id: str | None = None,
    event_type: str | None = None,
    since_seq: int = 0,
    _role: str = Depends(require_roles("observer", "commander", "tester", "maintainer")),
):
    store = request.app.state.store
    return store.list_events(device_id=device_id, event_type=event_type, since_seq=since_seq)


@router.get("/alerts")
async def list_alerts(request: Request, _role: str = Depends(require_roles("observer", "commander", "tester", "maintainer"))):
    """표6에는 없는 조회용 확장(gateway_schema patch) — 대시보드가 확인 대기 목록을 그리는 데 필요하다."""
    return list(request.app.state.store.alerts.values())


@router.get("/emergency")
async def list_emergencies(request: Request, _role: str = Depends(require_roles("observer", "commander", "tester", "maintainer"))):
    return list(request.app.state.store.emergencies.values())


class AckIn(BaseModel):
    reason: str = ""


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(
    alert_id: str,
    body: AckIn,
    request: Request,
    role: str = Depends(require_roles("commander")),
    actor_id: str = Depends(get_actor_id),
):
    store = request.app.state.store
    try:
        alert = store.ack_alert(alert_id, actor_id)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert not found")

    store.db.insert_user_action(
        {
            "role": role,
            "actor_id": actor_id,
            "action": "ack",
            "target_id": alert_id,
            "reason": body.reason,
            "gateway_utc": now_utc(),
        }
    )
    await store.add_event(
        device_id=alert["device_id"],
        monotonic_ms=0,
        event_type="ALERT_ACK",
        reason=body.reason,
        payload={"alert_id": alert_id, "actor_id": actor_id},
    )
    return alert


class EmergencyCloseIn(BaseModel):
    reason: str
    site_confirmer_id: str


@router.post("/emergency/{emergency_id}/close")
async def close_emergency(
    emergency_id: str,
    body: EmergencyCloseIn,
    request: Request,
    role: str = Depends(require_roles("commander")),
    actor_id: str = Depends(get_actor_id),
):
    store = request.app.state.store
    if not body.reason.strip() or not body.site_confirmer_id.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "emergency close requires site_confirmer_id and reason (PDD #16)",
        )
    try:
        emergency = store.close_emergency(emergency_id, body.site_confirmer_id, body.reason)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "emergency not found")
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    store.db.insert_user_action(
        {
            "role": role,
            "actor_id": actor_id,
            "action": "emergency_close",
            "target_id": emergency_id,
            "reason": body.reason,
            "gateway_utc": now_utc(),
        }
    )
    await store.add_event(
        device_id=emergency["device_id"],
        monotonic_ms=0,
        event_type="EMERGENCY_ACK_CLOSED",
        reason=body.reason,
        payload={
            "emergency_id": emergency_id,
            "site_confirmer_id": body.site_confirmer_id,
            "note": "관제 확인 기록일 뿐 장치 EMERGENCY 래치는 현장 물리 버튼으로만 해제된다",
        },
    )
    return emergency


class ExportIn(BaseModel):
    format: str = "json"  # "csv" | "json"
    device_id: str | None = None


@router.post("/export")
async def export_data(
    body: ExportIn,
    request: Request,
    role: str = Depends(require_roles("tester")),
    actor_id: str = Depends(get_actor_id),
):
    store = request.app.state.store
    events = store.list_events(device_id=body.device_id)

    store.db.insert_user_action(
        {
            "role": role,
            "actor_id": actor_id,
            "action": "export",
            "target_id": body.device_id or "*",
            "reason": f"format={body.format}",
            "gateway_utc": now_utc(),
        }
    )

    if body.format == "csv":
        buf = io.StringIO()
        fieldnames = ["seq", "gateway_utc", "monotonic_ms", "device_id", "event_type", "reason", "event_hash", "previous_hash"]
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for e in events:
            writer.writerow(e)
        return Response(content=buf.getvalue(), media_type="text/csv")

    return Response(content=json.dumps(events, ensure_ascii=False, indent=2), media_type="application/json")


@router.put("/config")
async def update_config(
    request: Request,
    x_hs_signature: str | None = None,
    role: str = Depends(require_roles("maintainer")),
):
    raw_body = await request.body()
    expected_sig = request.headers.get("x-hs-signature")
    computed_sig = hmac.new(CONFIG_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    if not expected_sig or not hmac.compare_digest(expected_sig, computed_sig):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing X-HS-Signature")

    payload = json.loads(raw_body or b"{}")
    request.app.state.pending_config = payload
    return {"status": "accepted", "risk_config_version": payload.get("risk_config_version")}
