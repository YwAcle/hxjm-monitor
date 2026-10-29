export const PRIMARY_CONNECT_TIMEOUT = 3000; // 主连接超时：3 秒
export const FRAME_STALE_TIMEOUT = 3000; // 画面卡死判定：3 秒没新帧
export const ALGORITHM_PROBE_INTERVAL = 5000; // 算法流探活间隔：5 秒

export function buildWhepUrl(url) {
  if (!url) return '';
  return `${url.replace(/\/+$/, '')}/whep`;
}

export function whepSessionUrl(location, requestUrl, pageUrl) {
  if (!location) throw new Error('WHEP response is missing its session Location');
  const request = new URL(requestUrl, pageUrl);
  const session = new URL(location, request);
  if (session.origin !== request.origin) throw new Error('WHEP session changed origin');
  return session.href;
}

export function releaseWhepSession(connection, send = fetch) {
  if (!connection?.sessionUrl) return;
  const url = connection.sessionUrl;
  connection.sessionUrl = null;
  // Use a fresh request: the connection's AbortController has already been cancelled.
  return send(url, { method: 'DELETE', keepalive: true }).catch(() => {});
}
