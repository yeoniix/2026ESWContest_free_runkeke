import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from server.app.main import app

TELEMETRY = {
    "schema_version": "2.0",
    "gateway_utc": "2026-08-08T12:00:00.250Z",
    "device_id": "HS-W-001",
    "monotonic_ms": 184225,
    "state": "COOLING",
    "risk_index": 88,
    "valid_weight": 1.0,
    "quality": {"ppg": 82, "skin": 96, "eda": 55, "imu": 100},
    "signals": {"hr_bpm": 148, "skin_c": 35.72, "activity": "RUN"},
    "cooling": {"requested": 1, "actual_pwm": 20, "current_ma": 284},
    "contributions": {},
    "active_errors": [],
    "config_version": "0.2.0",
    "sequence": 1,
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HEATSENTRY_DB_PATH", str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c


def test_ingest_then_list_devices(client):
    r = client.post("/ingest/telemetry", json=TELEMETRY)
    assert r.status_code == 200
    r = client.get("/api/v2/devices", headers={"X-HS-Role": "observer"})
    assert r.status_code == 200
    devices = r.json()
    assert devices[0]["device_id"] == "HS-W-001"


def test_state_change_creates_hash_chained_event(client):
    client.post("/ingest/telemetry", json=TELEMETRY)
    r = client.get("/api/v2/events", headers={"X-HS-Role": "observer"})
    events = r.json()
    assert len(events) == 1
    assert events[0]["event_type"] == "STATE_CHANGE"
    assert events[0]["previous_hash"] == "0" * 64


def test_ack_requires_commander_role(client):
    client.post("/ingest/telemetry", json=TELEMETRY)
    r = client.post("/api/v2/alerts/does-not-exist/ack", json={}, headers={"X-HS-Role": "observer"})
    assert r.status_code == 403


def test_ack_and_emergency_are_separate_actions(client):
    emergency_telemetry = {**TELEMETRY, "state": "EMERGENCY", "sequence": 2}
    client.post("/ingest/telemetry", json=emergency_telemetry)

    r = client.get("/api/v2/emergency", headers={"X-HS-Role": "observer"})
    emergency_id = r.json()[0]["id"]

    # HMI-001: 사유 없이는 응급 해제 불가
    r = client.post(
        f"/api/v2/emergency/{emergency_id}/close",
        json={"reason": "", "site_confirmer_id": "CDR1"},
        headers={"X-HS-Role": "commander", "X-HS-Actor": "cdr1"},
    )
    assert r.status_code == 400

    r = client.post(
        f"/api/v2/emergency/{emergency_id}/close",
        json={"reason": "현장 확인 완료", "site_confirmer_id": "CDR1"},
        headers={"X-HS-Role": "commander", "X-HS-Actor": "cdr1"},
    )
    assert r.status_code == 200
    assert r.json()["open"] is False


def test_export_requires_tester_role(client):
    client.post("/ingest/telemetry", json=TELEMETRY)
    r = client.post("/api/v2/export", json={"format": "json"}, headers={"X-HS-Role": "observer"})
    assert r.status_code == 403
    r = client.post("/api/v2/export", json={"format": "json"}, headers={"X-HS-Role": "tester"})
    assert r.status_code == 200


def test_config_update_requires_valid_signature(client):
    body = json.dumps({"risk_config_version": "0.2.1"}).encode()
    bad_sig = "0" * 64
    r = client.put(
        "/api/v2/config",
        content=body,
        headers={"X-HS-Role": "maintainer", "X-HS-Signature": bad_sig, "Content-Type": "application/json"},
    )
    assert r.status_code == 401

    good_sig = hmac.new(b"dev-only-insecure-secret", body, hashlib.sha256).hexdigest()
    r = client.put(
        "/api/v2/config",
        content=body,
        headers={"X-HS-Role": "maintainer", "X-HS-Signature": good_sig, "Content-Type": "application/json"},
    )
    assert r.status_code == 200


def test_tamper_detected_via_verify_chain(client):
    from common.hash_chain import verify_chain

    client.post("/ingest/telemetry", json=TELEMETRY)
    client.post("/ingest/telemetry", json={**TELEMETRY, "state": "WARNING", "sequence": 2})
    events = client.get("/api/v2/events", headers={"X-HS-Role": "observer"}).json()

    ok, _ = verify_chain(events)
    assert ok is True

    events[0]["reason"] = "TAMPERED"
    ok, bad_index = verify_chain(events)
    assert ok is False
    assert bad_index == 0
