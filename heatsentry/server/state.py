"""Gateway state store.

The Gateway aggregates, persists and broadcasts telemetry.
It does not replace the Belt's DeviceState/RiskIndex.

Unified DeviceState:
    BOOT / BASELINE / NORMAL / CAUTION /
    COOLING / EMERGENCY / SENSOR_CHECK
"""

from __future__ import annotations

import itertools
import uuid

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from heatsentry.common.hash_chain import (
    GENESIS_HASH,
    append_event,
)
from heatsentry.common.schema import (
    TelemetryV2,
)
from heatsentry.server.db import GatewayDB


BroadcastFn = Callable[
    [dict],
    Awaitable[None],
]


def now_utc() -> str:
    now = datetime.now(
        timezone.utc
    )

    return (
        now.strftime(
            "%Y-%m-%dT%H:%M:%S."
        )
        + f"{now.microsecond // 1000:03d}Z"
    )


class GatewayStore:
    def __init__(
        self,
        db: GatewayDB,
    ) -> None:

        self.db = db

        self.devices: dict[
            str,
            TelemetryV2,
        ] = {}

        self._prev_state: dict[
            str,
            str,
        ] = {}

        self._event_seq = itertools.count(1)
        self._last_event_hash = GENESIS_HASH

        self.alerts: dict[
            str,
            dict[str, Any],
        ] = {
            alert["id"]: alert
            for alert in db.load_alerts()
        }

        self.emergencies: dict[
            str,
            dict[str, Any],
        ] = {
            emergency["id"]: emergency
            for emergency in db.load_emergencies()
        }

        self._broadcast: BroadcastFn | None = None

        existing = self.db.all_events()

        if existing:
            self._last_event_hash = (
                existing[-1]["event_hash"]
            )

            self._event_seq = itertools.count(
                existing[-1]["seq"] + 1
            )

        for status in (
            db.load_device_statuses()
        ):
            telemetry = (
                TelemetryV2.model_validate(
                    status["telemetry"]
                )
            )

            self.devices[
                status["device_id"]
            ] = telemetry

            self._prev_state[
                status["device_id"]
            ] = telemetry.state

    def set_broadcaster(
        self,
        fn: BroadcastFn,
    ) -> None:
        self._broadcast = fn

    async def _publish(
        self,
        message: dict,
    ) -> None:

        if self._broadcast is not None:
            await self._broadcast(
                message
            )

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------
    async def ingest_telemetry(
        self,
        telemetry: TelemetryV2,
    ) -> bool:

        device_id = telemetry.device_id

        last_sequence = (
            self.db.last_sequence(
                device_id
            )
        )

        # At-least-once duplicate protection.
        # NOTE: if MCU sequence resets after reboot, current DB policy still
        # requires a sequence-epoch/reset policy or DB reset.
        if (
            last_sequence is not None
            and telemetry.sequence
            <= last_sequence
        ):
            return False

        prev_state = self._prev_state.get(
            device_id
        )

        self.devices[
            device_id
        ] = telemetry

        self.db.insert_telemetry(
            device_id,
            telemetry.gateway_utc,
            telemetry.sequence,
            telemetry.model_dump(),
        )

        self.db.save_device_status(
            device_id,
            telemetry.sequence,
            telemetry.monotonic_ms,
            now_utc(),
            telemetry.model_dump(),
        )

        await self._publish(
            {
                "type": "telemetry",
                "data":
                    telemetry.model_dump(),
            }
        )

        if prev_state != telemetry.state:
            await self.add_event(
                device_id=device_id,
                monotonic_ms=
                    telemetry.monotonic_ms,
                event_type="STATE_CHANGE",
                reason=(
                    f"{prev_state or 'UNKNOWN'}"
                    f"->{telemetry.state}"
                ),
                payload={
                    "from": prev_state,
                    "to": telemetry.state,
                    "risk_index":
                        telemetry.risk_index,
                    "cooling_stage":
                        telemetry.cooling.requested,
                },
            )

            self._prev_state[
                device_id
            ] = telemetry.state

            if (
                telemetry.state
                in ("CAUTION", "COOLING")
                and self._open_alert_for(
                    device_id
                ) is None
            ):
                self._open_alert(
                    device_id,
                    telemetry.state,
                )

            if (
                telemetry.state
                == "EMERGENCY"
                and self._open_emergency_for(
                    device_id
                ) is None
            ):
                self._open_emergency(
                    device_id
                )

        return True

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    async def add_event(
        self,
        device_id: str,
        monotonic_ms: int,
        event_type: str,
        reason: str = "",
        payload: dict | None = None,
    ) -> dict:

        seq = next(
            self._event_seq
        )

        raw = {
            "seq": seq,
            "gateway_utc": now_utc(),
            "monotonic_ms": monotonic_ms,
            "device_id": device_id,
            "event_type": event_type,
            "reason": reason,
            "payload": payload or {},
        }

        event = append_event(
            self._last_event_hash,
            raw,
        )

        self._last_event_hash = (
            event["event_hash"]
        )

        self.db.insert_event(
            event
        )

        await self._publish(
            {
                "type": "event",
                "data": event,
            }
        )

        return event

    def list_events(
        self,
        device_id: str | None = None,
        event_type: str | None = None,
        since_seq: int = 0,
    ) -> list[dict]:

        events = self.db.all_events()

        if device_id:
            events = [
                event
                for event in events
                if event["device_id"]
                == device_id
            ]

        if event_type:
            events = [
                event
                for event in events
                if event["event_type"]
                == event_type
            ]

        if since_seq:
            events = [
                event
                for event in events
                if event["seq"]
                > since_seq
            ]

        return events

    # ------------------------------------------------------------------
    # Command ACK
    # ------------------------------------------------------------------
    async def record_command_ack(
        self,
        record: dict,
    ) -> None:

        record = {
            **record,
            "gateway_utc":
                now_utc(),
        }

        self.db.insert_command_ack(
            record
        )

        await self._publish(
            {
                "type": "command_ack",
                "data": record,
            }
        )

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------
    def _open_alert_for(
        self,
        device_id: str,
    ) -> dict | None:

        for alert in self.alerts.values():
            if (
                alert["device_id"]
                == device_id
                and not alert["acknowledged"]
            ):
                return alert

        return None

    def _open_alert(
        self,
        device_id: str,
        state: str,
    ) -> dict:

        alert_id = str(
            uuid.uuid4()
        )

        alert = {
            "id": alert_id,
            "device_id": device_id,
            "state": state,
            "opened_at": now_utc(),
            "acknowledged": False,
            "acknowledged_by": None,
            "acknowledged_at": None,
        }

        self.alerts[
            alert_id
        ] = alert

        self.db.save_alert(
            alert
        )

        return alert

    def ack_alert(
        self,
        alert_id: str,
        actor_id: str,
    ) -> dict:

        alert = self.alerts.get(
            alert_id
        )

        if alert is None:
            raise KeyError(
                alert_id
            )

        alert["acknowledged"] = True
        alert["acknowledged_by"] = actor_id
        alert["acknowledged_at"] = now_utc()

        self.db.save_alert(
            alert
        )

        return alert

    # ------------------------------------------------------------------
    # Emergencies
    # ------------------------------------------------------------------
    def _open_emergency_for(
        self,
        device_id: str,
    ) -> dict | None:

        for emergency in (
            self.emergencies.values()
        ):
            if (
                emergency["device_id"]
                == device_id
                and emergency["open"]
            ):
                return emergency

        return None

    def _open_emergency(
        self,
        device_id: str,
    ) -> dict:

        emergency_id = str(
            uuid.uuid4()
        )

        emergency = {
            "id": emergency_id,
            "device_id": device_id,
            "opened_at": now_utc(),
            "open": True,
            "closed_by": None,
            "closed_at": None,
            "close_reason": None,
        }

        self.emergencies[
            emergency_id
        ] = emergency

        self.db.save_emergency(
            emergency
        )

        return emergency

    def close_emergency(
        self,
        emergency_id: str,
        actor_id: str,
        reason: str,
    ) -> dict:

        emergency = (
            self.emergencies.get(
                emergency_id
            )
        )

        if emergency is None:
            raise KeyError(
                emergency_id
            )

        if not reason.strip():
            raise ValueError(
                "emergency close requires "
                "a non-empty reason"
            )

        emergency["open"] = False
        emergency["closed_by"] = actor_id
        emergency["closed_at"] = now_utc()
        emergency["close_reason"] = reason

        self.db.save_emergency(
            emergency
        )

        return emergency
