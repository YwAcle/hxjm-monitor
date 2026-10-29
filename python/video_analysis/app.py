import asyncio
import json
import logging
import math
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect

from .analyzer import Analyzer
from .config import (
    CAMERAS,
    RECORDING_ENABLED,
    RECORDING_QUEUE_SIZE,
    RECORDING_RETENTION_SECONDS,
    RECORDING_ROOT,
    RECORDING_SEGMENT_SECONDS,
    SOURCE_IDS,
    WS_SEND_TIMEOUT_SECONDS,
    load_business_config,
)


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    if not math.isfinite(WS_SEND_TIMEOUT_SECONDS) or WS_SEND_TIMEOUT_SECONDS <= 0:
        raise ValueError("VIDEO_ANALYSIS_WS_SEND_TIMEOUT_SECONDS must be finite and positive")
    business = load_business_config()
    if RECORDING_ENABLED and not SOURCE_IDS:
        raise ValueError('Recording requires complete VIDEO_ANALYSIS_SOURCE_IDS')
    if RECORDING_ENABLED and business is not None and RECORDING_RETENTION_SECONDS != 604800:
        raise ValueError('Business recordings must expire seven days after their end')
    delivery = None
    if business is not None:
        from .business_runtime import create_delivery
        delivery = create_delivery(business)
    sample_pipeline = None
    if delivery is not None and business.get('sample_pipeline') is not None:
        from .sample_pipeline import LocalSamplePipeline
        sample_pipeline = LocalSamplePipeline(delivery.business_client,
            **business['sample_pipeline'], finish_tasks=True)
        delivery.on_confirmed = sample_pipeline.confirmed
    hub = None
    recorders = {}
    recording_delivery = None
    if RECORDING_ENABLED and delivery is not None:
        from .recording_delivery import RecordingDelivery
        recording_delivery = RecordingDelivery(
            delivery.business_client, delivery.business_runtime,
            storage_root=RECORDING_ROOT, source_ids=set(SOURCE_IDS.values()))
    if SOURCE_IDS:
        from frame_hub.hub import FrameHub
        recorder_factory = None
        if RECORDING_ENABLED:
            from frame_hub.recording import BackgroundRecorder

            def recorder_factory(source_id):
                recorder = BackgroundRecorder(
                    source_id,
                    storage_root=RECORDING_ROOT,
                    segment_seconds=RECORDING_SEGMENT_SECONDS,
                    queue_size=RECORDING_QUEUE_SIZE,
                    retention_seconds=RECORDING_RETENTION_SECONDS,
                    on_segment=recording_delivery,
                )
                recorders[source_id] = recorder
                return recorder

        sources = {SOURCE_IDS[camera_id]: url for camera_id, url in CAMERAS.items()}
        hub = FrameHub(sources, recorder_factory=recorder_factory) if recorder_factory else FrameHub(sources)
    options = {'frame_hub': hub, 'source_ids': SOURCE_IDS} if hub is not None else {}
    if delivery is not None:
        options['result_sink'] = delivery
    if sample_pipeline is not None:
        options['sample_pipeline'] = sample_pipeline
    analyzer = Analyzer(**options)
    app.state.analyzer = analyzer
    app.state.frame_hub = hub
    app.state.result_delivery = delivery
    app.state.recorders = recorders
    app.state.recording_delivery = recording_delivery
    app.state.sample_pipeline = sample_pipeline
    try:
        if sample_pipeline is not None:
            sample_pipeline.start()
        if delivery is not None:
            delivery.start()
        if recording_delivery is not None:
            recording_delivery.start()
        if hub is not None:
            hub.start()
        await analyzer.start()
        yield
    finally:
        try:
            await analyzer.stop()
        finally:
            try:
                if hub is not None:
                    await asyncio.to_thread(hub.stop)
            finally:
                try:
                    if recording_delivery is not None and not await asyncio.to_thread(recording_delivery.stop):
                        logger.error('Recording registration did not stop within its shutdown timeout')
                finally:
                    try:
                        if delivery is not None and not await asyncio.to_thread(delivery.stop):
                            logger.error('Result delivery did not stop within its shutdown timeout')
                    finally:
                        if sample_pipeline is not None and not await asyncio.to_thread(sample_pipeline.stop):
                            logger.error('Sample pipeline did not stop within its shutdown timeout')


app = FastAPI(title="Video analysis", lifespan=lifespan)


@app.get("/health")
async def health(request: Request):
    snapshot = request.app.state.analyzer.health()
    delivery = getattr(request.app.state, 'result_delivery', None)
    if delivery is not None:
        snapshot['result_delivery'] = delivery.status()
    recorders = getattr(request.app.state, 'recorders', {})
    if recorders:
        snapshot['recording'] = {
            source_id: recorder.status() for source_id, recorder in recorders.items()
        }
    recording_delivery = getattr(request.app.state, 'recording_delivery', None)
    if recording_delivery is not None:
        snapshot['recording_delivery'] = recording_delivery.status()
    sample_pipeline = getattr(request.app.state, 'sample_pipeline', None)
    if sample_pipeline is not None:
        snapshot['sample_pipeline'] = sample_pipeline.status()
    return snapshot


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
