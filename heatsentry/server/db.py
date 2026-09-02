"""게이트웨이 로컬 저장소 (SQLite).

출처: HS-SIID-002 p9 표9 "데이터 보존 정책". Telemetry/Event/Command·ACK/User
action 네 종류를 분리 저장한다. 대회용 MVP이므로 파일 하나(sqlite)로 충분하며,
Event 테이블만 해시체인이 걸린다(무결성 검사 대상, DAT-001/T10).
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "heatsentry_gateway.db"


def resolve_db_path() -> Path:
    """HEATSENTRY_DB_PATH가 있으면 그걸 쓴다(테스트에서 tmp 경로로 격리하기 위함)."""
    override = os.environ.get("HEATSENTRY_DB_PATH")
    return Path(override) if override else DEFAULT_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    gateway_utc TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_telemetry_device ON telemetry(device_id, id);

CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY,
    device_id TEXT NOT NULL,
    gateway_utc TEXT NOT NULL,
    monotonic_ms INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS command_acks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cmd_id INTEGER NOT NULL,
    device_id TEXT NOT NULL,
    requested_level INTEGER NOT NULL,
    requested_reason TEXT NOT NULL,
    actual_pwm INTEGER NOT NULL,
    current_ma INTEGER NOT NULL,
    result TEXT NOT NULL,
    retries INTEGER NOT NULL,
    gateway_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    gateway_utc TEXT NOT NULL
);

-- Runtime state is deliberately kept separate from the append-only audit event log.
-- It lets the gateway recover its current operational picture after a restart.
CREATE TABLE IF NOT EXISTS device_status (
    device_id TEXT PRIMARY KEY,
    last_sequence INTEGER NOT NULL,
    last_monotonic_ms INTEGER NOT NULL,
    last_seen_utc TEXT NOT NULL,
    telemetry_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    state TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    acknowledged_by TEXT,
    acknowledged_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_device ON alerts(device_id, acknowledged);

CREATE TABLE IF NOT EXISTS emergencies (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    open INTEGER NOT NULL DEFAULT 1,
    closed_by TEXT,
    closed_at TEXT,
    close_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_emergencies_device ON emergencies(device_id, open);
"""


class GatewayDB:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = str(path) if path is not None else str(resolve_db_path())
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def insert_telemetry(self, device_id: str, gateway_utc: str, sequence: int, payload: dict) -> None:
        self._conn.execute(
            "INSERT INTO telemetry(device_id, gateway_utc, sequence, payload_json) VALUES (?,?,?,?)",
            (device_id, gateway_utc, sequence, json.dumps(payload, ensure_ascii=False)),
        )
        self._conn.commit()

    def last_sequence(self, device_id: str) -> int | None:
        row = self._conn.execute(
            "SELECT last_sequence FROM device_status WHERE device_id = ?", (device_id,)
        ).fetchone()
        return int(row[0]) if row else None

    def save_device_status(self, device_id: str, sequence: int, monotonic_ms: int, seen_utc: str, payload: dict) -> None:
        self._conn.execute(
            """INSERT INTO device_status(device_id, last_sequence, last_monotonic_ms, last_seen_utc, telemetry_json)
               VALUES (?,?,?,?,?)
               ON CONFLICT(device_id) DO UPDATE SET
                 last_sequence=excluded.last_sequence,
                 last_monotonic_ms=excluded.last_monotonic_ms,
                 last_seen_utc=excluded.last_seen_utc,
                 telemetry_json=excluded.telemetry_json""",
            (device_id, sequence, monotonic_ms, seen_utc, json.dumps(payload, ensure_ascii=False)),
        )
        self._conn.commit()

    def load_device_statuses(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT device_id, last_sequence, last_monotonic_ms, last_seen_utc, telemetry_json FROM device_status"
        ).fetchall()
        return [
            {
                "device_id": row[0], "last_sequence": row[1], "last_monotonic_ms": row[2],
                "last_seen_utc": row[3], "telemetry": json.loads(row[4]),
            }
            for row in rows
        ]

    def save_alert(self, alert: dict) -> None:
        self._conn.execute(
            """INSERT INTO alerts(id, device_id, state, opened_at, acknowledged, acknowledged_by, acknowledged_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET acknowledged=excluded.acknowledged,
                 acknowledged_by=excluded.acknowledged_by, acknowledged_at=excluded.acknowledged_at""",
            (alert["id"], alert["device_id"], alert["state"], alert["opened_at"], int(alert["acknowledged"]),
             alert["acknowledged_by"], alert["acknowledged_at"]),
        )
        self._conn.commit()

    def load_alerts(self) -> list[dict]:
        rows = self._conn.execute("SELECT id, device_id, state, opened_at, acknowledged, acknowledged_by, acknowledged_at FROM alerts").fetchall()
        return [dict(zip(("id", "device_id", "state", "opened_at", "acknowledged", "acknowledged_by", "acknowledged_at"), row), acknowledged=bool(row[4])) for row in rows]

    def save_emergency(self, emergency: dict) -> None:
        self._conn.execute(
            """INSERT INTO emergencies(id, device_id, opened_at, open, closed_by, closed_at, close_reason)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET open=excluded.open, closed_by=excluded.closed_by,
                 closed_at=excluded.closed_at, close_reason=excluded.close_reason""",
            (emergency["id"], emergency["device_id"], emergency["opened_at"], int(emergency["open"]),
             emergency["closed_by"], emergency["closed_at"], emergency["close_reason"]),
        )
        self._conn.commit()

    def load_emergencies(self) -> list[dict]:
        rows = self._conn.execute("SELECT id, device_id, opened_at, open, closed_by, closed_at, close_reason FROM emergencies").fetchall()
        return [dict(zip(("id", "device_id", "opened_at", "open", "closed_by", "closed_at", "close_reason"), row), open=bool(row[3])) for row in rows]

    def insert_event(self, event: dict) -> None:
        self._conn.execute(
            """INSERT INTO events(seq, device_id, gateway_utc, monotonic_ms, event_type,
               reason, payload_json, previous_hash, event_hash)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                event["seq"],
                event["device_id"],
                event["gateway_utc"],
                event["monotonic_ms"],
                event["event_type"],
                event.get("reason", ""),
                json.dumps(event.get("payload", {}), ensure_ascii=False),
                event["previous_hash"],
                event["event_hash"],
            ),
        )
        self._conn.commit()

    def all_events(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM events ORDER BY seq ASC").fetchall()
        cols = [d[0] for d in self._conn.execute("SELECT * FROM events LIMIT 0").description]
        events = []
        for row in rows:
            record = dict(zip(cols, row))
            record["payload"] = json.loads(record.pop("payload_json"))
            events.append(record)
        return events

    def insert_command_ack(self, record: dict) -> None:
        self._conn.execute(
            """INSERT INTO command_acks(cmd_id, device_id, requested_level, requested_reason,
               actual_pwm, current_ma, result, retries, gateway_utc) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                record["cmd_id"],
                record["device_id"],
                record["requested_level"],
                record["requested_reason"],
                record["actual_pwm"],
                record["current_ma"],
                record["result"],
                record.get("retries", 0),
                record["gateway_utc"],
            ),
        )
        self._conn.commit()

    def insert_user_action(self, record: dict) -> None:
        self._conn.execute(
            """INSERT INTO user_actions(role, actor_id, action, target_id, reason, gateway_utc)
               VALUES (?,?,?,?,?,?)""",
            (
                record["role"],
                record["actor_id"],
                record["action"],
                record["target_id"],
                record.get("reason", ""),
                record["gateway_utc"],
            ),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
