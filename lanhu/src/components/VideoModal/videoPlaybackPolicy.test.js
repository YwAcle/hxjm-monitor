import test from 'node:test';
import assert from 'node:assert/strict';

import {
  canRetryPlayback,
  classifyPlaybackPreflightResponse,
  getPendingRecordingRetryDelay
} from './videoPlaybackPolicy.js';

test('404 is terminal and must not be retried', () => {
  assert.equal(classifyPlaybackPreflightResponse(404, false), 'missing');
});

test('5xx responses are retryable', () => {
  assert.equal(classifyPlaybackPreflightResponse(500, false), 'retryable');
  assert.equal(classifyPlaybackPreflightResponse(503, false), 'retryable');
});

test('successful preflight responses proceed to video loading', () => {
  assert.equal(classifyPlaybackPreflightResponse(200, true), 'playable');
  assert.equal(classifyPlaybackPreflightResponse(206, true), 'playable');
});

test('other 4xx responses are terminal', () => {
  assert.equal(classifyPlaybackPreflightResponse(401, false), 'unavailable');
  assert.equal(classifyPlaybackPreflightResponse(403, false), 'unavailable');
});

test('automatic retries stop after two attempts', () => {
  assert.equal(canRetryPlayback(0), true);
  assert.equal(canRetryPlayback(1), true);
  assert.equal(canRetryPlayback(2), false);
});

test('a recording that is still being finalized is retried', () => {
  const url = 'http://media.example:9996/get?path=live%2Fcamera_4&start=2026-08-09T20%3A49%3A06.516000%2B08%3A00&duration=30.232';
  const now = Date.parse('2026-08-09T20:49:26.000+08:00');

  assert.equal(getPendingRecordingRetryDelay(url, now), 2000);
});

test('an old missing recording is not retried as a pending segment', () => {
  const url = 'http://media.example:9996/get?path=live%2Fcamera_4&start=2026-08-09T20%3A49%3A06.516000%2B08%3A00&duration=30.232';
  const now = Date.parse('2026-08-09T20:50:00.000+08:00');

  assert.equal(getPendingRecordingRetryDelay(url, now), null);
});
