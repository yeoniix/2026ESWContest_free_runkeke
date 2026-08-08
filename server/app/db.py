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
