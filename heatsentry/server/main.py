"""HeatSentry 게이트웨이 (SU-G).

HS-SIID-002 기준선의 로컬 API v2 + WebSocket을 구현한다. 실행:

    uvicorn heatsentry.server.main:app --reload --port 8000

heatsentry/simulator가 /ingest/*로 텔레메트리를 보내면 이 서버가 저장·해시체인·역할기반
확인 절차를 거쳐 /api/v2/*와 /ws/live로 대시보드에 내보낸다.

구 버전(GPS 분대 관제, soldier_id/readiness_score 기반 /api/sensor)은
HS-SIID-002/HS-PDD-002 v2.0으로 기준선이 바뀌면서 이 파일에서 완전히
교체됐다. 이전 구현은 git 이력에서 확인할 수 있다.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from heatsentry.server import routes_api_v2, routes_ingest
from heatsentry.server.db import GatewayDB
from heatsentry.server.state import GatewayStore
from heatsentry.server.ws import ConnectionManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = GatewayDB()
    store = GatewayStore(db)
    manager = ConnectionManager()
    store.set_broadcaster(manager.broadcast)

    app.state.db = db
    app.state.store = store
    app.state.ws_manager = manager
    app.state.pending_config = None

    yield

    db.close()


app = FastAPI(title="HeatSentry Gateway", version="2.0", lifespan=lifespan)

# A browser dashboard is local by default.  Deployments must list their exact
# console origins instead of exposing credentialed API calls to every origin.
allowed_origins = [
    origin.strip()
    for origin in os.environ.get(
        "HEATSENTRY_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_ingest.router)
app.include_router(routes_api_v2.router)


@app.get("/")
def root():
    return {
        "message": "HeatSentry gateway (schema_version 2.0) is running",
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    """IF-05 게이트웨이->UI WebSocket. observer 권한 수준의 실시간 스트림."""
    manager: ConnectionManager = websocket.app.state.ws_manager
    await manager.connect(websocket)
    try:
        store = websocket.app.state.store
        await websocket.send_json(
            {
                "type": "snapshot",
                "data": {
                    "devices": [t.model_dump() for t in store.devices.values()],
                    "events": store.list_events()[-50:],
                },
            }
        )
        while True:
            # 클라이언트는 보통 아무것도 안 보내지만, 연결 유지를 위해 수신 루프를 둔다.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)
