"""Service-owned round-robin scheduler; clients subscribe without creating work."""
import asyncio
import inspect
import logging
import math
import time
import uuid
from collections import OrderedDict, deque
from functools import partial

from .config import (
    CAMERAS, INFERENCE_INTERVAL_SECONDS, RESULT_TTL_MS, WORKER_COUNT,
    WORKER_RETRY_SECONDS, WORKER_RETRY_MAX_SECONDS, MAX_CLIENTS, WORKER_IDLE_SECONDS,
    FRAME_FRESH_MS, SYNC_FPS, ALGORITHM,
)
from .stream_grabber import LatestFrameGrabber
from .sync_frame import encode_frame
from .worker import ModelWorker
from .frame_result import FrameResultInput, frame_result

logger = logging.getLogger(__name__)
# Keep the public task key aligned with the configured detector.  The
# subscription key and result metadata must not advertise a different
# algorithm when the service is running in BoT-SORT mode.
TASK = ALGORITHM


class Subscription:
    """At most one status and one detection per configured camera/task, FIFO keys."""
    def __init__(self, keys, include_frames=False):
        self.include_frames = include_frames
        self.allowed = set(keys)
        self.pending = OrderedDict()
        self._ready = asyncio.Event()

    def put(self, message):
        key = (message['camera_id'], message['task'])
        if key not in self.allowed:
            return
        self.pending[(*key, message['type'])] = message
        self._ready.set()

    async def next_message(self):
        await self._ready.wait()
        _, message = self.pending.popitem(last=False)
        if not self.pending:
            self._ready.clear()
        return message


class CameraAnalysis:
    def __init__(self, camera_id, url, callback, grabber_factory):
        self.camera_id = camera_id
        self.grabber = grabber_factory(callback, rtsp_url=url)
        self.session_id = uuid.uuid4().hex
        self.session_generation = 0
        self.tracking_started_at_ms = None
        self.states = {'capture': {'state': 'idle', 'error': None},
                       'analyzer': {'state': 'waiting_source', 'error': None}}
        self.inflight = False
        self.next_at = 0
        self.last_attempt = 0
        self.last_result = None
        self.inferences = 0
        self.attempts = 0
        self.published = 0
        self.discarded = 0
        self.failures = 0
        self.recent = deque(maxlen=10)
        self.stream_epoch = None
        self.source_shape = None

    def invalidate(self):
        self.session_id = uuid.uuid4().hex
        self.session_generation += 1
        self.tracking_started_at_ms = None
        self.last_result = None

    @property
    def tracking_context_id(self):
        return str(uuid.UUID(self.session_id))

    def input_session_id(self, captured=None):
        if captured is not None:
            reference = getattr(captured, 'public_frame_ref', None)
            session = getattr(reference, 'stream_session_id', None) or getattr(captured, 'stream_session_id', None)
            if session:
                return session
        return self.grabber.snapshot().get('stream_session_id')


class Analyzer:
    def __init__(self, inference_interval=INFERENCE_INTERVAL_SECONDS, cameras=None,
                 worker_count=WORKER_COUNT, grabber_factory=LatestFrameGrabber,
                 worker_factory=ModelWorker, worker_retry=WORKER_RETRY_SECONDS,
                 worker_idle=WORKER_IDLE_SECONDS, algorithm=ALGORITHM,
                 worker_retry_max=WORKER_RETRY_MAX_SECONDS, result_sink=None,
                 frame_hub=None, source_ids=None, sample_pipeline=None):
        if not math.isfinite(inference_interval) or inference_interval <= 0:
            raise ValueError('Inference interval must be finite and positive')
        if not 1 <= worker_count <= 4:
            raise ValueError('Worker count must be 1 to 4')
        if not math.isfinite(worker_idle) or worker_idle <= 0:
            raise ValueError('Worker idle time must be finite and positive')
        if not math.isfinite(worker_retry) or worker_retry <= 0:
            raise ValueError('Worker retry time must be finite and positive')
        if not math.isfinite(worker_retry_max) or worker_retry_max < worker_retry:
            raise ValueError('Worker retry maximum must be finite and at least the retry time')
        self._inference_interval = inference_interval
        self.algorithm = algorithm
        self._worker_retry = worker_retry
        self._worker_retry_max = worker_retry_max
        self._loading_lock = asyncio.Lock()
        self._retry_delays = {}
        self._worker_idle = worker_idle
        self._stop_event = asyncio.Event()
        self._subscriptions = set()
        self._loop = None
        self._tasks = []
        self._heartbeat = None
        self._image_tasks = {}
        self._cursor = 0
        self._service_id = uuid.uuid4().hex
        if result_sink is not None and (not callable(result_sink)
                or inspect.iscoroutinefunction(result_sink)
                or inspect.iscoroutinefunction(getattr(result_sink, '__call__', None))):
            raise ValueError('result_sink must be a synchronous nonblocking callable')
        self._result_sink = result_sink
        self._sample_pipeline = sample_pipeline
        self._result_handoffs = 0
        self._result_failures = 0
        self._result_error = None
        camera_urls = CAMERAS if cameras is None else cameras
        if frame_hub is not None and (not isinstance(source_ids, dict)
                                       or set(source_ids) != set(camera_urls)):
            raise ValueError('Shared input requires a source ID for every configured camera')
        if frame_hub is None and source_ids is not None:
            raise ValueError('Source mappings require a shared frame input')
        self._workers = [worker_factory(i) for i in range(min(worker_count, len(camera_urls)))]
        self._cameras = {}
        for camera_id, url in camera_urls.items():
            def callback(state, error, epoch, camera_id=camera_id):
                if self._loop is not None and not self._loop.is_closed():
                    self._loop.call_soon_threadsafe(self._capture_status, camera_id, state, error, epoch)
            factory = grabber_factory
            if frame_hub is not None:
                source_id = source_ids[camera_id]
                factory = lambda callback, rtsp_url, sid=source_id: frame_hub.reader(sid, callback)
            self._cameras[camera_id] = CameraAnalysis(camera_id, url, callback, factory)
        if not self._cameras:
            raise ValueError('At least one camera is required')
        self._order = list(self._cameras.values())

    async def start(self):
        if self._tasks:
            raise RuntimeError('Analyzer already started')
        self._loop = asyncio.get_running_loop()
        for camera in self._order:
            camera.grabber.start()
        self._tasks = [asyncio.create_task(self._run_worker(worker), name=f'analysis-slot-{worker.slot}')
                       for worker in self._workers]
        self._heartbeat = asyncio.create_task(self._send_heartbeat())

    async def stop(self):
        self._stop_event.set()
        for camera in self._order:
            camera.grabber.request_stop()
        for task in [*self._tasks, self._heartbeat]:
            if task is not None:
                task.cancel()
        await asyncio.gather(*self._tasks, *([self._heartbeat] if self._heartbeat else []), return_exceptions=True)
        image_tasks = list(self._image_tasks.values())
        for task in image_tasks:
            task.cancel()
        await asyncio.gather(*image_tasks, return_exceptions=True)
        self._image_tasks.clear()
        await asyncio.gather(*(worker.stop() for worker in self._workers))
        await asyncio.gather(*(asyncio.to_thread(camera.grabber.stop) for camera in self._order))
        self._subscriptions.clear()

    def _camera_health(self, camera):
        capture = camera.grabber.snapshot()
        result = camera.last_result
        available = (capture['state'] == 'streaming' and capture['latest_frame_id'] is not None
                     and camera.states['analyzer']['state'] in {'ready', 'detecting'})
        fresh = (result is not None and result['stream_epoch'] == capture['stream_epoch']
                 and time.time_ns() // 1_000_000 < result['valid_until_ms'])
        return {'status': 'ok' if available and fresh else 'degraded',
                'camera_id': camera.camera_id, 'task': TASK,
                'stream_session_id': camera.session_id, 'session_generation': camera.session_generation,
                'input_stream_session_id': camera.input_session_id(),
                'tracking_context_id': camera.tracking_context_id if self.algorithm == 'botsort' else None,
                'capture': capture, 'components': dict(camera.states), 'inflight': camera.inflight,
                'inference_attempts': camera.attempts, 'inference_count': camera.inferences,
                'published_count': camera.published, 'discarded_stale_results': camera.discarded,
                'failures': camera.failures, 'last_analyzed_frame_id': camera.last_attempt,
                'last_published_frame_id': result['frame_id'] if result else None,
                'recent_inferences': list(camera.recent)}

    def health(self):
        cameras = {camera.camera_id: self._camera_health(camera) for camera in self._order}
        workers = [worker.snapshot() for worker in self._workers]
        alive = bool(self._tasks) and all(not task.done() for task in self._tasks)
        snapshot = {'status': 'ok' if alive and all(c['status'] == 'ok' for c in cameras.values()) else 'degraded',
                'algorithm': self.algorithm, 'tracking': self.algorithm == 'botsort',
                'service_session_id': self._service_id, 'cameras': cameras, 'workers': workers,
                'analysis_task_alive': alive, 'worker_count': len(workers),
                'running_workers': sum(w.get('pid') is not None for w in workers),
                'worker_idle_seconds': self._worker_idle, 'frame_fresh_ms': FRAME_FRESH_MS,
                'active_inferences': sum(camera.inflight for camera in self._order),
                'model_initializations': sum(w['model_initializations'] for w in workers),
                'inference_interval_seconds': self._inference_interval, 'clients': len(self._subscriptions),
                'max_pending_messages_per_client': 2 * len(cameras)}
        if self._result_sink is not None:
            snapshot['result_handoff'] = {
                'handed_off_count': self._result_handoffs,
                'failure_count': self._result_failures, 'last_error': self._result_error,
            }
        return snapshot

    def _status_message(self, camera, component='service', state=None):
        return {'type': 'status', 'camera_id': camera.camera_id, 'task': TASK,
                'algorithm': self.algorithm,
                'service_session_id': self._service_id, 'stream_session_id': camera.session_id,
                'input_stream_session_id': camera.input_session_id(),
                'tracking_context_id': camera.tracking_context_id if self.algorithm == 'botsort' else None,
                'session_generation': camera.session_generation,
                'stream_epoch': camera.grabber.snapshot()['stream_epoch'],
                'component': component, 'state': state or camera.states['analyzer']['state'],
                'components': dict(camera.states), 'capture': camera.grabber.snapshot(), 'sent_at_ms': time.time_ns() // 1_000_000}

    def subscribe(self, include_frames=False):
        if len(self._subscriptions) >= MAX_CLIENTS:
            raise OverflowError('Analysis WebSocket client limit reached')
        subscription = Subscription(((camera.camera_id, TASK) for camera in self._order), include_frames)
        self._subscriptions.add(subscription)
        for camera in self._order:
            subscription.put(self._status_message(camera))
        return subscription

    def unsubscribe(self, subscription):
        self._subscriptions.discard(subscription)

    def _publish(self, message, include_frames=None):
        for subscription in self._subscriptions:
            if include_frames is None or subscription.include_frames == include_frames:
                subscription.put(message)

    def _start_image(self, camera, captured, session):
        if (camera.camera_id in self._image_tasks
                or not any(sub.include_frames for sub in self._subscriptions)):
            return None
        result_ready = asyncio.get_running_loop().create_future()
        task = asyncio.create_task(self._deliver_image(camera, captured, session, result_ready))
        self._image_tasks[camera.camera_id] = task
        task.add_done_callback(lambda _: self._image_tasks.pop(camera.camera_id, None))
        return result_ready

    async def _deliver_image(self, camera, captured, session, result_ready):
        try:
            frame = await asyncio.to_thread(encode_frame, captured.frame, captured.frame_id)
            result = await result_ready
            latest = camera.grabber.latest_frame()
            now = time.time_ns() // 1_000_000
            if (result is None or self._stop_event.is_set() or latest is None
                    or latest.stream_epoch != captured.stream_epoch or camera.session_id != session
                    or now >= result['valid_until_ms']):
                return
            self._publish({**result, 'frame': frame, 'sent_at_ms': now}, include_frames=True)
        except Exception as exc:
            # Diagnostic image failure must not invalidate a successful inference/tracker.
            logger.warning('%s diagnostic image failed: %s: %s', camera.camera_id, type(exc).__name__, exc)

    def _set_status(self, camera, component, state, error=None):
        updated = {'state': state, 'error': error}
        if camera.states.get(component) != updated:
            camera.states[component] = updated
            logger.info('%s %s state=%s error=%s', camera.camera_id, component, state, error)
            self._publish(self._status_message(camera, component, state))

    def _capture_status(self, camera_id, state, error, epoch):
        camera = self._cameras[camera_id]
        if self.algorithm == 'botsort' and camera.stream_epoch is not None and epoch != camera.stream_epoch:
            camera.invalidate()
            camera.last_attempt = 0
        camera.stream_epoch = epoch
        if state != 'streaming':
            camera.last_result = None
        self._set_status(camera, 'capture', state, error)

    async def _wait(self, seconds):
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def _send_heartbeat(self):
        while not self._stop_event.is_set():
            for camera in self._order:
                self._refresh_waiting(camera)
                self._publish(self._status_message(camera))
            await self._wait(1)

    def _fresh_frame(self, camera):
        if camera.grabber.snapshot()['state'] != 'streaming':
            return None
        frame = camera.grabber.latest_frame()
        now = time.time_ns() // 1_000_000
        if (frame is None or frame.frame_id <= camera.last_attempt
                or not 0 <= now - (getattr(frame, 'decode_ts_ms', 0) or frame.frame_ts_ms) < FRAME_FRESH_MS
                or not 0 <= now - frame.frame_ts_ms < RESULT_TTL_MS):
            return None
        return frame

    def _refresh_waiting(self, camera):
        capture = camera.grabber.snapshot()
        if capture['state'] != 'streaming':
            self._set_status(camera, 'analyzer', 'waiting_source')
        elif not camera.inflight:
            # Keep inference failures visible until this camera gets a retry.
            if camera.states['analyzer']['state'] in {'worker_timeout', 'inference_error', 'model_error'}:
                return
            fresh = (capture.get('latest_decode_ts_ms') or capture.get('latest_frame_ts_ms'))
            if fresh is not None and time.time_ns() // 1_000_000 - fresh >= FRAME_FRESH_MS:
                self._set_status(camera, 'analyzer', 'no_new_frame')
            elif camera.last_result is not None:
                self._set_status(camera, 'analyzer', 'ready')
            else:
                self._set_status(camera, 'analyzer', 'waiting_worker')

    def _claim(self, worker=None):
        # Reserve only a camera with a fresh frame. No frame FIFO during model loading.
        now = self._loop.time()
        for offset in range(len(self._order)):
            index = (self._cursor + offset) % len(self._order)
            if self.algorithm == 'botsort' and index % len(self._workers) != worker.slot:
                continue
            camera = self._order[index]
            if camera.inflight or camera.next_at > now or self._fresh_frame(camera) is None:
                continue
            camera.inflight = True
            self._cursor = (index + 1) % len(self._order)
            return camera
        return None

    async def _run_worker(self, worker):
        last_used = self._loop.time()
        try:
            while not self._stop_event.is_set():
                if self.algorithm != 'botsort' and not worker.ready and any(w.ready and not getattr(w, 'assigned_camera', None)
                                            for w in self._workers):
                    await self._wait(0.02)
                    continue
                camera = self._claim(worker)
                if camera is None:
                    if worker.ready and self._loop.time() - last_used >= self._worker_idle:
                        await worker.stop()
                    await self._wait(0.02)
                    continue
                try:
                    worker.assigned_camera = camera.camera_id
                    if not worker.ready:
                        try:
                            async with self._loading_lock:
                                if self.algorithm == 'botsort':
                                    # Restart loses every tracker owned by this process.
                                    for index, owned in enumerate(self._order):
                                        if index % len(self._workers) == worker.slot:
                                            owned.invalidate()
                                self._set_status(camera, 'analyzer', 'loading_model')
                                await worker.start()
                        except Exception as exc:
                            worker.last_error = f'{type(exc).__name__}: {exc}'[:1000]
                            self._set_status(camera, 'analyzer', 'model_error', worker.last_error)
                            await self._backoff(worker)
                            continue
                    last_used = self._loop.time()
                    # Source may have vanished during loading: never submit the reserved old frame.
                    captured = self._fresh_frame(camera)
                    if captured is None:
                        self._refresh_waiting(camera)
                        continue
                    if self.algorithm == 'botsort':
                        shape = captured.frame.shape[:2]
                        if camera.source_shape is not None and camera.source_shape != shape:
                            camera.invalidate()
                            self._publish(self._status_message(camera))
                        camera.source_shape = shape
                    camera.last_attempt = captured.frame_id
                    camera.attempts += 1
                    # Full-rate inference is shared by all synchronized viewers. No
                    # backlog: overload drops whole frame/result pairs, never reuses boxes.
                    interval = self._inference_interval
                    if self.algorithm != 'botsort' and any(sub.include_frames for sub in self._subscriptions):
                        interval = min(interval, 1 / SYNC_FPS)
                    camera.next_at = self._loop.time() + interval
                    await self._analyze(worker, camera, captured)
                finally:
                    worker.assigned_camera = None
                    camera.inflight = False
                    self._refresh_waiting(camera)
        finally:
            await worker.stop()

    async def _backoff(self, worker):
        delay = self._retry_delays.get(worker.slot, self._worker_retry)
        self._retry_delays[worker.slot] = min(delay * 2, self._worker_retry_max)
        logger.warning('worker %s retry in %.1fs: %s', worker.slot, delay, worker.last_error)
        # Wait per worker: switching cameras or reaching ready must not reset failures.
        await self._wait(delay)

    async def _analyze(self, worker, camera, captured):
        session = camera.session_id
        input_session = camera.input_session_id(captured)
        tracking_context = camera.tracking_context_id
        session_generation = camera.session_generation
        worker_generation = worker.generation
        if camera.tracking_started_at_ms is None:
            camera.tracking_started_at_ms = captured.frame_ts_ms
        tracking_started_at_ms = camera.tracking_started_at_ms
        self._set_status(camera, 'analyzer', 'detecting')
        # At most one diagnostic image per camera; ordinary live results never wait for it.
        image_result = self._start_image(camera, captured, session)
        try:
            if self.algorithm == 'botsort':
                metadata = {'camera_id': camera.camera_id, 'stream_session_id': input_session or session,
                            'tracking_context_id': tracking_context,
                            'stream_epoch': captured.stream_epoch, 'frame_id': captured.frame_id,
                            'frame_ts_ms': captured.frame_ts_ms,
                            'decode_ts_ms': getattr(captured, 'decode_ts_ms', 0) or captured.frame_ts_ms,
                            'media_pts_ms': getattr(captured, 'media_pts_ms', None)}
                options = {'full_results': True} if self._result_sink is not None else {}
                detections, inference_ms = await worker.infer(captured.frame, metadata, **options)
            else:
                options = {'full_results': True} if self._result_sink is not None else {}
                detections, inference_ms = await worker.infer(captured.frame, **options)
            if self._sample_pipeline is not None:
                try:
                    self._sample_pipeline.offer(captured, detections,
                        tracking_context_id=tracking_context, algorithm=self.algorithm)
                except Exception:
                    logger.exception('%s sample handoff failed', camera.camera_id)
            if self._result_sink is not None:
                try:
                    factory = partial(frame_result,
                        FrameResultInput.from_capture(captured), detections,
                        camera_id=camera.camera_id, algorithm=self.algorithm,
                        tracking_session=session, session_generation=session_generation,
                        tracking_started_at_ms=tracking_started_at_ms,
                        worker_slot=worker.slot, worker_generation=worker_generation,
                        processed_at_ms=time.time_ns() // 1_000_000)
                    deferred = getattr(self._result_sink, 'defer', None)
                    # Worker IPC transfers a fresh detection list; it is not mutated after handoff.
                    delivery = (deferred(factory) if callable(deferred)
                                else self._result_sink(factory()))
                    if inspect.isawaitable(delivery):
                        if inspect.iscoroutine(delivery):
                            delivery.close()
                        raise TypeError('result_sink must hand off synchronously')
                    self._result_handoffs += 1
                    self._result_error = None
                except Exception as exc:
                    # Persistence must not reset a successful model or its tracker.
                    self._result_failures += 1
                    self._result_error = f'{type(exc).__name__}: {exc}'[:1000]
                    logger.error('%s result handoff failed: %s', camera.camera_id, self._result_error)
            self._retry_delays.pop(worker.slot, None)
            camera.inferences += 1
            camera.recent.append({'frame_id': captured.frame_id, 'stream_epoch': captured.stream_epoch,
                                  'inference_ms': inference_ms, 'worker_slot': worker.slot,
                                  'worker_generation': worker.generation,
                                  'frame_to_result_ms': time.time_ns() // 1_000_000 - captured.frame_ts_ms})
            self._set_status(camera, 'analyzer', 'ready')
            latest = camera.grabber.latest_frame()
            completed = time.time_ns() // 1_000_000
            if (latest is None or latest.stream_epoch != captured.stream_epoch
                    or camera.session_id != session or completed - captured.frame_ts_ms >= RESULT_TTL_MS):
                camera.discarded += 1
                return
            result = {'type': 'detections', 'camera_id': camera.camera_id, 'task': TASK,
                      'algorithm': self.algorithm,
                      'service_session_id': self._service_id, 'stream_session_id': session,
                      'input_stream_session_id': input_session,
                      'tracking_context_id': tracking_context if self.algorithm == 'botsort' else None,
                      'session_generation': camera.session_generation,
                      'frame_ts_ms': captured.frame_ts_ms, 'timestamp_kind': getattr(captured, 'timestamp_kind', 'decode_wall_clock'),
                      'decode_ts_ms': getattr(captured, 'decode_ts_ms', captured.frame_ts_ms),
                      'media_pts_ms': getattr(captured, 'media_pts_ms', None),
                      'worker_slot': worker.slot, 'worker_generation': worker.generation,
                      'completed_at_ms': completed, 'valid_until_ms': captured.frame_ts_ms + RESULT_TTL_MS,
                      'source_width': captured.source_width, 'source_height': captured.source_height,
                      'inference_ms': inference_ms, 'detections': detections[:500],
                      'frame_id': captured.frame_id, 'stream_epoch': captured.stream_epoch,
                      'sent_at_ms': completed}
            camera.last_result = result
            camera.published += 1
            self._publish(result, include_frames=False)
            if image_result is not None and not image_result.done():
                image_result.set_result(result)
        except Exception as exc:
            camera.failures += 1
            camera.invalidate()
            state = 'worker_timeout' if isinstance(exc, TimeoutError) else 'inference_error'
            self._set_status(camera, 'analyzer', state, f'{type(exc).__name__}: {exc}'[:1000])
            logger.warning('%s %s; worker %s %s', camera.camera_id, state, worker.slot,
                           'retained' if worker.ready else 'will reload')
            await self._backoff(worker)
        finally:
            if image_result is not None and not image_result.done():
                image_result.set_result(None)
