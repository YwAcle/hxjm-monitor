"""Reliable producer path, independent of WebSocket queues and display expiry."""
import asyncio
import logging
import math
import time
from copy import deepcopy
from types import SimpleNamespace
from urllib.parse import urlencode

from .tracking_client import BusinessClient, BusinessError
from .tracking_spool import ResultSpool, canonical_bytes
from .persistence_config import valid_uuid
from .tracking_state import new_id, instant, after, timestamp, frame_fact

logger = logging.getLogger(__name__)


class PersistenceError(Exception):
    pass


class ResultPublisher:
    def __init__(self, config, client=None, spool=None, on_confirmed=None):
        if on_confirmed is not None and not callable(on_confirmed):
            raise ValueError('on_confirmed must be callable')
        self.config = config
        self.on_confirmed = on_confirmed
        self.client = client or BusinessClient(config.business_base_url, config.service_id,
                                               config.service_token, config.timeout)
        reserve = min(config.max_bytes // 2, max(4 * 1024 ** 2, config.batch_bytes * (len(config.sources) + 1) * 2))
        self.spool = spool or ResultSpool(config.spool_dir, config.max_bytes, reserve)
        self.inputs, self.contexts = {}, {}
        self.tasks = []
        self.stopping = False
        self._stop_event = asyncio.Event()
        self.blocked = {}
        self.error = None
        self.generated = self.confirmed = self.rejected = 0
        self.last_success = None
        self.paused_at = None

    async def start(self):
        await asyncio.to_thread(self._recover)
        self.tasks = [asyncio.create_task(self._lane(camera), name='result-writer-' + camera)
                      for camera in self.config.sources]

    def _recover(self):
        # Old live tracker state cannot survive a process restart. Drain its facts first.
        # Recover the last durable frame even if the producer died before updating state.
        latest = {}
        for _, job in self.spool.entries():
            if job['lane'] not in self.config.sources:
                raise ValueError('Pending result lane is missing from the configured source map')
            if job['kind'] == 'frame':
                payload = job['payload']
                latest[payload['context_id']] = max(latest.get(payload['context_id'], ''), payload['frame']['occurred_at'])
        states = self.spool.all_states()
        for state in states:
            if state['kind'] == 'context':
                last = max(state['last_at'], latest.get(state['id'], ''))
                self.spool.merge_state(state['id'], {'last_at': last})
                self._close_context(state['id'], 'observation_interrupted', 'service_restart')
        for state in states:
            if state['kind'] == 'input':
                # Every context records the same public input ID, never an unrelated decoder's session.
                last = max([state['last_at']] + [max(c['last_at'], latest.get(c['id'], '')) for c in states
                                                if c['kind'] == 'context' and c['input_id'] == state['id']])
                self.spool.merge_state(state['id'], {'last_at': last})
                self._close_input(state['id'], 'service_restart')

    def can_accept(self):
        try:
            available = not self.error and self.spool.can_accept()
            if not available and self.paused_at is None:
                self.paused_at = instant(time.time_ns() // 1_000_000)
            return available
        except OSError:
            self.error = 'SPOOL_UNAVAILABLE'
            return False

    def health(self):
        try:
            snapshot = self.spool.snapshot()
            available = self.spool.can_accept()
        except (OSError, ValueError, KeyError, TypeError):
            self.error = 'SPOOL_UNAVAILABLE'
            snapshot, available = {}, False
        return dict(enabled=True, state='degraded' if self.error or self.blocked or not available else 'ready',
                    process_generated_frames=self.generated, process_confirmed_frames=self.confirmed,
                    process_rejected_attempts=self.rejected,
                    **snapshot,
                    last_success_at=self.last_success, blocked_lanes=dict(self.blocked), error=self.error,
                    unpublished_temporary_files=self.spool.recovery_temporaries)

    async def begin_frame(self, camera, captured, service_id, component_session):
        return await self._durable(self._begin_frame, camera, captured, service_id, component_session)

    async def _durable(self, operation, *args):
        task = asyncio.create_task(asyncio.to_thread(operation, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise
        except (OSError, ValueError, KeyError, TypeError):
            self.error = 'PERSISTENCE_ENQUEUE_FAILED'
            raise PersistenceError(self.error) from None

    def _begin_frame(self, camera, captured, service_id, component_session):
        with self.spool.mutex:
            occurred = instant(captured.frame_ts_ms)
            previous = self.inputs.get(camera)
            identity = [service_id, captured.stream_epoch]
            pts = getattr(captured, 'media_pts_ms', None)
            if not isinstance(pts, (int, float)) or not math.isfinite(pts) or pts < 0:
                pts = None
            # A clock regression cannot silently change an existing public time axis.
            reset = previous and (identity != previous['identity'] or occurred < previous['last_at']
                                  or (pts is not None and previous.get('last_pts') is not None and pts < previous['last_pts']))
            if reset:
                if camera in self.contexts:
                    self._close_context(self.contexts.pop(camera), 'observation_interrupted', 'input_reset')
                self._close_input(previous['id'], 'input_reset')
                previous = None
            if previous is None:
                mapping = self.config.sources[camera]
                ident = new_id()
                origin = captured.frame_ts_ms
                if isinstance(pts, (int, float)) and pts >= 0:
                    origin -= pts
                previous = dict(kind='input', id=ident, camera=camera, identity=identity,
                                source=mapping['source_id'], stream=mapping['camera_stream_id'],
                                started_at=occurred, last_at=occurred, last_pts=pts,
                                open_request=dict(request_id=new_id(), source_id=mapping['source_id'],
                                                  stream_session_id=ident, session_key='analysis:' + ident,
                                                  camera_stream_id=mapping['camera_stream_id'], started_at=occurred,
                                                  time_origin_at=instant(origin), time_basis='ingest_clock',
                                                  source_timezone=mapping.get('timezone', 'Asia/Shanghai'),
                                                  source_width=captured.source_width, source_height=captured.source_height))
                self.spool.save_state(ident, previous)
                self.inputs[camera] = previous
            context_id = self.contexts.get(camera)
            shape = [captured.source_width, captured.source_height]
            context = self.spool.load_state(context_id) if context_id else None
            if context and self.paused_at:
                self._close_context(context_id, 'observation_interrupted', 'analysis_backpressure',
                                    gap_start=self.paused_at, gap_end=occurred)
                context = None
            if context and (context['component_session'] != component_session or context['shape'] != shape):
                self._close_context(context_id, 'observation_interrupted', 'tracking_reset')
                context = None
            if context is None:
                context_id = new_id()
                context = dict(kind='context', id=context_id, input_id=previous['id'], camera=camera,
                               component_session=component_session, shape=shape,
                               started_at=occurred, last_at=occurred, result_set_id=new_id(),
                               context_key=service_id + ':' + component_session,
                               submit_request_id=new_id(), start_request_id=new_id(), tracks={},
                               instance_id=self.config.sources[camera]['instance_id'],
                               implementation_code=self.config.implementation_code,
                               implementation_version=self.config.implementation_version,
                               capability_code=self.config.capability_code, service_id=self.config.service_id,
                               parameters=getattr(self.config, 'parameters', {}))
                self.spool.save_state(context_id, context)
                self.spool.enqueue(camera, 'open', {'context_id': context_id})
                self.contexts[camera] = context_id
            # Other cameras close their old contexts on their next frame too.
            if self.paused_at and all(self.spool.load_state(c)['started_at'] >= self.paused_at for c in self.contexts.values()):
                self.paused_at = None
            return context_id

    async def record(self, context_id, captured, detections, completed_ms, removed_tracks=()):
        return await self._durable(self._record, context_id, captured, detections, completed_ms, removed_tracks)

    def _record(self, context_id, captured, detections, completed_ms, removed_tracks):
        with self.spool.mutex:
            context = self.spool.load_state(context_id)
            fact = frame_fact(captured, detections)
            # Disambiguate frame counters belonging to different ingest contexts.
            fact['producer_result_key'] = context['input_id'] + ':frame:' + str(captured.frame_id)
            payload = dict(context_id=context_id, frame=fact, processed_at=instant(completed_ms),
                           component=dict(frame_ts_ms=captured.frame_ts_ms,
                                          decode_ts_ms=getattr(captured, 'decode_ts_ms', None),
                                          timestamp_kind=getattr(captured, 'timestamp_kind', 'decode_wall_clock')))
            self.spool.enqueue(context['camera'], 'frame', payload)
            self.generated += 1
            tracks = context['tracks']
            for target in fact['targets']:
                if not target['is_prediction']:
                    tracks[str(target['local_track_id'])] = fact['occurred_at']
            self.spool.merge_state(context_id, {'last_at': fact['occurred_at'], 'tracks': tracks})
            input_state = self.spool.merge_state(context['input_id'], {'last_at': fact['occurred_at'],
                                                                       'last_pts': getattr(captured, 'media_pts_ms', None)})
            self.inputs[context['camera']] = input_state
            known = [int(i) for i in removed_tracks if str(i) in tracks]
            if known:
                self.spool.enqueue(context['camera'], 'tracks_close', dict(context_id=context_id,
                                   request_id=new_id(), local_track_ids=known, end_reason='normal',
                                   ended_at=after(fact['occurred_at']), reason_code='tracker_removed'))
                for local in known:
                    tracks.pop(str(local), None)
                self.spool.merge_state(context_id, {'tracks': tracks})
            # The sample pipeline needs the public IDs that appear in /results/register,
            # not the decoder-local frame counter.
            return SimpleNamespace(source_id=input_state['source'],
                                   stream_session_id=context['input_id'],
                                   frame_id=fact['frame_id'])

    async def interrupt(self, camera, reason='inference_error', input_ended=False):
        await self._durable(self._interrupt, camera, reason, input_ended)

    async def failure(self, camera, captured):
        def record_failure():
            with self.spool.mutex:
                context = self.contexts.pop(camera, None)
                if context:
                    occurred = instant(captured.frame_ts_ms)
                    self._close_context(context, 'observation_interrupted', 'analysis_failed',
                                        gap_start=occurred, gap_end=after(occurred))
        await self._durable(record_failure)

    def _interrupt(self, camera, reason, input_ended):
        with self.spool.mutex:
            context = self.contexts.pop(camera, None)
            if context:
                self._close_context(context, 'observation_interrupted', reason)
            if input_ended and camera in self.inputs:
                self._close_input(self.inputs.pop(camera)['id'], reason)

    def _close_context(self, context_id, end_reason, reason, gap_start=None, gap_end=None):
        state = self.spool.load_state(context_id)
        payload = state.get('close_payload') or dict(context_id=context_id,
                           request_id=context_id + ':close', end_reason=end_reason,
                           ended_at=after(state['last_at']), reason_code=reason)
        if gap_start and gap_end and gap_end > gap_start and not state.get('close_payload'):
            payload.update(gap_start_at=gap_start, gap_end_at=gap_end)
        self.spool.merge_state(context_id, {'close_payload': payload})
        self.spool.enqueue(state['camera'], 'context_close', payload, key=context_id)
        self.spool.merge_state(context_id, {'close_queued': True})

    def _close_input(self, input_id, reason):
        state = self.spool.load_state(input_id)
        payload = state.get('close_payload') or dict(input_id=input_id,
                           request_id=input_id + ':close', ended_at=after(state['last_at']), reason_code=reason)
        self.spool.merge_state(input_id, {'close_payload': payload})
        self.spool.enqueue(state['camera'], 'input_close', payload, key=input_id)
        self.spool.merge_state(input_id, {'close_queued': True})

    def _bootstrap(self, context_id):
        context = self.spool.load_state(context_id)
        input_state = self.spool.load_state(context['input_id'])
        if context['service_id'] != self.config.service_id:
            raise BusinessError('PRODUCER_IDENTITY_CHANGED')
        if not input_state.get('opened'):
            opened = self.client.call('/streams/open', input_state['open_request'])
            if (opened.get('stream_session_id') != input_state['id'] or opened.get('source_id') != input_state['source']
                    or opened.get('state') != 'open'):
                raise BusinessError('INVALID_STREAM_RESPONSE', True)
            self.spool.merge_state(input_state['id'], {'opened': True})
        instance_id = context['instance_id']
        if not context.get('submitted'):
            result = self.client.call('/instances?' + urlencode({'instance_id': instance_id}))
            instances = result.get('items', [])
            if (not isinstance(instances, list) or len(instances) != 1 or not isinstance(instances[0], dict)
                    or instances[0].get('implementation_code') != context['implementation_code']
                    or instances[0].get('implementation_version') != context['implementation_version']):
                raise BusinessError('IMPLEMENTATION_MISMATCH')
            body = dict(request_id=context['submit_request_id'], task_kind='tracking',
                        business_key='tracking:' + context_id, capability_code=context['capability_code'],
                        task_mode='continuous', input=dict(kind='live_video', source_id=input_state['source'],
                                                         stream_session_id=input_state['id']),
                        requested_outputs=['detection.frame'], parameters=context.get('parameters', {}), instance_id=instance_id)
            submitted = self.client.call('/tasks', body)
            if (not self._public_id(submitted.get('task_id')) or type(submitted.get('revision')) is not int
                    or submitted['revision'] < 1):
                raise BusinessError('INVALID_TASK_RESPONSE', True)
            context = self.spool.merge_state(context_id, {'submitted': submitted})
        if not context.get('started'):
            started = self.client.call('/tasks/start', dict(request_id=context['start_request_id'],
                                       task_id=context['submitted']['task_id'],
                                       expected_revision=context['submitted']['revision'], instance_id=instance_id))
            if not self._public_id(started.get('run_id')) or started.get('task_id') != context['submitted']['task_id']:
                raise BusinessError('INVALID_START_RESPONSE', True)
            context = self.spool.merge_state(context_id, {'started': started})
        return context, input_state

    @staticmethod
    def _public_id(value):
        try:
            return isinstance(value, str) and bool(valid_uuid(value))
        except ValueError:
            return False

    @staticmethod
    def _acknowledgement(result, expected):
        accepted = result.get('accepted_result_ids')
        duplicate = result.get('duplicate_result_ids')
        rejected = result.get('rejected_results')
        if (not isinstance(accepted, list) or not isinstance(duplicate, list) or not isinstance(rejected, list)
                or any(not isinstance(i, str) for i in accepted + duplicate)
                or any(not isinstance(i, dict) or not isinstance(i.get('result_id'), str)
                       or type(i.get('retryable')) is not bool for i in rejected)):
            raise BusinessError('INVALID_RESULT_ACK', True)
        confirmed = accepted + duplicate
        failed = [i['result_id'] for i in rejected]
        if (len(set(confirmed)) != len(confirmed) or len(set(failed)) != len(failed)
                or set(confirmed) & set(failed) or set(confirmed) | set(failed) != expected):
            raise BusinessError('INVALID_RESULT_ACK', True)
        return set(confirmed), rejected, set(failed)

    @staticmethod
    def _expired(at):
        return timestamp(at) + 7 * 86400 <= time.time()

    def _expiry_receipt(self, count, last_result):
        key = 'ffffffff-ffff-4fff-8fff-ffffffffffff'
        try:
            value = self.spool.load_state(key)
        except FileNotFoundError:
            value = dict(kind='expiry_receipt', count=0)
        value.update(count=value['count'] + count, last_result_id=last_result,
                     updated_at=instant(time.time_ns() // 1_000_000))
        self.spool.save_state(key, value)

    def _frame_request(self, context, input_state, jobs):
        frames = [job['payload']['frame'] for _, job in jobs]
        return dict(request_id=new_id(), task_id=context['started']['task_id'], run_id=context['started']['run_id'],
                    result_set_id=context['result_set_id'], set_key='tracking:' + context['id'],
                    capability_code=context['capability_code'], result_type='detection.frame', schema_version='1',
                    source_id=input_state['source'], stream_session_id=input_state['id'], tracking_context_id=context['id'],
                    tracking_context=dict(context_key=context['context_key'], started_at=context['started_at'], reset_reason=None),
                    processed_at=max(job['payload']['processed_at'] for _, job in jobs), results=frames,
                    analysis_coverage=dict(start_at=min(f['occurred_at'] for f in frames),
                                           end_at=after(max(f['occurred_at'] for f in frames)), closed=True,
                                           analyzed_frame_count=len(frames), frame_ids=[f['frame_id'] for f in frames], gaps=[]))

    def _deliver_frames(self, path, job, candidates):
        delivery = job.get('delivery')
        if delivery is None:
            selected = []
            size = 0
            context_id = job['payload']['context_id']
            for candidate in candidates:
                item = candidate[1]
                if item['kind'] != 'frame' or item['payload']['context_id'] != context_id:
                    break
                amount = len(canonical_bytes(item['payload']))
                if selected and size + amount > self.config.batch_bytes:
                    break
                selected.append(candidate)
                size += amount
                if len(selected) >= self.config.batch_frames:
                    break
            context, input_state = self._bootstrap(context_id)
            delivery = dict(request=self._frame_request(context, input_state, selected),
                            members=[p.name for p, _ in selected], confirmed=[], complete=False)
            job['delivery'] = delivery
            self.spool.update(path, job)
        if not delivery['complete']:
            body = delivery['request']
            result = self.client.call('/results/register', body)
            expected = {f['result_id'] for f in body['results']}
            accepted, rejected, failed = self._acknowledgement(result, expected)
            if self.on_confirmed is not None:
                try:
                    # Confirm before a partial retry mutates the frozen request. The
                    # sample pipeline filters by accepted/duplicate ids itself.
                    self.on_confirmed(deepcopy(body), deepcopy(result))
                except Exception:
                    # Sampling is downstream of confirmed persistence; a failure there
                    # must not resurrect or re-send an already acknowledged batch.
                    logger.exception('Confirmed-result callback failed')
            delivery['confirmed'] = sorted(set(delivery['confirmed']) | accepted)
            self.spool.update(path, job)
            if rejected:
                self.rejected += len(rejected)
                permanent = [f for f in rejected if f.get('retryable') is not True]
                if permanent:
                    raise BusinessError('RESULT_REJECTED')
                # A completed partial request is cached by the server. Use a new request
                # only for the unconfirmed subset, retaining immutable frame IDs and keys.
                body['request_id'] = new_id()
                body['results'] = [f for f in body['results'] if f['result_id'] in failed]
                self.spool.update(path, job)
                raise BusinessError('RESULTS_PENDING', True)
            delivery['complete'] = True
            self.spool.update(path, job)
        for name in delivery['members'][1:]:
            self.spool.remove(self.spool.jobs / name)
        self.spool.remove(path)  # Leader is removed last; recovery reuses its frozen delivery.
        self.confirmed += len(delivery['confirmed'])
        if not delivery.get('expired'):
            self.last_success = instant(time.time_ns() // 1_000_000)

    def _process(self, entries):
        path, job = entries[0]
        if job.get('complete'):
            self.spool.remove(path)
            return
        payload, kind = job['payload'], job['kind']
        if kind == 'frame':
            delivery = job.get('delivery')
            if not delivery and self._expired(payload['frame']['occurred_at']):
                self._expiry_receipt(1, payload['frame']['result_id'])
                self.spool.remove(path)
                return
            if delivery and not delivery['complete'] and all(self._expired(f['occurred_at']) for f in delivery['request']['results']):
                self._expiry_receipt(len(delivery['request']['results']), delivery['request']['results'][-1]['result_id'])
                delivery['complete'] = True
                delivery['expired'] = True
                self.spool.update(path, job)
            self._deliver_frames(path, job, entries)
            return
        if kind == 'input_close':
            state = self.spool.load_state(payload['input_id'])
            if state.get('opened') and not self._expired(state['last_at']):
                closed = self.client.call('/streams/close', dict(request_id=payload['request_id'], stream_session_id=state['id'],
                                 expected_state='open', state='interrupted', occurred_at=payload['ended_at'],
                                 ended_at=payload['ended_at'], reason_code=payload['reason_code']))
                if closed.get('stream_session_id') != state['id'] or closed.get('state') != 'interrupted':
                    raise BusinessError('INVALID_STREAM_RESPONSE', True)
            job['complete'] = True
            self.spool.update(path, job)
            self.spool.delete_state(state['id'])
            self.spool.remove(path)
            return
        context = self.spool.load_state(payload['context_id'])
        if self._expired(context['last_at']):
            if kind == 'context_close':
                job['complete'] = True
                self.spool.update(path, job)
                self.spool.delete_state(context['id'])
            self.spool.remove(path)
            return
        context, input_state = self._bootstrap(payload['context_id'])
        if kind != 'open':
            body = dict(request_id=payload['request_id'], source_id=input_state['source'],
                        task_id=context['started']['task_id'], run_id=context['started']['run_id'],
                        tracking_context_id=context['id'], end_reason=payload['end_reason'], ended_at=payload['ended_at'],
                        reason_code=payload['reason_code'], close_context=kind == 'context_close',
                        local_track_ids=payload.get('local_track_ids', []))
            for key in ('gap_start_at', 'gap_end_at'):
                if key in payload:
                    body[key] = payload[key]
            closed = self.client.call('/tracking/close', body)
            if closed.get('tracking_context_id') != context['id'] or closed.get('context_closed') is not body['close_context']:
                raise BusinessError('INVALID_TRACKING_RESPONSE', True)
        if kind == 'context_close':
            job['complete'] = True
            self.spool.update(path, job)
            self.spool.delete_state(context['id'])
        self.spool.remove(path)

    def _blocked_expired(self, entries):
        job = entries[0][1]
        if job.get('complete'):
            return True
        payload = job['payload']
        if job['kind'] == 'frame':
            facts = job.get('delivery', {}).get('request', {}).get('results', [payload['frame']])
            return all(self._expired(f['occurred_at']) for f in facts)
        state_id = payload.get('context_id', payload.get('input_id'))
        return self._expired(self.spool.load_state(state_id)['last_at'])

    async def _pause(self, seconds):
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def _lane(self, camera):
        delay = 1.
        while not self.stopping:
            try:
                entries = self.spool.lane_entries(camera, self.config.batch_frames)
                if not entries:
                    await self._pause(.1)
                    continue
                if camera in self.blocked:
                    # Expiry is local and needs no working credentials or API.
                    if await asyncio.to_thread(self._blocked_expired, entries):
                        await asyncio.to_thread(self._process, entries)
                    else:
                        await self._pause(.1)
                    continue
                if (entries[0][1]['kind'] == 'frame' and not entries[0][1].get('delivery')
                        and len(entries) < self.config.batch_frames
                        and time.time() - entries[0][1]['queued_at'] < self.config.flush_seconds):
                    await self._pause(.05)
                    continue
                await asyncio.to_thread(self._process, entries)
                delay = 1.
            except BusinessError as exc:
                if not exc.retryable:
                    self.blocked[camera] = exc.code
                logger.warning('Result persistence camera=%s code=%s retryable=%s', camera, exc.code, exc.retryable)
                await self._pause(delay)
                delay = min(delay * 2, self.config.retry_max)
            except (OSError, ValueError, KeyError, TypeError):
                self.error = 'SPOOL_OR_PROTOCOL_ERROR'
                self.blocked[camera] = self.error
                logger.error('Result persistence camera=%s paused; durable queue retained', camera)
                await self._pause(delay)

    async def stop(self):
        self.stopping = True
        self._stop_event.set()
        try:
            for camera in list(self.inputs):
                await self.interrupt(camera, 'service_stopped', input_ended=True)
        finally:
            try:
                # Finish the bounded in-progress delivery; never cancel its file transaction.
                if self.tasks:
                    await asyncio.gather(*self.tasks)
            finally:
                self.spool.close()
