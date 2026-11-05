"""Four independent capture contexts, one fair JoyAI inference loop and one reviewer."""
import logging
import os
from pathlib import Path
import threading
import time
import uuid

from .input import InputHub
from .contracts import iso
from .evidence import FrameBuffer, build_evidence, review_frames
from .ledger import Ledger
from .observer import JoyAnalyzer
from .publisher import Publisher
from .review_runtime import OnDemandReviewer
from .verdict import VisionReviewer, ReviewFailure

log = logging.getLogger(__name__)


class Monitor:
    def __init__(self, config):
        self.config = config
        self.ledger = Ledger(Path(config['state_dir']) / 'delivery.sqlite3')
        self.publisher = Publisher(config, self.ledger)
        self.lock = threading.RLock()
        self.inference_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.threads = []
        self.hub = None
        self.cameras = {}
        self.buffers = {}
        self.observers = {}
        self.review = OnDemandReviewer(config, self.stop_event)
        self.joy_review = VisionReviewer(config['model_url'], 'jdopensource/JoyAI-VL-Interaction', timeout=90, max_tokens=800)
        self.last_error = None

    def start(self, camera_ids=None):
        with self.lock:
            if any(t.is_alive() for t in self.threads):
                return self.status()
            camera_ids = camera_ids or list(self.config['cameras'])
            if not camera_ids or len(set(camera_ids)) != len(camera_ids) or set(camera_ids) - self.config['cameras'].keys():
                raise ValueError('Select configured camera IDs only')
            self.publisher.deploy()
            self.stop_event.clear()
            self.buffers = {name: FrameBuffer(seconds=60, fps=self.config['sample_fps'], width=960) for name in camera_ids}
            self.observers = {name: JoyAnalyzer(self.config['observer_url'], timeout=90) for name in camera_ids}
            self.cameras = {name: {'source_id': self.config['cameras'][name]['source_id'], 'state': 'connecting', 'observations': 0, 'last_frame_at': None,
                                  'last_observed_at': None, 'session_id': None, 'last_error': None,
                                  'cooldowns': {}, 'skipped_candidates': 0} for name in camera_ids}
            self.hub = InputHub({self.config['cameras'][name]['source_id']: self.config['cameras'][name]['rtsp_url']
                                 for name in camera_ids})
            self.hub.start()
            self.threads = [threading.Thread(target=fn, name=name, daemon=True) for name, fn in (
                ('joyai-evidence-sampler', self.sample), ('joyai-fair-observer', self.observe),
                ('joyai-clip-collector', self.collect_pending),
                ('joyai-review-delivery', self.deliver))]
            for thread in self.threads:
                thread.start()
        return self.status()

    def stop(self):
        self.stop_event.set()
        if self.hub:
            self.hub.stop()
        # Requests have bounded timeouts; never claim stopped while one still runs.
        for thread in self.threads:
            thread.join(timeout=2)
        if not any(t.is_alive() for t in self.threads):
            for observer in self.observers.values():
                observer.close()
            self.retire_idle(stopping=True)
            self.release_reviewer()
        return self.status()

    def pending(self):
        return [job for job in self.ledger.all('job') if job['state'] not in ('published', 'incomplete', 'blocked')
                or (job.get('review_task_id') and not job.get('task_ended') and job['state'] in ('incomplete', 'blocked'))]

    def restart_review(self, report_id):
        with self.lock:
            if self.stop_event.is_set() or not any(t.is_alive() for t in self.threads):
                raise ValueError('异常监控未启动，请先启动监控工具')
            original = next((job for job in self.ledger.all('job') if job.get('report_id') == report_id), None)
            if not original or original['state'] != 'published':
                raise ValueError('找不到已完成复核的原事件')
            root_id = original.get('root_candidate_id', original['id'])
            if any(job.get('root_candidate_id') == root_id for job in self.pending()):
                return self.status()
            if len(self.pending()) >= 8:
                raise ValueError('复核队列已满，请稍后重试')
            # The public read also checks expiry and access before reading local evidence.
            self.publisher.client.get('/reports/' + report_id)
            path = (Path(self.config['storage_root']) / original['storage_key']).resolve()
            if not path.is_relative_to(Path(self.config['storage_root']).resolve()) or not path.is_file():
                raise ValueError('原视频片段不存在或已过期')
            job = {k: original[k] for k in ('camera_id', 'source_id', 'unit_id', 'trigger_at', 'event_type',
                   'observation', 'joy_verdict', 'start', 'end', 'storage_key', 'asset_id',
                   'thumbnail_asset_id', 'evidence', 'event_id')}
            job.update(id=str(uuid.uuid4()), kind='job', state='awaiting_review', manual_review=True,
                       root_candidate_id=root_id, previous_report_id=report_id, frames=review_frames(path),
                       joy_clip_reviewed=True, processed_at=time.time())
            self.ledger.save(job['id'], 'job', job)
            return self.status()

    def status(self):
        with self.lock:
            running = any(t.is_alive() for t in self.threads)
            jobs = self.pending()
            latest_reviews = {}
            for job in self.ledger.all('job'):
                if job.get('manual_review'):
                    latest_reviews[job['root_candidate_id']] = job
            failed_reviews = [job for job in latest_reviews.values()
                              if job['state'] in ('blocked', 'incomplete') and job['id'] not in {j['id'] for j in jobs}
                              and time.time() - job['end'] < 7 * 86400]
            cameras = {name: {k: v for k, v in state.items() if k != 'cooldowns'} for name, state in self.cameras.items()}
            return {'status': 'stopping' if running and self.stop_event.is_set() else 'running' if running else 'stopped',
                'model_instances': 1, 'camera_contexts': len(cameras), 'cameras': cameras,
                'observer_precision': 'INT4', 'reviewer': self.review.status(),
                'pending_reviews': len(jobs), 'last_error': self.last_error,
                'pending_events': [dict(
                    {k: job.get(k) for k in ('id', 'camera_id', 'source_id', 'event_type', 'state', 'error',
                                             'event_id', 'report_id', 'thumbnail_asset_id', 'root_candidate_id',
                                             'previous_report_id', 'manual_review')},
                    camera_name=self.config['cameras'][job['camera_id']]['name'],
                    location=self.config['cameras'][job['camera_id']].get('location', ''),
                    occurred_at=iso(job['trigger_at']), video_asset_id=job.get('asset_id'),
                    clip_seconds=self.config['clip_seconds'], observation=job.get('observation', ''))
                    for job in jobs + failed_reviews],
                'recent_work': [{k: job.get(k) for k in ['id', 'camera_id', 'event_type', 'state', 'error']}
                                for job in self.ledger.all('job')[-8:]],
                'alarm_rule': 'JoyAI 与 Qwen 均确认同类异常，且视频、成果及报告完成公共登记'}

    def sample(self):
        seen = {}
        while not self.stop_event.is_set():
            for name in self.cameras:
                frame = self.hub.latest(self.config['cameras'][name]['source_id'])
                if frame is None or seen.get(name) == frame.reference.frame_id:
                    continue
                seen[name] = frame.reference.frame_id
                try:
                    image = frame.frame
                    stamp = frame.frame_ts_ms / 1000
                    with self.lock:
                        state = self.cameras[name]
                        if state['session_id'] != frame.reference.stream_session_id:
                            self.buffers[name].clear()
                            state.update(session_id=frame.reference.stream_session_id, state='warming_up')
                        self.buffers[name].add(image, stamp)
                        state['last_frame_at'] = stamp
                except Exception:
                    self.fail(name, '视频取帧失败，未确认异常')
            self.stop_event.wait(1 / self.config['sample_fps'])

    def fail(self, camera, message):
        with self.lock:
            self.last_error = message
            if camera in self.cameras:
                changed = self.cameras[camera]['last_error'] != message
                self.cameras[camera].update(last_error=message, state='degraded')
            else:
                changed = True
        if changed:
            log.warning('%s: %s', camera, message)

    def observe(self):
        previous_session = {}
        while not self.stop_event.is_set():
            for name, observer in self.observers.items():
                if self.stop_event.is_set():
                    break
                frame = self.hub.latest(self.config['cameras'][name]['source_id'])
                if frame is None or time.time() - frame.frame_ts_ms / 1000 > 5:
                    self.fail(name, '摄像头输入未就绪或已中断')
                    continue
                stamp = frame.frame_ts_ms / 1000
                with self.lock:
                    last = self.cameras[name]['last_observed_at']
                if last is not None and stamp - last < self.config['observe_interval']:
                    continue
                try:
                    unit = self.publisher.unit(name, frame)
                    with self.inference_lock:
                        if previous_session.get(name) != unit['id']:
                            observer.reset()
                            previous_session[name] = unit['id']
                        result, _ = observer.analyze(frame.frame, stamp)
                    with self.lock:
                        self.cameras[name].update(state='observing', last_observed_at=stamp, last_error=None)
                        self.cameras[name]['observations'] += 1
                        if all(c['last_error'] is None for c in self.cameras.values()):
                            self.last_error = None
                    for candidate in result['candidates']:
                        self.candidate(name, unit, stamp, candidate, result['joyMessage'])
                except Exception as exc:
                    self.fail(name, str(exc)[:300] if isinstance(exc, (RuntimeError, ValueError)) else type(exc).__name__)
            self.stop_event.wait(.1)

    def candidate(self, name, unit, stamp, candidate, observation):
        with self.lock:
            cooldowns = self.cameras[name]['cooldowns']
            key = unit['id'] + ':' + candidate['kind']
            if stamp - cooldowns.get(key, -float('inf')) < self.config['cooldown_seconds']:
                return
            if len(self.pending()) >= 8:
                self.cameras[name]['skipped_candidates'] += 1
                self.fail(name, '复核队列已满，本次候选未进入确认流程')
                return
            cooldowns[key] = stamp
            job = {'id': str(uuid.uuid4()), 'kind': 'job', 'state': 'collecting', 'camera_id': name,
                   'source_id': unit['source_id'], 'unit_id': unit['id'], 'trigger_at': stamp,
                   'event_type': candidate['kind'], 'observation': observation,
                   'joy_verdict': candidate.get('verdict'), 'processed_at': time.time(),
                   'start': stamp - self.config['pre_seconds'],
                   'end': stamp + self.config['clip_seconds'] - self.config['pre_seconds']}
            self.ledger.save(job['id'], 'job', job)

    def collect(self, job):
        if time.time() < job['end'] + .25:
            return False
        with self.lock:
            camera = self.cameras.get(job['camera_id'])
            if camera is None or camera['session_id'] != job['unit_id']:
                raise ValueError('摄像头会话已变化，无法补造原会话的视频证据')
            samples = self.buffers[job['camera_id']].between(job['start'], job['end'])
        # The complete raw frame is the ROI; painted detection overlays are never model inputs.
        import cv2
        import numpy as np
        first = cv2.imdecode(np.frombuffer(samples[0][1], np.uint8), cv2.IMREAD_COLOR) if samples else None
        if first is None:
            raise ValueError('没有可用视频证据')
        height, width = first.shape[:2]
        video, frames, evidence = build_evidence(samples, [0, 0, width, height], first.shape,
                                                duration=self.config['clip_seconds'])
        job.update(start=samples[0][0], end=samples[0][0] + evidence['duration'], frames=frames, evidence=evidence)
        evidence.update(preTriggerSeconds=round(job['trigger_at'] - job['start'], 3),
                        postTriggerSeconds=round(job['end'] - job['trigger_at'], 3), delegation=job['observation'])
        key = f"algorithm-output/joyai/{self.config['instance_id']}/{job['id']}.mp4"
        path = Path(self.config['storage_root']) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.mp4.tmp')
        with temporary.open('wb') as handle:
            handle.write(video)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        thumbnail = path.with_suffix('.jpg')
        thumbnail.write_bytes(samples[len(samples) // 2][1])
        job.update(storage_key=key, state='awaiting_review', error=None)
        self.ledger.save(job['id'], 'job', job)
        return True

    def collect_pending(self):
        while not self.stop_event.is_set():
            for job in self.pending():
                if job['state'] != 'collecting':
                    continue
                try:
                    self.collect(job)
                except (ValueError, RuntimeError, OSError) as exc:
                    job.update(state='incomplete', error=str(exc)[:300])
                    self.ledger.save(job['id'], 'job', job)
                    self.fail(job['camera_id'], job['error'])
            self.stop_event.wait(.25)

    def deliver(self):
        try:
            self.deliver_pending()
        finally:
            self.release_reviewer()

    def deliver_pending(self):
        while not self.stop_event.is_set():
            for job in self.pending():
                if self.stop_event.is_set():
                    break
                if job.get('retry_at', 0) > time.time():
                    continue
                if job['state'] == 'collecting':
                    continue
                if job['state'] in ('incomplete', 'blocked'):
                    try:
                        self.publisher.finish_review(job, job.get('error_code', 'REVIEW_INVALID_EVIDENCE'))
                    except Exception:
                        job['retry_at'] = time.time() + 30
                        self.ledger.save(job['id'], 'job', job)
                    continue
                try:
                    if job.get('manual_review'):
                        self.publisher.prepare_review(job)
                    else:
                        self.publisher.asset(job)
                    initial = job.setdefault('initial_joy_verdict', job.get('joy_verdict') or {
                        'decision': 'uncertain', 'reason': job['observation'], 'confidence': None})
                    self.publisher.assessment(job, 'joyai_initial', initial)
                    if not job.get('joy_clip_reviewed') and (not job.get('joy_verdict') or job['joy_verdict']['decision'] != 'confirmed'):
                        # Native JoyAI may delegate prose. Obtain its own structured clip
                        # verdict before testing agreement; a Qwen verdict cannot replace it.
                        with self.inference_lock:
                            job['joy_verdict'] = self.joy_review.review(job['event_type'], job['frames'], job['evidence'])
                        job['joy_clip_reviewed'] = True
                        self.ledger.save(job['id'], 'job', job)
                    if not job.get('review_verdict'):
                        job.update(state='reviewing', error=None)
                        self.ledger.save(job['id'], 'job', job)
                        job['review_verdict'] = self.review.review(job['event_type'], job['frames'], job['evidence'])
                        job.update(state='registering', processed_at=time.time())
                        self.ledger.save(job['id'], 'job', job)
                    self.publisher.publish(job)
                    job.pop('frames', None)
                    self.ledger.save(job['id'], 'job', job)
                except ReviewFailure as exc:
                    # A manual execution has a definite failure; retry is a new explicit review.
                    job.update(state='blocked' if job.get('manual_review') else 'awaiting_review',
                               error=str(exc), error_code=exc.code, retry_at=time.time() + 30)
                    self.ledger.save(job['id'], 'job', job)
                    self.fail(job['camera_id'], job['error'])
                except ValueError as exc:
                    job.update(state='incomplete' if job['state'] == 'collecting' else 'blocked', error=str(exc)[:300])
                    self.ledger.save(job['id'], 'job', job)
                    self.fail(job['camera_id'], job['error'])
                except Exception as exc:
                    job.update(state='awaiting_review' if not job.get('review_verdict') else 'registering',
                               error='等待模型复核或公共登记：' + str(exc)[:250], retry_at=time.time() + 30)
                    self.ledger.save(job['id'], 'job', job)
                    self.fail(job['camera_id'], job['error'])
            self.retire_idle()
            if not any(job['state'] != 'collecting' and not job.get('review_verdict')
                       and job.get('retry_at', 0) <= time.time() for job in self.pending()):
                self.release_reviewer()
            self.stop_event.wait(.5)

    def release_reviewer(self):
        try:
            self.review.release()
        except Exception:
            self.last_error = '复核模型显存尚未释放，将重试停止本目录复核服务'

    def retire_idle(self, stopping=False):
        active = {camera['session_id'] for camera in self.cameras.values()} if not stopping else set()
        pending = {job['unit_id'] for job in self.pending()}
        for unit in self.ledger.all('unit'):
            if unit.get('retired') or unit['id'] in active or unit['id'] in pending or unit.get('cleanup_retry_at', 0) > time.time():
                continue
            # Allow an old in-flight observation to finish before completing its task.
            if not stopping:
                idle = unit.setdefault('idle_since', time.time())
                self.ledger.save(unit['id'], 'unit', unit)
                if time.time() - idle < 120:
                    continue
            try:
                self.publisher.retire(unit)
            except Exception:
                unit['cleanup_retry_at'] = time.time() + 30
                self.ledger.save(unit['id'], 'unit', unit)
                self.last_error = '公共任务收尾尚未完成，将在下次运行时重试'
