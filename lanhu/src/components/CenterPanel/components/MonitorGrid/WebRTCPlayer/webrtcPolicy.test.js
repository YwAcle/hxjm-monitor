import test from 'node:test';
import assert from 'node:assert/strict';

import {
  ALGORITHM_PROBE_INTERVAL,
  FRAME_STALE_TIMEOUT,
  PRIMARY_CONNECT_TIMEOUT,
  buildWhepUrl,
  whepSessionUrl,
  releaseWhepSession,
} from './webrtcPolicy.js';

test('buildWhepUrl normalizes trailing slashes', () => {
  assert.equal(
    buildWhepUrl('http://127.0.0.1:8889/live/camera_1_boxmot/'),
    'http://127.0.0.1:8889/live/camera_1_boxmot/whep',
  );
  assert.equal(
    buildWhepUrl('http://127.0.0.1:8889/live/camera_1'),
    'http://127.0.0.1:8889/live/camera_1/whep',
  );
});

test('fallback and stale-frame thresholds match monitoring policy', () => {
  assert.equal(PRIMARY_CONNECT_TIMEOUT, 3000);
  assert.equal(FRAME_STALE_TIMEOUT, 3000);
  assert.equal(ALGORITHM_PROBE_INTERVAL, 5000);
});

test('WHEP session cleanup resolves proxied, absolute and relative Locations', async () => {
  const page = 'http://100.127.237.7:3002/';
  const request = '/shared-media/live/camera_1/whep';
  assert.equal(whepSessionUrl('/shared-media/live/camera_1/whep/one', request, page),
    'http://100.127.237.7:3002/shared-media/live/camera_1/whep/one');
  assert.equal(whepSessionUrl('whep/two', request, page),
    'http://100.127.237.7:3002/shared-media/live/camera_1/whep/two');
  assert.equal(whepSessionUrl('http://127.0.0.1:18889/live/camera_1/whep/three',
    'http://127.0.0.1:18889/live/camera_1/whep', page),
  'http://127.0.0.1:18889/live/camera_1/whep/three');
  assert.throws(() => whepSessionUrl(null, request, page), /missing/);
  assert.throws(() => whepSessionUrl('http://other-host/session', request, page), /origin/);
  const calls = [];
  const connection = { closed: true, sessionUrl: whepSessionUrl('whep/late', request, page) };
  const send = async (...args) => { calls.push(args); throw new Error('already gone'); };
  await releaseWhepSession(connection, send);
  await releaseWhepSession(connection, send);
  assert.equal(calls.length, 1, 'even an aborted connection releases a late session once');
  assert.equal(calls[0][1].method, 'DELETE');
  assert.equal(calls[0][1].keepalive, true);
  assert.equal(calls[0][1].signal, undefined);
});
