"""
FastAPI microservice: the "Telemetry Broker & Live Dashboard" deliverable.

Endpoints:
  GET  /                 -> serves the dashboard (single HTML file)
  GET  /health           -> basic liveness check
  GET  /api/metrics      -> current aggregate counts / congestion / FPS
  GET  /api/violations   -> recent violation events
  GET  /video_feed       -> MJPEG stream of the annotated frame (for the dashboard's live view)
  WS   /ws/live          -> push metrics+violations to connected clients every ~1s

Runs the CV pipeline in a background thread on startup so a single process
serves both the vision workload and the web layer -- start it with:

    uvicorn app.api.main:app --host 0.0.0.0 --port 8000

or simply: python -m scripts.run_pipeline --serve
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from ..pipeline import TrafficPipeline
from ..shared_state import shared_state

app = FastAPI(title="Edge-AI Traffic Analytics Engine")

_pipeline: TrafficPipeline | None = None
_dashboard_path = Path(__file__).resolve().parent.parent / "dashboard" / "index.html"


@app.on_event("startup")
async def _startup():
    global _pipeline
    config_path = os.environ.get("TRAFFIC_CONFIG")
    _pipeline = TrafficPipeline(config_path=config_path)
    _pipeline.run_in_thread()


@app.on_event("shutdown")
async def _shutdown():
    if _pipeline:
        _pipeline.stop()


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(_dashboard_path.read_text(encoding="utf-8"))


@app.get("/health")
async def health():
    return {"status": "ok", "uptime_seconds": round(shared_state.uptime_seconds(), 1)}


@app.get("/api/metrics")
async def metrics():
    return JSONResponse(shared_state.get_metrics())


@app.get("/api/violations")
async def violations():
    return JSONResponse(shared_state.get_violations())


def _mjpeg_generator():
    boundary = b"--frame"
    while True:
        frame = shared_state.get_frame()
        if frame is not None:
            yield boundary + b"\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        import time
        time.sleep(0.05)


@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(_mjpeg_generator(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            payload = {
                "metrics": shared_state.get_metrics(),
                "violations": shared_state.get_violations()[-5:],
                "fps": shared_state.get_fps(),
            }
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
