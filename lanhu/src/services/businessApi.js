const BASE = '/api/v1/business';

export class BusinessApiError extends Error {
  constructor(message, status, code, traceId) {
    super(message);
    this.name = 'BusinessApiError';
    this.status = status;
    this.code = code;
    this.traceId = traceId;
  }
}

export function createBusinessApi({ fetchImpl = (...args) => fetch(...args) } = {}) {
  async function request(path, body, { method = 'POST', signal } = {}) {
    const multipart = typeof FormData !== 'undefined' && body instanceof FormData;
    const response = await fetchImpl(path, {
      method, signal, cache: 'no-store', credentials: 'omit',
      headers: {
        Accept: 'application/json',
        ...(body === undefined || multipart ? {} : { 'Content-Type': 'application/json' }),
      },
      ...(body === undefined ? {} : { body: multipart ? body : JSON.stringify(body) }),
    });
    let data;
    try { data = await response.json(); }
    catch { throw new BusinessApiError('服务返回的数据格式不正确', response.status, 'INVALID_RESPONSE'); }
    if (!response.ok || data?.error || (data?.code != null && data.code !== 200)) {
      const status = data?.code === 401 ? 401 : response.status;
      throw new BusinessApiError(data?.error?.message || data?.msg || `请求失败（${status}）`,
        status, data?.error?.code, data?.trace_id);
    }
    return data;
  }
  return {
    async sources(signal) {
      const items = [], cursors = new Set();
      let cursor;
      do {
        const data = await request(`${BASE}/sources?page_size=200${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`,
          undefined, { method: 'GET', signal });
        if (!Array.isArray(data.items)) throw new BusinessApiError('视频来源响应格式不正确', 502, 'INVALID_RESPONSE');
        items.push(...data.items);
        if (!data.has_more) return { ...data, items };
        if (typeof data.next_cursor !== 'string' || !data.next_cursor || cursors.has(data.next_cursor)) {
          throw new BusinessApiError('视频来源分页游标无效', 502, 'INVALID_RESPONSE');
        }
        cursor = data.next_cursor;
        cursors.add(cursor);
      } while (true);
    },
    results: (body, signal) => request(`${BASE}/results/query`, body, { signal }),
    assets: (body, signal) => request(`${BASE}/assets/query`, body, { signal }),
    resolve: (body, signal) => request(`${BASE}/media/resolve`, body, { signal }),
    uploadImage(file, fields, signal) {
      const body = new FormData();
      body.append('file', file);
      Object.entries(fields).forEach(([name, value]) => { if (value != null) body.append(name, value); });
      return request(`${BASE}/assets/upload`, body, { signal });
    },
    registerIdentity: (body, signal) => request(`${BASE}/identities/register`, body, { signal }),
    identities: (body, signal) => request(`${BASE}/identities/query`, body, { signal }),
    identity: (id, signal) => request(`${BASE}/identities/${encodeURIComponent(id)}`, undefined, { method: 'GET', signal }),
    createQuery: (body, signal) => request(`${BASE}/queries`, body, { signal }),
    query: (id, signal) => request(`${BASE}/queries/${encodeURIComponent(id)}`, undefined, { method: 'GET', signal }),
    selectCandidate: (body, signal) => request(`${BASE}/queries/select`, body, { signal }),
    tracklets: (body, signal) => request(`${BASE}/tracklets/query`, body, { signal }),
    events: (body, signal) => request(`${BASE}/events/query`, body, { signal }),
    searchReports: (body, signal) => request(`${BASE}/reports/search`, body, { signal }),
    activities: (body, signal) => request(`${BASE}/activities/query`, body, { signal }),
    reports: (body, signal) => request(`${BASE}/reports/query`, body, { signal }),
    async playbackTicket(assetId, signal) {
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(assetId)) {
        throw new BusinessApiError('录像资产标识无效', 400, 'INVALID_ARGUMENT');
      }
      const ticket = await request(`${BASE}/assets/${assetId}/playback-ticket`, {}, { signal });
      if (typeof ticket?.url !== 'string'
          || !Number.isFinite(Date.parse(ticket.expires_at))) {
        throw new BusinessApiError('录像访问响应格式不正确', 502, 'INVALID_RESPONSE');
      }
      const location = typeof window === 'undefined' ? 'http://localhost/' : window.location.href;
      const url = new URL(ticket.url, location);
      if (url.origin !== new URL(location).origin || !['http:', 'https:'].includes(url.protocol)
          || url.username || url.password || Date.parse(ticket.expires_at) <= Date.now()) {
        throw new BusinessApiError('录像访问链接无效或已到期', 502, 'INVALID_RESPONSE');
      }
      return ticket;
    },
  };
}

export const businessApi = createBusinessApi();
