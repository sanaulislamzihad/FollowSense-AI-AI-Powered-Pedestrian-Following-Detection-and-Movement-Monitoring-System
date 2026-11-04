"""FollowSense AI - FastAPI application entry point."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import events, jobs, system, videos
from .config import app_config
from .database import init_db
from .services.jobs import manager
from .services.realtime import hub

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    hub.bind_loop(asyncio.get_running_loop())
    manager.recover()
    yield
    manager.shutdown()


app = FastAPI(title="FollowSense AI", version="1.0.0", lifespan=lifespan,
              description="Pedestrian following detection, group movement and crowd monitoring API")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in app_config.cors_origins.split(",")],
                   allow_methods=["*"], allow_headers=["*"])
for r in (system.router, videos.router, jobs.router, events.router):
    app.include_router(r)


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keep-alive pings from the client
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(ws)


# Serve the built React dashboard (frontend/dist) when present, e.g. in Docker.
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if not DIST.exists():
    DIST = Path(__file__).resolve().parents[1] / "static"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = DIST / path
        if path and target.is_file() and DIST in target.resolve().parents:
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
