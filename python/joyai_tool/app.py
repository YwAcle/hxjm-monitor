"""Authenticated monitoring controls and a public readiness/status view."""
import asyncio
from contextlib import asynccontextmanager
import secrets
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from uuid import UUID
from .config import load
from .contracts import tool_description
from .monitor import Monitor


@asynccontextmanager
async def lifespan(app):
    config = load()
    app.state.config = config
    app.state.monitor = Monitor(config)
    # The launcher starts observation explicitly; Qwen loads only for queued clips.
    yield
    await asyncio.to_thread(app.state.monitor.stop)


app = FastAPI(title='JoyAI anomaly tool', lifespan=lifespan)


class StartRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    camera_ids: list[str] | None = None


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    report_id: UUID


def authorize(token):
    if not token or not secrets.compare_digest(token, app.state.config['token']):
        raise HTTPException(401, 'JoyAI 工具写操作需要有效的服务令牌')


@app.get('/health')
@app.get('/status')
def status():
    return app.state.monitor.status()


@app.get('/tools')
def tools():
    return {'items': [tool_description()]}


@app.post('/monitoring/start')
async def start(body: StartRequest, x_joyai_token: str | None = Header(default=None)):
    authorize(x_joyai_token)
    try:
        return await asyncio.to_thread(app.state.monitor.start, body.camera_ids)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@app.post('/monitoring/stop')
async def stop(x_joyai_token: str | None = Header(default=None)):
    authorize(x_joyai_token)
    return await asyncio.to_thread(app.state.monitor.stop)


@app.post('/reviews/restart')
async def restart_review(body: ReviewRequest, x_joyai_token: str | None = Header(default=None)):
    authorize(x_joyai_token)
    try:
        return await asyncio.to_thread(app.state.monitor.restart_review, str(body.report_id))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
