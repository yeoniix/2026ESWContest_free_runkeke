"""게이트웨이 /ingest/* 로 보내는 얇은 HTTP 클라이언트.

실제로는 IF-04(BLE GATT)가 담당할 몫을 개발 단계에서는 HTTP POST로 대신한다
(server/app/routes_ingest.py 참고). 연결 실패는 예외를 그대로 올리지 않고
GatewayUnavailable로 감싸, run_demo가 사용자에게 친절한 안내를 줄 수 있게 한다.
"""

from __future__ import annotations

import requests


class GatewayUnavailable(RuntimeError):
    pass


class GatewayClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout_s: float = 3.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def _post(self, path: str, payload: dict) -> dict:
        try:
            resp = requests.post(f"{self.base_url}{path}", json=payload, timeout=self.timeout_s)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError as exc:
            raise GatewayUnavailable(
                f"게이트웨이({self.base_url})에 연결할 수 없습니다. "
                "uvicorn server.app.main:app 을 먼저 실행하세요."
            ) from exc

    def post_telemetry(self, telemetry: dict) -> dict:
        return self._post("/ingest/telemetry", telemetry)

    def post_event(self, event: dict) -> dict:
        return self._post("/ingest/event", event)

    def post_command_ack(self, record: dict) -> dict:
        return self._post("/ingest/command_ack", record)
