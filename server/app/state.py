"""게이트웨이 상태 저장소.

SU-G(게이트웨이) 책임: "BLE 집계·저장·WebSocket·선택 LoRa". 하지 않는 일:
"센서 원시판정 대체" — 즉 이 파일은 RiskIndex/FSM을 다시 계산하지 않고,
node_sim(손목/허리 노드)이 이미 판정해 보낸 telemetry/event를 그대로 집계·저장·
전파하기만 한다.

alerts/emergencies는 게이트웨이 자체의 "확인 여부" 장부다. HMI-001("지휘관
확인은 수신 확인이며 응급 해제와 분리")과 SIID p7 금지 사항("대시보드가
Emergency를 자동 해제하거나 ACK 버튼 하나로 경보와 팬·구조 절차를 동시에
종료해서는 안 된다")을 지키기 위해, emergency close는 오직 감사 기록만 남기고
장치의 실제 EMERGENCY 래치는 건드리지 않는다 — 그 래치는 현장 물리 버튼(허리
노드) 쪽에서만 풀 수 있다.
"""

from __future__ import annotations

import itertools
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from common.hash_chain import GENESIS_HASH, append_event
from common.schema import TelemetryV2
from server.app.db import GatewayDB

BroadcastFn = Callable[[dict], Awaitable[None]]


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


class GatewayStore:
    def __init__(self, db: GatewayDB) -> None:
        self.db = db
        self.devices: dict[str, TelemetryV2] = {}
        self._prev_state: dict[str, str] = {}
        self._event_seq = itertools.count(1)
        self._last_event_hash = GENESIS_HASH
        self.alerts: dict[str, dict[str, Any]] = {a["id"]: a for a in db.load_alerts()}
        self.emergencies: dict[str, dict[str, Any]] = {e["id"]: e for e in db.load_emergencies()}
        self._broadcast: BroadcastFn | None = None

        # 재시작 시 마지막 해시를 이어받아 체인이 끊기지 않게 한다.
        existing = self.db.all_events()
        if existing:
            self._last_event_hash = existing[-1]["event_hash"]
            self._event_seq = itertools.count(existing[-1]["seq"] + 1)
        for status in db.load_device_statuses():
            self.devices[status["device_id"]] = TelemetryV2.model_validate(status["telemetry"])
            self._prev_state[status["device_id"]] = self.devices[status["device_id"]].state

    def set_broadcaster(self, fn: BroadcastFn) -> None:
        self._broadcast = fn

    async def _publish(self, message: dict) -> None:
        if self._broadcast is not None:
            await self._broadcast(message)

    # ------------------------------------------------------------------
    # Telemetry (IF-04의 소프트웨어 등가물: node_sim -> POST /ingest/telemetry)
    # ------------------------------------------------------------------

    async def ingest_telemetry(self, telemetry: TelemetryV2) -> bool:
        device_id = telemetry.device_id
        last_sequence = self.db.last_sequence(device_id)
        # IF-04 is at-least-once delivery.  A repeated or out-of-order packet must
        # never overwrite the newest state or create a second state transition.
        if last_sequence is not None and telemetry.sequence <= last_sequence:
            return False
        prev_state = self._prev_state.get(device_id)
        self.devices[device_id] = telemetry
        self.db.insert_telemetry(
            device_id, telemetry.gateway_utc, telemetry.sequence, telemetry.model_dump()
        )
        self.db.save_device_status(
            device_id, telemetry.sequence, telemetry.monotonic_ms, now_utc(), telemetry.model_dump()
        )
        await self._publish({"type": "telemetry", "data": telemetry.model_dump()})

        if prev_state != telemetry.state:
            await self.add_event(
                device_id=device_id,
                monotonic_ms=telemetry.monotonic_ms,
                event_type="STATE_CHANGE",
                reason=f"{prev_state or 'UNKNOWN'}->{telemetry.state}",
                payload={"from": prev_state, "to": telemetry.state, "risk_index": telemetry.risk_index},
            )
            self._prev_state[device_id] = telemetry.state

            if telemetry.state in ("WARNING", "COOLING") and self._open_alert_for(device_id) is None:
                self._open_alert(device_id, telemetry.state)
            if telemetry.state == "EMERGENCY" and self._open_emergency_for(device_id) is None:
                self._open_emergency(device_id)
        return True

    # ------------------------------------------------------------------
    # Events (해시체인)
    # ------------------------------------------------------------------

    async def add_event(
        self, device_id: str, monotonic_ms: int, event_type: str, reason: str = "", payload: dict | None = None
    ) -> dict:
        seq = next(self._event_seq)
        raw = {
            "seq": seq,
            "gateway_utc": now_utc(),
            "monotonic_ms": monotonic_ms,
            "device_id": device_id,
            "event_type": event_type,
            "reason": reason,
            "payload": payload or {},
        }
        event = append_event(self._last_event_hash, raw)
        self._last_event_hash = event["event_hash"]
        self.db.insert_event(event)
        await self._publish({"type": "event", "data": event})
        return event

    def list_events(
        self, device_id: str | None = None, event_type: str | None = None, since_seq: int = 0
    ) -> list[dict]:
        events = self.db.all_events()
        if device_id:
            events = [e for e in events if e["device_id"] == device_id]
        if event_type:
            events = [e for e in events if e["event_type"] == event_type]
        if since_seq:
            events = [e for e in events if e["seq"] > since_seq]
        return events

    # ------------------------------------------------------------------
    # Command/ACK (node_sim -> POST /ingest/command_ack)
    # ------------------------------------------------------------------

    async def record_command_ack(self, record: dict) -> None:
        record = {**record, "gateway_utc": now_utc()}
        self.db.insert_command_ack(record)
        await self._publish({"type": "command_ack", "data": record})

    # ------------------------------------------------------------------
    # Alerts (표10 HMI: "확인 전까지 유지", 확인은 해제가 아님)
    # ------------------------------------------------------------------

    def _open_alert_for(self, device_id: str) -> dict | None:
        for alert in self.alerts.values():
            if alert["device_id"] == device_id and not alert["acknowledged"]:
                return alert
        return None

    def _open_alert(self, device_id: str, state: str) -> dict:
        alert_id = str(uuid.uuid4())
        alert = {
            "id": alert_id,
            "device_id": device_id,
            "state": state,
            "opened_at": now_utc(),
            "acknowledged": False,
            "acknowledged_by": None,
            "acknowledged_at": None,
        }
        self.alerts[alert_id] = alert
        self.db.save_alert(alert)
        return alert

    def ack_alert(self, alert_id: str, actor_id: str) -> dict:
        alert = self.alerts.get(alert_id)
        if alert is None:
            raise KeyError(alert_id)
        alert["acknowledged"] = True
        alert["acknowledged_by"] = actor_id
        alert["acknowledged_at"] = now_utc()
        self.db.save_alert(alert)
        return alert

    # ------------------------------------------------------------------
    # Emergencies (해제는 현장 확인 후 -> 여기서는 "관제가 인지했다"는 감사기록만 남긴다)
    # ------------------------------------------------------------------

    def _open_emergency_for(self, device_id: str) -> dict | None:
        for em in self.emergencies.values():
            if em["device_id"] == device_id and em["open"]:
                return em
        return None

    def _open_emergency(self, device_id: str) -> dict:
        emergency_id = str(uuid.uuid4())
        emergency = {
            "id": emergency_id,
            "device_id": device_id,
            "opened_at": now_utc(),
            "open": True,
            "closed_by": None,
            "closed_at": None,
            "close_reason": None,
        }
        self.emergencies[emergency_id] = emergency
        self.db.save_emergency(emergency)
        return emergency

    def close_emergency(self, emergency_id: str, actor_id: str, reason: str) -> dict:
        emergency = self.emergencies.get(emergency_id)
        if emergency is None:
            raise KeyError(emergency_id)
        if not reason.strip():
            raise ValueError("emergency close requires a non-empty reason")
        emergency["open"] = False
        emergency["closed_by"] = actor_id
        emergency["closed_at"] = now_utc()
        emergency["close_reason"] = reason
        self.db.save_emergency(emergency)
        return emergency
