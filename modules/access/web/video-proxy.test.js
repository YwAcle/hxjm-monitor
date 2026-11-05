import assert from 'node:assert/strict';
import test from 'node:test';
import { videoProxies } from './video-proxy.js';
import { videoAnalysisEnabled, videoMediaBase, detectionSocketPath, synchronizedAnalysisAllowed } from './src/config/videoDeployment.js';

test('shared algorithm uses its origin while each worktree serves video from local MediaMTX', () => {
  const env = { VITE_VIDEO_ANALYSIS_ORIGIN: 'http://127.0.0.1:28012', VITE_MEDIA_PORT: '19089' };
  const page = { protocol: 'http:', hostname: '100.127.237.7' };
  assert.equal(videoProxies(env)['/ws/detections'].target, 'http://127.0.0.1:28010');
  assert.equal(videoProxies(env)['/shared-media'].target, 'http://127.0.0.1:19089');
  assert.equal(videoMediaBase(env, page), '/shared-media/live');
  assert.equal(videoAnalysisEnabled({ VITE_VIDEO_ANALYSIS_MODE: 'shared', VITE_VIDEO_ANALYSIS_ENABLED: 'false' }), true);
  assert.equal(videoAnalysisEnabled({ VITE_VIDEO_ANALYSIS_MODE: 'local', VITE_VIDEO_ANALYSIS_ENABLED: 'false' }), false);
  assert.equal(videoProxies({ ...env, VIDEO_ANALYSIS_SHARED_ORIGIN: 'http://127.0.0.1:29999' })['/ws/detections'].target,
    'http://127.0.0.1:29999');
  env.VITE_VIDEO_ANALYSIS_MODE = 'local';
  assert.equal(videoProxies(env)['/ws/detections'].target, env.VITE_VIDEO_ANALYSIS_ORIGIN);
  assert.equal(videoMediaBase(env, page), 'http://100.127.237.7:19089/live');
  assert.equal(detectionSocketPath(), '/ws/detections');
  assert.equal(detectionSocketPath(true), '/ws/detections?frames=1');
});

test('shared media proxy keeps WHEP Location and session methods on its public prefix', () => {
  const proxy = videoProxies({ SHARED_MEDIA_ORIGIN: 'http://127.0.0.1:18889' })['/shared-media'];
  let response;
  proxy.configure({ on(event, callback) { assert.equal(event, 'proxyRes'); response = callback; } });
  const request = '/shared-media/live/camera_1/whep';
  assert.equal(proxy.rewrite(request), '/live/camera_1/whep');
  for (const location of ['/live/camera_1/whep/id', 'whep/id',
    'http://127.0.0.1:18889/live/camera_1/whep/id']) {
    const upstream = { headers: { location } };
    response(upstream, { url: request });
    assert.equal(upstream.headers.location, '/shared-media/live/camera_1/whep/id');
    assert.equal(proxy.rewrite(upstream.headers.location), '/live/camera_1/whep/id');
  }
  const upstream = { headers: { location: '/live/camera_1/whep/id?token=one' } };
  response(upstream, { url: '/live/camera_1/whep' });
  assert.equal(upstream.headers.location, '/shared-media/live/camera_1/whep/id?token=one');
  response({ headers: {} }, { url: request });
});

test('subscriber shares only detections and ignores an inherited primary media origin', () => {
  const env = { VITE_VIDEO_ANALYSIS_MODE: 'shared', VITE_VIDEO_ANALYSIS_SUBSCRIBER: 'true',
    VITE_MEDIA_PORT: '19089', SHARED_MEDIA_ORIGIN: 'http://main.invalid:18889',
    VIDEO_ANALYSIS_SHARED_ORIGIN: 'http://127.0.0.1:28010' };
  assert.equal(videoProxies(env)['/ws/detections'].target, 'http://127.0.0.1:28010');
  assert.equal(videoProxies(env)['/shared-media'].target, 'http://127.0.0.1:19089');
  assert.equal(synchronizedAnalysisAllowed(env), false);
  assert.equal(synchronizedAnalysisAllowed({}), true);
});
