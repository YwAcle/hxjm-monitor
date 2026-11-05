import asyncio
import json
import logging
import math
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect

from .analyzer import Analyzer
from .config import WS_SEND_TIMEOUT_SECONDS
from .config import CAMERAS, ALGORITHM_SPEC
from .persistence_config import PersistenceConfig
from .result_publisher import ResultPublisher


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    if not math.isfinite(WS_SEND_TIMEOUT_SECONDS) or WS_SEND_TIMEOUT_SECONDS <= 0:
        raise ValueError("VIDEO_ANALYSIS_WS_SEND_TIMEOUT_SECONDS must be finite and positive")
    persistence = PersistenceConfig(cameras=CAMERAS)
    if persistence.enabled and not ALGORITHM_SPEC.tracking and ALGORITHM_SPEC.result_type != 'garbage.detection':
        raise ValueError('Reliable tracking persistence requires a tracking adapter')
    publisher = ResultPublisher(persistence) if persistence.enabled else None
    analyzer = Analyzer(result_publisher=publisher)
    app.state.analyzer = analyzer
    try:
        if publisher:
            await publisher.start()
        await analyzer.start()
        yield
    finally:
        try:
            await analyzer.stop()
        finally:
            if publisher:
                await publisher.stop()


app = FastAPI(title="Video analysis", lifespan=lifespan)


@app.get("/v1/algorithms")
async def algorithms(request: Request):
    analyzer = request.app.state.analyzer
    health = analyzer.health()
    return {"items": [analyzer.algorithm_spec.describe(analyzer.algorithm)],
            "runtime": {"state": "ready" if health["status"] == "ok" else "degraded", "details": health}}


@app.get("/health")
async def health(request: Request):
    return request.app.state.analyzer.health()


async def _send_messages(websocket, subscription, send_lock):
    while True:
        message = await subscription.next_message()
        outgoing = {**message, "sent_at_ms": time.time_ns() // 1_000_000}
        if not subscription.include_frames:
            outgoing.pop('frame', None)
        if message["type"] == "detections":
            outgoing["valid_for_ms"] = message["valid_until_ms"] - outgoing["sent_at_ms"]
            if outgoing["valid_for_ms"] <= 0:
                continue
        async with send_lock:
            await asyncio.wait_for(websocket.send_json(outgoing), timeout=WS_SEND_TIMEOUT_SECONDS)


async def _wait_for_disconnect(websocket, send_lock):
    last_clock_reply = -math.inf
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        if message.get('text') and len(message['text']) <= 4096:
            try:
                ping = json.loads(message['text'])
                now = asyncio.get_running_loop().time()
                if (ping.get('type') == 'clock_ping' and isinstance(ping.get('client_ms'), (float, int))
                        and math.isfinite(ping['client_ms']) and now - last_clock_reply >= 0.5):
                    last_clock_reply = now
                    async with send_lock:
                        await asyncio.wait_for(websocket.send_json({
                            'type': 'clock_pong', 'client_ms': ping['client_ms'],
                            'server_ms': time.time_ns() // 1_000_000,
                        }), timeout=WS_SEND_TIMEOUT_SECONDS)
            except (ValueError, AttributeError):
                pass


@app.websocket("/ws/detections")
async def detections(websocket: WebSocket):
    await websocket.accept()
    analyzer = websocket.app.state.analyzer
    try:
        subscription = analyzer.subscribe(include_frames=websocket.query_params.get('frames') == '1')
    except OverflowError:
        await websocket.close(code=1013)
        return
    send_lock = asyncio.Lock()
    sender = asyncio.create_task(_send_messages(websocket, subscription, send_lock))
    receiver = asyncio.create_task(_wait_for_disconnect(websocket, send_lock))
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
