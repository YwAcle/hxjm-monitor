export const DEFAULT_ALARM_RETENTION_MS = 168 * 60 * 60 * 1000; //默认保留时间为7天

// 解析时间戳
export function parseAlarmTime(value) {
  // 如果是数字(毫秒时间戳) 直接返回
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  // 如果是空值 返回null
  if (typeof value !== 'string' || !value.trim()) return null;

  const text = value.trim();
  // 标准格式字符串 "2026-08-14 10:30:00"
  const localMatch = text.match(
    /^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})$/,
  );
  if (localMatch) {
    const [, year, month, day, hour, minute, second] = localMatch.map(Number);
    const date = new Date(year, month - 1, day, hour, minute, second);
    if (
      date.getFullYear() === year
      && date.getMonth() === month - 1
      && date.getDate() === day
      && date.getHours() === hour
      && date.getMinutes() === minute
      && date.getSeconds() === second
    ) {
      return date.getTime();
    }
    return null;
  }

  // 其他格式，交给浏览器兜底解析
  const parsed = Date.parse(text);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseExpiry(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

export function resolveAlarmTiming(
  alarm,
  { now = Date.now(), allowReceivedAtFallback = false } = {},
) {

  /*
  计算告警信息的发生时间
  */

  // 对告警信息的时间戳进行解析
  let occurredAt = parseAlarmTime(alarm?.timestamp);
  // 如果第一步没解析出发生时间（null），但调用方传了 allowReceivedAtFallback: true，就用"收到这条消息的时刻" now 当发生时间
  if (occurredAt == null && allowReceivedAtFallback) occurredAt = now;
  // 如果连兜底都不允许，直接 return null，表示"这条告警无法确定时间，整体丢弃"
  if (occurredAt == null) return null;

  /*
  计算告警信息的过期时间
  */
  //如果后端明确给了过期时间（expires_at 或 expiresAt 字段），就显示返回expiresAt: explicitExpiry
  //否则就使用发生时间 + 7天
  const explicitExpiry = parseExpiry(alarm?.expires_at ?? alarm?.expiresAt);
  return {
    occurredAt,
    expiresAt: explicitExpiry ?? occurredAt + DEFAULT_ALARM_RETENTION_MS,
  };
}

export function isAlarmFresh(alarm, options) {
  const timing = resolveAlarmTiming(alarm, options);
  return timing != null && timing.expiresAt > (options?.now ?? Date.now());
}

export function pruneExpiredAlarms(alarms, now = Date.now()) {
  return (alarms || []).filter((alarm) => {
    const expiresAt = parseExpiry(alarm?.expiresAt ?? alarm?.expires_at);
    if (expiresAt != null) return expiresAt > now;
    return isAlarmFresh(alarm, { now });
  });
}
