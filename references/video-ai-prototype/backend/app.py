import asyncio
import logging
import math
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect

from .analyzer import Analyzer
from .config import WS_SEND_TIMEOUT_SECONDS


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    if not math.isfinite(WS_SEND_TIMEOUT_SECONDS) or WS_SEND_TIMEOUT_SECONDS <= 0:
        raise ValueError("DEMO_WS_SEND_TIMEOUT_SECONDS must be finite and positive")
    analyzer = Analyzer()
    app.state.analyzer = analyzer
    await analyzer.start()
    try:
        yield
    finally:
        await analyzer.stop()


app = FastAPI(title="Video AI decoupling demo", lifespan=lifespan)


@app.get("/health")
async def health(request: Request):
    return request.app.state.analyzer.health()


async def _send_messages(websocket, subscription):
    while True:
        message = await subscription.next_message()
        outgoing = {**message, "sent_at_ms": time.time_ns() // 1_000_000}
        await asyncio.wait_for(websocket.send_json(outgoing), timeout=WS_SEND_TIMEOUT_SECONDS)


async def _wait_for_disconnect(websocket):
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return


@app.websocket("/ws/detections")
async def detections(websocket: WebSocket):
    await websocket.accept()
    analyzer = websocket.app.state.analyzer
    subscription = analyzer.subscribe()
    sender = asyncio.create_task(_send_messages(websocket, subscription))
    receiver = asyncio.create_task(_wait_for_disconnect(websocket))
    close_code = 1000
    try:
        done, pending = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except asyncio.TimeoutError:
        close_code = 1013
        logger.info("Closing slow WebSocket client")
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        for task in (sender, receiver):
            task.cancel()
        await asyncio.gather(sender, receiver, return_exceptions=True)
        analyzer.unsubscribe(subscription)
        try:
            await asyncio.wait_for(websocket.close(code=close_code), timeout=WS_SEND_TIMEOUT_SECONDS)
        except (WebSocketDisconnect, RuntimeError, asyncio.TimeoutError):
            pass
