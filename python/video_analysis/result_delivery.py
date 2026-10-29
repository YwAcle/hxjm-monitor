"""Batch completed frame results off the inference loop, then replay disk requests."""
import asyncio
from collections import OrderedDict
from copy import deepcopy
import inspect
import logging
import math
import queue
import threading
import time
import uuid

from .frame_result import registration_request


logger = logging.getLogger(__name__)
OPERATION = 'results.register'


class ResultDispatcher:
    """One worker owns local batch writes and submission; no credentials are stored.

    units maps (source_id, algorithm) to real task/run/result-set references.
    window_for(frames) supplies explicit start_at/end_at/gaps and optionally
    closed (False by default). It must cover every frame in its batch.
    submit(actor_key, operation, payload) returns the API response data object;
    it obtains current credentials when called and may return an awaitable.
    """

    def __init__(self, spool, *, actor_key, units, window_for, submit,
                 batch_size=32, queue_size=256, flush_interval=0.2, close_for=None,
                 on_confirmed=None):
        if not isinstance(actor_key, str) or not actor_key:
            raise ValueError('actor_key must be a nonempty string')
        if not callable(units) and (not isinstance(units, dict) or not units):
            raise ValueError('At least one explicit source/execution unit is required')
        if not callable(window_for) or not callable(submit):
            raise ValueError('window_for and submit must be callable')
        if close_for is not None and not callable(close_for):
            raise ValueError('close_for must be callable')
        if on_confirmed is not None and not callable(on_confirmed):
            raise ValueError('on_confirmed must be callable')
        if (type(batch_size) is not int or batch_size <= 0
                or type(queue_size) is not int or queue_size <= 0
                or isinstance(flush_interval, bool)
                or not isinstance(flush_interval, (int, float))
                or not math.isfinite(flush_interval) or flush_interval <= 0):
            raise ValueError('Batch size, queue size and flush interval must be positive')
        self.spool = spool
        self.actor_key = actor_key
        self.units = units if callable(units) else deepcopy(units)
        self.window_for = window_for
        self.submit = submit
        self.close_for = close_for
        self.on_confirmed = on_confirmed
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._queue = queue.Queue(maxsize=queue_size)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._inflight = []
        self._prepared = None
        self._blocked = set()
        self._state = 'idle'
        self._error = None
        self._enqueued = self._persisted = self._confirmed = self._partial = self._rejected = 0
        self._invalid = 0
        self._invalid_error = None
        self._pending = 0
        for key, execution in (() if callable(self.units) else self.units.items()):
            if (not isinstance(key, tuple) or len(key) != 2
                    or not all(isinstance(value, str) and value for value in key)
                    or not isinstance(execution, dict)):
                raise ValueError('Each unit key must be (source_id, algorithm)')
            for name in ('task_id', 'run_id', 'result_set_id'):
                if uuid.UUID(execution[name]).int == 0:
                    raise ValueError(name + ' cannot be the zero UUID')
            for name in ('set_key', 'capability_code'):
                if not isinstance(execution.get(name), str) or not execution[name]:
                    raise ValueError(name + ' is required')

    def start(self):
        with self._lock:
            if self._thread is not None or self._stop.is_set():
                raise RuntimeError('Create a new dispatcher for another lifecycle')
            self._state = 'running'
            self._thread = threading.Thread(target=self._run, name='result-dispatcher', daemon=False)
            self._thread.start()

    def __call__(self, frame):
        """Hand off without disk/network I/O; queue.Full means no handoff occurred."""
        if not callable(self.units) and (frame.get('source_id'), frame.get('algorithm')) not in self.units:
            raise ValueError('No execution is configured for this source and algorithm')
        snapshot = deepcopy(frame)
        self._handoff(snapshot)

    def defer(self, factory):
        """Accept an owned frame factory; construct its historical payload off inference."""
        if not callable(factory):
            raise ValueError('Deferred frame factory must be callable')
        self._handoff(factory)

    def _handoff(self, snapshot):
        with self._lock:
            if self._state not in ('running', 'retrying') or self._stop.is_set():
                raise RuntimeError('Result dispatcher is not accepting frames')
            try:
                self._queue.put_nowait(snapshot)
            except queue.Full:
                self._rejected += 1
                self._error = 'Result handoff queue is full'
                raise
            self._enqueued += 1

    def status(self):
        with self._lock:
            return {'state': self._state, 'last_error': self._error,
                    'queued_frames': self._queue.qsize(), 'inflight_frames': len(self._inflight),
                    'enqueued_frames': self._enqueued, 'persisted_frames': self._persisted,
                    'confirmed_batches': self._confirmed, 'partial_batches': self._partial,
                    'invalid_frames': self._invalid, 'last_invalid_error': self._invalid_error,
                    'rejected_handoffs': self._rejected, 'pending_batches': self._pending,
                    'blocked_batches': len(self._blocked),
                    'thread_alive': self._thread is not None and self._thread.is_alive()}

    def stop(self, timeout=5):
        """Flush and stop; return thread exit, while status retains write failures."""
        with self._lock:
            self._stop.set()
            if self._state not in ('failed', 'stopped'):
                self._state = 'stopping'
            thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return thread is None or not thread.is_alive()

    def _failure(self, error, *, fatal=False):
        with self._lock:
            self._error = type(error).__name__ + ': ' + str(error)
            self._state = 'failed' if fatal else 'retrying'
        logger.error('Result delivery failed: %s', error)

    def _batch(self):
        frames = []
        deadline = time.monotonic() + self.flush_interval
        while len(frames) < self.batch_size:
            try:
                if self._stop.is_set():
                    item = self._queue.get_nowait()
                else:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    item = self._queue.get(timeout=remaining)
            except queue.Empty:
                break
            frames.append(item)
        return frames

    def _persist(self, frames):
        index = 0
        while index < len(frames):
            if callable(frames[index]):
                try:
                    frames[index] = frames[index]()
                except (ValueError, KeyError, TypeError) as error:
                    message = (type(error).__name__ + ': ' + str(error))[:1000]
                    with self._lock:
                        del frames[index]
                        self._invalid += 1
                        self._invalid_error = message
                    logger.error('Invalid deferred frame was not saved: %s', message)
                    continue
            index += 1
        groups = OrderedDict()
        for frame in frames:
            key = tuple(frame[name] for name in (
                'source_id', 'stream_session_id', 'tracking_context_id', 'algorithm'))
            groups.setdefault(key, []).append(frame)
        for key, group in groups.items():
            if self._prepared is None:
                execution = deepcopy(self.units(deepcopy(group)) if callable(self.units)
                                     else self.units[(key[0], key[3])])
                if key[2] is not None:
                    context = group[0]['tracking_context']
                    if any(frame['tracking_context'] != context for frame in group):
                        raise ValueError('One tracking context cannot have different definitions')
                    execution['tracking_context'] = deepcopy(context)
                coverage = deepcopy(self.window_for(deepcopy(group)))
                coverage.setdefault('closed', False)
                coverage.setdefault('gaps', [])
                coverage['frame_ids'] = [frame['result']['frame_id'] for frame in group]
                coverage['analyzed_frame_count'] = len(group)
                self._prepared = registration_request(group, execution, coverage, request_id=str(uuid.uuid4()))
            payload = self._prepared
            self.spool.put(self.actor_key, OPERATION, payload)
            self._prepared = None
            with self._lock:
                self._persisted += len(group)
                self._pending += 1
                # Retrying a later group must not recreate an already durable batch.
                persisted = {id(frame) for frame in group}
                frames[:] = [frame for frame in frames if id(frame) not in persisted]

    def _replay(self):
        keys = self.spool.pending()
        with self._lock:
            self._pending = len(keys)
        for key in keys:
            if key in self._blocked or self._stop.is_set():
                continue
            try:
                record = self.spool.read(key)
                if record['actor_key'] != self.actor_key or record['operation'] != OPERATION:
                    raise ValueError('Pending request belongs to another actor or operation')
                payload = record['payload']
                response = self.submit(record['actor_key'], record['operation'], deepcopy(payload))
                if inspect.isawaitable(response):
                    async def await_response():
                        return await response
                    response = asyncio.run(await_response())
                confirmed = set(response.get('accepted_result_ids', [])) | set(response.get('duplicate_result_ids', []))
                expected = {result['result_id'] for result in payload['results']}
                if self.on_confirmed is not None and expected & confirmed:
                    try:
                        self.on_confirmed(deepcopy(payload), deepcopy(response))
                    except Exception:
                        # A downstream sample failure cannot revoke a durable frame.
                        logger.exception('Result confirmation consumer failed')
                if (self.close_for is not None and expected == confirmed and not response.get('rejected_results')
                        and payload['analysis_coverage'].get('closed') is False):
                    # Persist the close before removing its parent, including across a restart.
                    self.spool.put(self.actor_key, OPERATION, self.close_for(deepcopy(payload)))
                if self.spool.acknowledge(key, response):
                    with self._lock:
                        self._confirmed += 1
                    continue
                self.spool.replace_unconfirmed(key, response)
                with self._lock:
                    self._partial += 1
            except (ValueError, KeyError, TypeError) as error:
                self._blocked.add(key)
                self._failure(error)
            except Exception as error:
                self._failure(error)
        pending_count = len(self.spool.pending())
        with self._lock:
            self._pending = pending_count
            if pending_count == 0 and self._state == 'retrying' and not self._stop.is_set():
                self._state, self._error = 'running', None

    def _run(self):
        while True:
            try:
                if self._stop.is_set() and not self._inflight and self._queue.empty():
                    break
                if not self._inflight and not self._stop.is_set():
                    self._replay()
                frames = self._inflight or self._batch()
                with self._lock:
                    self._inflight = frames
                if frames:
                    self._persist(frames)
                    with self._lock:
                        self._inflight = []
                if not self._stop.is_set():
                    self._replay()
            except (ValueError, KeyError, TypeError) as error:
                self._failure(error, fatal=True)
                return
            except Exception as error:
                self._failure(error)
                if self._stop.is_set():
                    # Keep already accepted memory until its NFS write succeeds.
                    time.sleep(self.flush_interval)
                else:
                    self._stop.wait(self.flush_interval)
        with self._lock:
            self._state = 'stopped'
