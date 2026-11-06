export function getPedestrianSearchResult(payload) {
  for (const result of [payload?.data, payload]) {
    if (['pedestrian_search', 'pedestrian_selection'].includes(result?.type)) return result;
  }
  return null;
}

export function getPendingPedestrianSelection(messages) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    // 新图提交后，旧截图的编号不能再用于选择。
    if (message.type === 'user' && message.image) return null;
    const result = message.pedestrianSearch;
    if (result) {
      return result.type === 'pedestrian_selection' && result.status === 'selection_required'
        ? message
        : null;
    }
  }
  return null;
}

export function getPedestrianSearchStatus(result) {
  switch (result.status) {
    case 'not_configured':
      return '登记库检索服务尚未配置，本次未执行匹配。';
    case 'no_compatible_features':
      return '登记库没有兼容的特征，本次无法完成匹配；不代表未找到此人。';
    case 'empty_history':
      return '当前保留期内没有可检索的历史轨迹特征，本次无法完成匹配；不代表未找到此人。';
    case 'no_identity_candidates':
      return '历史轨迹特征尚未关联到有效身份，本次无法返回人员候选。';
    case 'feature_space_missing':
      return '数据库中没有当前特征空间，本次未执行历史轨迹检索。';
    case 'feature_space_incompatible':
      return '数据库特征空间与当前模型不兼容，本次未执行历史轨迹检索。';
    case 'missing_image':
      return '请在本轮上传单人裁剪图后重新检索。';
    case 'invalid_image':
      return '查询图片无法解析，请重新上传单人裁剪图。';
    case 'no_person':
      return '截图中未检测到行人，请重新上传截图或裁剪单人人像后重试。';
    case 'selection_expired':
      return '待选择截图已过期或不存在，请重新上传截图。';
    case 'cancelled':
      return '已取消本次截图选择。';
    default:
      return Array.isArray(result.candidates) && result.candidates.length > 0
        ? ''
        : '本次检查的登记照片中暂无候选，不能据此排除该人员。';
  }
}

const ISO_TIME_PATTERN = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})/;

function parseOccurrenceTime(value) {
  if (typeof value !== 'string') return null;
  const text = value.trim();
  if (!text) return null;
  const match = ISO_TIME_PATTERN.exec(text);
  if (!match) return { text, date: null, time: null };
  return { text: `${match[1]} ${match[2]}`, date: match[1], time: match[2] };
}

// 把后端 ISO 时间转成“2026-11-04 22:13:30”；同一天只重复一次日期。
export function formatOccurrenceTimeRange(startAt, endAt) {
  const start = parseOccurrenceTime(startAt);
  if (!start) return '未知';
  const end = parseOccurrenceTime(endAt);
  if (!end || end.text === start.text) return start.text;
  if (start.date && start.date === end.date) return `${start.text} 至 ${end.time}`;
  return `${start.text} 至 ${end.text}`;
}

// 后端按 request_id 做请求去重，每次点击回放都需要新的标识。
export function createRequestId() {
  const webCrypto = typeof globalThis === 'undefined' ? null : globalThis.crypto;
  if (webCrypto && typeof webCrypto.randomUUID === 'function') {
    return webCrypto.randomUUID();
  }
  const bytes = new Uint8Array(16);
  if (webCrypto && typeof webCrypto.getRandomValues === 'function') {
    webCrypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

// 用轨迹的来源和时间定位可回放的录像资产。
export function buildPlaybackQuery(occurrence, requestId) {
  const source = typeof occurrence?.source_id === 'string' ? occurrence.source_id.trim() : '';
  const request = typeof requestId === 'string' ? requestId.trim() : '';
  const start = Date.parse(occurrence?.start_at);
  if (!source || !request || !Number.isFinite(start)) return null;
  const rawEnd = Date.parse(occurrence?.end_at);
  const end = Number.isFinite(rawEnd) && rawEnd > start ? rawEnd : start + 1;
  return {
    request_id: request,
    purpose: 'playback',
    source_id: source,
    start_at: new Date(start).toISOString(),
    end_at: new Date(end).toISOString(),
  };
}

export function pickPlaybackAsset(response) {
  const items = Array.isArray(response?.items) ? response.items : [];
  return items.find(item => item && typeof item.asset_id === 'string'
    && item.state === 'available') || null;
}

// 优先使用后端返回的录像内偏移；没有时按轨迹开始时间计算。
export function playbackOffsetMs(asset, occurrenceStartAt) {
  const supplied = Number(asset?.offset_ms);
  if (Number.isFinite(supplied)) return Math.max(0, supplied);
  const start = Date.parse(occurrenceStartAt);
  const assetStart = Date.parse(asset?.start_at);
  return Number.isFinite(start) && Number.isFinite(assetStart)
    ? Math.max(0, start - assetStart) : 0;
}

export function getRegistrationImageSrc(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  const image = value.trim();
  if (/^data:image\/(?:jpeg|png|webp);base64,[A-Za-z0-9+/=\s]+$/i.test(image)) {
    return image;
  }
  if (/^[A-Za-z0-9+/=\s]+$/.test(image)) {
    return `data:image/jpeg;base64,${image.replace(/\s/g, '')}`;
  }
  return null;
}
