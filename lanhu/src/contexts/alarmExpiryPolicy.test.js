import assert from 'node:assert/strict';
import test from 'node:test';

import {
  DEFAULT_ALARM_RETENTION_MS,
  isAlarmFresh,
  pruneExpiredAlarms,
  resolveAlarmTiming,
} from './alarmExpiryPolicy.js';

test('prefers backend expires_at', () => {
  const now = Date.now();
  const timing = resolveAlarmTiming({
    timestamp: now - 1000,
    expires_at: now + 5000,
  }, { now });

  assert.equal(timing.expiresAt, now + 5000);
  assert.equal(isAlarmFresh({ timestamp: now, expires_at: now }, { now }), false);
});

test('falls back to the default seven-day retention', () => {
  const now = Date.now();
  const occurredAt = now - 60_000;
  const timing = resolveAlarmTiming({ timestamp: occurredAt }, { now });

  assert.equal(timing.expiresAt, occurredAt + DEFAULT_ALARM_RETENTION_MS);
  assert.equal(isAlarmFresh({
    timestamp: now - DEFAULT_ALARM_RETENTION_MS - 1,
  }, { now }), false);
});

test('rejects malformed historical timestamps but accepts live fallback', () => {
  const now = Date.now();
  assert.equal(isAlarmFresh({ timestamp: 'not-a-time' }, { now }), false);

  const timing = resolveAlarmTiming(
    { timestamp: '' },
    { now, allowReceivedAtFallback: true },
  );
  assert.equal(timing.occurredAt, now);
});

test('prunes cards as soon as their expiry boundary is reached', () => {
  const now = Date.now();
  const alarms = [
    { id: 'fresh', expiresAt: now + 1 },
    { id: 'expired', expiresAt: now },
  ];

  assert.deepEqual(pruneExpiredAlarms(alarms, now).map(({ id }) => id), ['fresh']);
});
