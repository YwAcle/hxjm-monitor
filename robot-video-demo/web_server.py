from pathlib import Path
import asyncio
from contextlib import asynccontextmanager, suppress
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from settings import Settings
from telemetry import DEVICES, TelemetryStore, simulate, simulate_step

ROOT = Path(__file__).resolve().parent


class StateReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    state: str = Field(min_length=1, max_length=40)


async def telemetry_events(request, store):
    # Snapshots coalesce updates and keep memory bounded for slow clients.
    while not await request.is_disconnected():
        payload = json.dumps(store.snapshot(), ensure_ascii=False)
        yield f"event: telemetry\ndata: {payload}\n\n"
        await asyncio.sleep(1)


def create_app(settings: Settings, process_status=None, telemetry_store=None, source_status=None):
    store = telemetry_store if telemetry_store is not None else TelemetryStore(settings.mode)

    @asynccontextmanager
    async def lifespan(app):
        task = None
        if settings.mode == "simulated":
            simulate_step(store, 0)
            task = asyncio.create_task(simulate(store))
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="机器狗视频与状态监控 Demo", docs_url=None, redoc_url=None,
                  lifespan=lifespan)

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(ROOT / "web" / "index.html")

    @app.get("/api/config")
    async def config():
        return {"mode": settings.mode, "cameras": settings.public_cameras(),
                "channel_count": len(settings.cameras)}

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "processes": process_status() if process_status else {},
                "sources": source_status() if source_status else []}

    @app.get("/api/telemetry")
    async def telemetry():
        return store.snapshot()

    @app.get("/api/telemetry/events")
    async def events(request: Request):
        return StreamingResponse(telemetry_events(request, store), media_type="text/event-stream",
                                 headers={"X-Accel-Buffering": "no"})

    @app.post("/api/devices/{device}/state")
    async def report(device: str, payload: StateReport):
        if device not in DEVICES:
            raise HTTPException(404, "设备须为 dog 或 arm")
        if settings.mode != "hardware":
            raise HTTPException(409, "模拟模式不接受实物状态；请使用 --mode hardware 启动")
        try:
            store.update(device, payload.state)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return store.snapshot()

    @app.middleware("http")
    async def headers(request, call_next):
        r = await call_next(request)
        r.headers["X-Content-Type-Options"] = "nosniff"
        r.headers["Referrer-Policy"] = "same-origin"
        r.headers["Cache-Control"] = "no-store"
        r.headers["Content-Security-Policy"] = f"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' http://{settings.public_host}:{settings.whep_port}; media-src 'self' blob:; img-src 'self' data:; frame-ancestors 'none'"
        return r

    app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")
    return app
