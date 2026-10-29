import { collectAgentResults } from './agentResults.js';
const DEFAULT_AGENT_BASE_URL = '/api';
const DEFAULT_TIMEOUT_MS = 190_000;
const SESSION_ID_PATTERN = /^[A-Za-z0-9._:-]{1,128}$/;
export const SUPPORTED_IMAGE_TYPES = Object.freeze(['image/jpeg', 'image/png', 'image/webp']);
export const MAX_IMAGE_SIZE = 10 * 1024 * 1024;

const configuredBaseUrl = import.meta.env?.VITE_AGENT_BASE_URL?.trim();

export const AGENT_BASE_URL = (
  configuredBaseUrl || DEFAULT_AGENT_BASE_URL
).replace(/\/+$/, '');

export class AgentApiError extends Error {
  constructor(message, status = null, { errorCode = null, traceId = null } = {}) {
    super(message);
    this.name = 'AgentApiError';
    this.status = status;
    this.errorCode = errorCode;
    this.traceId = traceId;
  }
}

export function isValidSessionId(sessionId) {
  return typeof sessionId === 'string' && SESSION_ID_PATTERN.test(sessionId);
}

export function createSessionId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  return `browser-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

export function createTraceId() {
  return createSessionId();
}

async function parseResponse(response) {
  const contentType = response.headers?.get?.('content-type') || '';

  if (!contentType.includes('application/json')) {
    const body = await response.text();
    throw new AgentApiError(
      response.ok
        ? 'Agent 返回了无法识别的响应格式'
        : body || `Agent 请求失败：HTTP ${response.status}`,
      response.status,
    );
  }

  let result;
  try {
    result = await response.json();
  } catch {
    throw new AgentApiError('Agent 返回的 JSON 数据无法解析', response.status);
  }

  if (!response.ok) {
    throw new AgentApiError(
      result?.error || `Agent 请求失败：HTTP ${response.status}`,
      response.status,
      { errorCode: result?.error_code, traceId: result?.trace_id },
    );
  }

  return result;
}

async function request(
  path,
  options,
  { fetchImpl = fetch, timeoutMs = DEFAULT_TIMEOUT_MS, signal: externalSignal } = {},
) {
  const controller = new AbortController();
  const abortFromExternalSignal = () => controller.abort(externalSignal.reason);

  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort(externalSignal.reason);
    } else {
      externalSignal.addEventListener('abort', abortFromExternalSignal, { once: true });
    }
  }

  const timeoutId = setTimeout(() => controller.abort('timeout'), timeoutMs);

  try {
    const url = `${AGENT_BASE_URL}${path}`;
    const response = await fetchImpl(url, {
      ...options,
      credentials: 'omit',
      signal: controller.signal,
    });
    return await parseResponse(response);
  } catch (error) {
    if (error instanceof AgentApiError) {
      throw error;
    }
    if (controller.signal.aborted) {
      throw new AgentApiError(
        externalSignal?.aborted ? '请求已取消' : 'Agent 响应超时，请稍后重试',
      );
    }
    throw new AgentApiError('无法连接 Agent 服务，请检查网络或服务状态');
  } finally {
    clearTimeout(timeoutId);
    externalSignal?.removeEventListener('abort', abortFromExternalSignal);
  }
}

function assertSessionId(sessionId) {
  if (!isValidSessionId(sessionId)) {
    throw new AgentApiError('当前会话 ID 无效，请新建会话后重试');
  }
}

function assertTraceId(traceId) {
  if (!isValidSessionId(traceId)) {
    throw new AgentApiError('请求追踪 ID 无效');
  }
}

function parseSseFrame(frame) {
  let eventName = 'message';
  const dataLines = [];

  for (const line of frame.split(/\r\n|\r|\n/)) {
    if (!line || line.startsWith(':')) continue;
    const separator = line.indexOf(':');
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? '' : line.slice(separator + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') eventName = value;
    if (field === 'data') dataLines.push(value);
  }

  if (dataLines.length === 0) return null;

  try {
    return { event: eventName, data: JSON.parse(dataLines.join('\n')) };
  } catch {
    throw new AgentApiError('Agent 返回的流式数据无法解析');
  }
}

async function consumeSse(response, onEvent) {
  if (!response.body || typeof response.body.getReader !== 'function') {
    throw new AgentApiError('当前浏览器不支持流式响应', response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  const processFrames = (flush = false) => {
    const frames = [];
    let separator;
    while ((separator = buffer.match(/\r\n\r\n|\n\n|\r\r/))) {
      frames.push(buffer.slice(0, separator.index));
      buffer = buffer.slice(separator.index + separator[0].length);
    }
    if (flush && buffer) frames.push(buffer);
    if (flush) buffer = '';
    for (const frame of frames) {
      if (!frame.trim()) continue;
      const parsed = parseSseFrame(frame);
      if (parsed) onEvent(parsed);
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    processFrames();
  }
  buffer += decoder.decode();
  processFrames(true);
}

function validateImageFile(file) {
  if (!file || typeof file !== 'object') {
    throw new AgentApiError('请选择需要上传的图片', 400, { errorCode: 'INVALID_IMAGE' });
  }
  if (!SUPPORTED_IMAGE_TYPES.includes(file.type)) {
    throw new AgentApiError('仅支持 JPEG、PNG 和 WebP 图片', 400, {
      errorCode: 'UNSUPPORTED_IMAGE_FORMAT',
    });
  }
  if (typeof file.size === 'number' && file.size > MAX_IMAGE_SIZE) {
    throw new AgentApiError('图片文件不能超过 10 MB', 413, { errorCode: 'IMAGE_TOO_LARGE' });
  }
}

function assertChatResponse(result, fallbackTraceId) {
  if (!result || typeof result !== 'object') {
    throw new AgentApiError('Agent 返回的数据格式不正确');
  }
  if (!isValidSessionId(result.session_id)) {
    throw new AgentApiError('Agent 响应中缺少有效的会话 ID');
  }
  // 兼容旧版 Agent：后端未返回 trace_id 时仍保留本次请求生成的 ID。
  if (!result.trace_id && fallbackTraceId) {
    result.trace_id = fallbackTraceId;
  }
  if (result.trace_id) {
    assertTraceId(result.trace_id);
  }
  return result;
}

export async function sendAgentMessage(prompt, sessionId, options) {
  assertSessionId(sessionId);
  const traceId = createTraceId();
  const result = await request('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Trace-ID': traceId },
    body: JSON.stringify({ prompt, session_id: sessionId }),
  }, options);
  return assertChatResponse(result, traceId);
}

export async function streamAgentMessage(prompt, sessionId, onEvent, options = {}) {
  assertSessionId(sessionId);
  if (typeof onEvent !== 'function') {
    throw new AgentApiError('流式事件处理函数无效');
  }

  const traceId = createTraceId();
  const { fetchImpl = fetch, signal, file } = options;
  let body;
  if (file) {
    validateImageFile(file);
    body = new FormData();
    body.append('prompt', prompt);
    body.append('file', file);
    body.append('session_id', sessionId);
    body.append('trace_id', traceId);
  } else {
    body = JSON.stringify({ prompt, session_id: sessionId, trace_id: traceId });
  }

  try {
    const url = `${AGENT_BASE_URL}/chat/stream`;
    const response = await fetchImpl(url, {
      method: 'POST',
      credentials: 'omit',
      headers: {
        ...(file ? {} : { 'Content-Type': 'application/json' }),
        Accept: 'text/event-stream',
        'X-Session-ID': sessionId,
        'X-Trace-ID': traceId,
      },
      body,
      signal,
    });

    if (!response.ok) {
      return await parseResponse(response);
    }

    const contentType = response.headers?.get?.('content-type') || '';
    if (!contentType.includes('text/event-stream')) {
      throw new AgentApiError('Agent 返回了无法识别的响应格式', response.status, { traceId });
    }

    let doneEvent = null;
    let results = [];
    await consumeSse(response, streamEvent => {
      const { event, data } = streamEvent;
      if (event === 'result') results = collectAgentResults(data, results);
      if (event === 'error') {
        throw new AgentApiError(data?.error || '处理请求失败', response.status, {
          errorCode: data?.error_code,
          traceId: data?.trace_id || traceId,
        });
      }
      if (event === 'done') {
        if (!isValidSessionId(data?.session_id)) {
          throw new AgentApiError('Agent 响应中缺少有效的会话 ID');
        }
        doneEvent = { ...data, trace_id: data.trace_id || traceId };
      }
      onEvent(streamEvent);
    });

    if (!doneEvent) {
      throw new AgentApiError('Agent 流式响应意外中断', response.status, { traceId });
    }
    return { ...doneEvent, results: collectAgentResults(doneEvent, results) };
  } catch (error) {
    if (error instanceof AgentApiError) throw error;
    if (signal?.aborted || error?.name === 'AbortError') {
      throw new AgentApiError('请求已取消');
    }
    throw new AgentApiError('无法连接 Agent 服务，请检查网络或服务状态');
  }
}

export async function sendAgentImageMessage(prompt, file, sessionId, options) {
  assertSessionId(sessionId);
  validateImageFile(file);
  const traceId = createTraceId();
  const formData = new FormData();
  formData.append('prompt', prompt);
  formData.append('file', file);
  formData.append('session_id', sessionId);
  formData.append('trace_id', traceId);

  const result = await request('/chat', {
    method: 'POST',
    body: formData,
  }, options);
  return assertChatResponse(result, traceId);
}

export async function clearAgentMemory(sessionId, options) {
  assertSessionId(sessionId);
  const traceId = createTraceId();
  return request(
    `/sessions/${encodeURIComponent(sessionId)}/memory`,
    { method: 'DELETE', headers: { 'X-Trace-ID': traceId } },
    options,
  );
}
