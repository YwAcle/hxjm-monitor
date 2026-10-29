import assert from 'node:assert/strict';
import test from 'node:test';
import { ServerClock, MediaTimeline, FrameAnnotations, nearestResult, FrameBuffer, BUFFER_MAX, BUFFER_BYTES_MAX } from './videoAlignment.js';
import { DetectionChannel } from './detectionChannel.js';

test('RTT mapping handles browser/server skew and expires stale clock samples', () => {
  const clock = new ServerClock();
  assert.equal(clock.accept({ client_ms: 100, server_ms: 1000105 }, 110), true);
  assert.equal(clock.toLocal(1000200, 150), 200);
  assert.equal(clock.accept({ client_ms: 200, server_ms: 99999999 }, 300), true);
  assert.equal(clock.toLocal(1000200, 300), 200); // slower sample ignored
  assert.equal(clock.toLocal(1000200, 21000), null);
});

test('matching rejects future/old/expired results and honors zero target frames', () => {
  const hist = [0, 200, 400].map((t, i) => ({ frameAt: t, expiresAt: 3000,
    message: { frame_id: i + 1, detections: t === 400 ? [] : ['person'] } }));
  assert.equal(nearestResult(hist, 290, 1000).frameAt, 200);
  assert.deepEqual(nearestResult(hist, 400, 1000).message.detections, []);
  assert.equal(nearestResult(hist, -200, 1000), null);
  assert.equal(nearestResult(hist, 400, 3000), null);
  assert.equal(nearestResult(hist, 1700, 2000), null);
});

test('one-second detections cover the timeline without periodic blank intervals', () => {
  const history = Array.from({ length: 10 }, (_, i) => ({ frameAt: i * 1000,
    expiresAt: i * 1000 + 3000, message: { frame_id: i + 1, detections: i === 4 ? [] : ['person'] } }));
  for (let t = 1000; t < 8000; t += 10) {
    // Simulate results already delivered by a 650 ms delayed video presentation.
    const available = history.filter(p => p.frameAt + 100 <= t + 650);
    assert.ok(nearestResult(available, t, t + 650), `blank at ${t} ms`);
  }
  assert.deepEqual(nearestResult(history, 4000, 4650).message.detections, []);
  const stopped = history.slice(0, 3);
  assert.equal(nearestResult(stopped, 3300, 3950), null);
  assert.equal(nearestResult(stopped, 2000, 5000), null);
});

test('media arrival mapping absorbs small jitter and resets accumulated drift', () => {
  const clock = new MediaTimeline();
  assert.equal(clock.map(0, 10000), 10000);
  assert.equal(clock.map(100, 10400), 10100);
  assert.equal(clock.map(200, 10250), 10200);
  assert.equal(clock.map(300, 13000), 13000);
  assert.equal(clock.map(400, 13100), 13100);
  assert.equal(clock.map(400, 15000), 15000);
  assert.equal(clock.map(500, 15100), 15100);
  assert.equal(clock.map(NaN, 16000), null);
  assert.equal(clock.map(600, 16100), 16100);
  clock.reset();
  for (let i = 0; i < 100; i++) {
    const arrival = 20000 + i * 200;
    const at = clock.map(i * 100, arrival);
    assert.ok(at <= arrival && arrival - at <= 500);
  }
});

test('frame count, time and bytes stay bounded and every bitmap is released', () => {
  let opened = 0; let closed = 0;
  const buffer = new FrameBuffer();
  for (let i = 0; i < 300; i++) {
    opened++;
    buffer.push({ at: i * 20, bitmap: { width: 1920, height: 1080, close() { closed++; } } });
    assert.ok(buffer.frames.length <= BUFFER_MAX);
    assert.ok(buffer.bytes <= BUFFER_BYTES_MAX);
  }
  const f = buffer.take(6500, 100000); // clamp requested delay to the hard ceiling
  f?.bitmap.close();
  buffer.clear();
  assert.equal(opened, closed);
});

test('a frozen image keeps its own annotation; advancing frames obey expiry and zero targets', () => {
  const snapshot = new FrameAnnotations();
  const positive = { expiresAt: 1000, message: { detections: ['person'] } };
  const zero = { expiresAt: 5000, message: { detections: [] } };
  assert.deepEqual(snapshot.select(1, positive, 100), { packet: positive, frozen: false });
  // New AI output and channel expiry cannot change the annotation of this image.
  assert.deepEqual(snapshot.select(1, zero, 1100), { packet: positive, frozen: true });
  assert.equal(snapshot.select(1, null, 4000).packet, positive);
  assert.equal(snapshot.select(2, positive, 4000).packet, null);
  assert.equal(snapshot.select(3, zero, 4100).packet, zero);
  snapshot.reset();
  assert.equal(snapshot.select(3, null, 4200).packet, null);
});

test('bounded history, factual state precedence and channel recovery', () => {
  const c = new DetectionChannel('camera_1');
  const s = { camera_id: 'camera_1', task: 'deepsort', service_session_id: 's', stream_session_id: 'v',
    session_generation: 0, stream_epoch: 1, type: 'status', component: 'service', state: 'ready',
    components: { capture: { state: 'streaming' }, analyzer: { state: 'ready' } } };
  for (const [capture, analyzer, label] of [['connecting','loading_model','等待视频源'],
    ['reconnecting','model_error','取帧重连'], ['streaming','loading_model','模型加载中'],
    ['streaming','inference_error','推理异常']]) {
    c.accept({ ...s, components: { capture: { state: capture }, analyzer: { state: analyzer } } }, 0);
    assert.equal(c.aiStatus, label);
  }
  c.accept(s, 0);
  for (let i = 1; i <= 200; i++) c.accept({ ...s, type: 'detections', frame_id: i,
    frame_ts_ms: i, sent_at_ms: i + 100, valid_for_ms: 2000, detections: [] }, 200 + i);
  assert.equal(c.historyRef.current.length, 64);
  c.expire(10000);
  assert.equal(c.historyRef.current.length, 0);
  assert.equal(c.aiStatus, '分析延迟');
});

test('future results cannot advance the ordering baseline; expiry stays visible on heartbeat', () => {
  const clock = new ServerClock(); clock.accept({client_ms: 0, server_ms: 100000}, 0);
  const c = new DetectionChannel('camera_1');
  const s = {type:'status',camera_id:'camera_1',task:'deepsort',service_session_id:'s',stream_session_id:'v',
    session_generation:0,stream_epoch:1,state:'ready',components:{capture:{state:'streaming'},analyzer:{state:'ready'}}};
  c.accept(s, 0);
  const p = {...s,type:'detections',frame_id:999,frame_ts_ms:101000,sent_at_ms:101001,valid_for_ms:2000,detections:[]};
  assert.equal(c.accept(p, 100, clock), false);
  assert.equal(c.accept({...p,frame_id:1,frame_ts_ms:100050,sent_at_ms:100060},100,clock), true);
  c.expire(5000);c.accept(s,5000);
  assert.equal(c.aiStatus,'分析延迟');
});
