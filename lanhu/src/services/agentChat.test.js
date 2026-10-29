import assert from 'node:assert/strict';
import test from 'node:test';
import { getPedestrianSearchResult } from './pedestrianSearch.js';

import {
  AgentApiError,
  clearAgentMemory,
  isValidSessionId,
  MAX_IMAGE_SIZE,
  sendAgentImageMessage,
  sendAgentMessage,
  streamAgentMessage,
} from './agentChat.js';

const jsonResponse = (body, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: { 'Content-Type': 'application/json' },
});

test('Agent text, image, streaming and memory requests carry no login credentials', async () => {
  const fetchImpl = async (url, options) => {
    assert.equal(options.headers?.Authorization, undefined);
    assert.equal(options.headers?.['X-HXJM-Service-Token'], undefined);
    assert.equal(options.credentials, 'omit');
    if (url.endsWith('/stream')) return sseResponse(['event: done\ndata: {"session_id":"shared-session"}\n\n']);
    return jsonResponse({ session_id: 'shared-session', status: 'ok' });
  };
  await sendAgentMessage('查询', 'shared-session', { fetchImpl });
  await sendAgentImageMessage('查图', new Blob(['image'], { type: 'image/jpeg' }), 'shared-session', { fetchImpl });
  await streamAgentMessage('查询', 'shared-session', () => {}, { fetchImpl });
  await clearAgentMemory('shared-session', { fetchImpl });
});

test('文本聊天发送并接收同一个 session_id', async () => {
  let request;
  const fetchImpl = async (url, options) => {
    request = { url, options };
    return jsonResponse({
      session_id: 'session-text-1',
      type: 'normal',
      text: 'ok',
    });
  };

  const result = await sendAgentMessage('记住 9527', 'session-text-1', { fetchImpl });

  assert.equal(request.url, '/api/chat');
  assert.equal(request.options.method, 'POST');
  assert.match(request.options.headers['X-Trace-ID'], /^[A-Za-z0-9._:-]{1,128}$/);
  assert.deepEqual(JSON.parse(request.options.body), {
    prompt: '记住 9527',
    session_id: 'session-text-1',
  });
  assert.equal(result.session_id, 'session-text-1');
});

test('图片聊天使用 FormData 并携带 session_id', async () => {
  let request;
  const fetchImpl = async (url, options) => {
    request = { url, options };
    return jsonResponse({ session_id: 'session-image-1', type: 'normal', text: 'ok' });
  };

  await sendAgentImageMessage(
    '分析图片',
    new Blob(['image'], { type: 'image/jpeg' }),
    'session-image-1',
    { fetchImpl },
  );

  assert.equal(request.url, '/api/chat');
  assert.equal(request.options.headers, undefined);
  assert.equal(request.options.body.get('prompt'), '分析图片');
  assert.equal(request.options.body.get('session_id'), 'session-image-1');
  assert.match(request.options.body.get('trace_id'), /^[A-Za-z0-9._:-]{1,128}$/);
});

test('图片上传在请求前校验格式和大小', async () => {
  await assert.rejects(
    sendAgentImageMessage(
      '分析图片',
      new Blob(['image'], { type: 'image/gif' }),
      'session-image-1',
      { fetchImpl: async () => { throw new Error('不应发起请求'); } },
    ),
    error => error instanceof AgentApiError
      && error.errorCode === 'UNSUPPORTED_IMAGE_FORMAT',
  );

  const oversized = new Blob([new Uint8Array(MAX_IMAGE_SIZE + 1)], { type: 'image/jpeg' });
  await assert.rejects(
    sendAgentImageMessage(
      '分析图片',
      oversized,
      'session-image-1',
      { fetchImpl: async () => { throw new Error('不应发起请求'); } },
    ),
    error => error instanceof AgentApiError
      && error.status === 413
      && error.errorCode === 'IMAGE_TOO_LARGE',
  );
});

test('后端错误保留 error_code 和 trace_id', async () => {
  const fetchImpl = async () => jsonResponse({
    error: '仅支持 JPEG、PNG 和 WebP 图片',
    error_code: 'UNSUPPORTED_IMAGE_FORMAT',
    trace_id: 'trace-error-1',
  }, 400);

  await assert.rejects(
    sendAgentMessage('分析图片', 'valid-session', { fetchImpl }),
    error => error instanceof AgentApiError
      && error.status === 400
      && error.errorCode === 'UNSUPPORTED_IMAGE_FORMAT'
      && error.traceId === 'trace-error-1',
  );
});

test('清空会话调用 memory DELETE 接口', async () => {
  let request;
  const fetchImpl = async (url, options) => {
    request = { url, options };
    return jsonResponse({ status: 'ok', session_id: 'session-clear-1', cleared: true });
  };

  await clearAgentMemory('session-clear-1', { fetchImpl });

  assert.equal(request.url, '/api/sessions/session-clear-1/memory');
  assert.equal(request.options.method, 'DELETE');
});

test('接口错误优先展示后端 error 字段', async () => {
  const fetchImpl = async () => jsonResponse({ error: 'session_id 非法' }, 400);

  await assert.rejects(
    sendAgentMessage('hello', 'valid-session', { fetchImpl }),
    error => error instanceof AgentApiError
      && error.status === 400
      && error.message === 'session_id 非法',
  );
});

test('session_id 校验符合后端约定', () => {
  assert.equal(isValidSessionId('user_1001:chat-27.1'), true);
  assert.equal(isValidSessionId('包含空格'), false);
  assert.equal(isValidSessionId('chat/001'), false);
  assert.equal(isValidSessionId('x'.repeat(129)), false);
});

const sseResponse = (chunks, { status = 200, contentType = 'text/event-stream' } = {}) => {
  const encoder = new TextEncoder();
  return new Response(new ReadableStream({
    start(controller) {
      chunks.forEach(chunk => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  }), {
    status,
    headers: { 'Content-Type': contentType },
  });
};

const pedestrianResult = {
  type: 'pedestrian_search',
  status: 'success',
  candidates: [{ person_id: 'person-1', name: '登记人员', image_base64: '/9j/AA==', similarity: 0.91 }],
};

test('普通聊天保留 data 中的登记库候选和照片', async () => {
  const result = await sendAgentMessage('查找穿红衣的人', 'gallery-session', {
    fetchImpl: async () => jsonResponse({
      session_id: 'gallery-session', type: 'agent', text: '找到候选', data: pedestrianResult,
    }),
  });
  assert.deepEqual(getPedestrianSearchResult(result), pedestrianResult);
});

test('图片流式检索在 delta 和 done 之间透传跨分片 result，保留候选照片', async () => {
  const events = [];
  const frame = `event: result\ndata: ${JSON.stringify(pedestrianResult)}\n\n`;
  let searchResult = null;
  const done = await streamAgentMessage('用这张单人图片找登记候选', 'gallery-session', event => {
    events.push(event.event);
    if (event.event === 'result') searchResult = getPedestrianSearchResult(event.data);
  }, {
    file: new Blob(['query-image'], { type: 'image/jpeg' }),
    fetchImpl: async (_url, { body }) => {
      assert.equal(await body.get('file').text(), 'query-image');
      assert.equal(body.get('session_id'), 'gallery-session');
      return sseResponse([
        'event: delta\ndata: {"text":"找到登记候选。"}\n\n',
        frame.slice(0, 47), frame.slice(47),
        'event: done\ndata: {"session_id":"gallery-session","finish_reason":"final"}\n\n',
      ]);
    },
  });
  assert.deepEqual(events, ['delta', 'result', 'done']);
  assert.deepEqual(searchResult, pedestrianResult);
  assert.equal(done.session_id, 'gallery-session');
});

test('普通图片聊天保留多人候选，并以同一 session_id 发送纯文本选择和取消', async () => {
  const selection = {
    type: 'pedestrian_selection', status: 'selection_required', source_asset_id: 'screenshot-json',
    candidates: [{ candidate_id: '2', bbox: [120, 80, 300, 600], image_base64: '/9j/AA==' }],
  };
  const result = await sendAgentImageMessage('用截图在登记库找相似行人',
    new Blob(['screenshot'], { type: 'image/png' }), 'selection-json-session', {
      fetchImpl: async (_url, { body }) => {
        assert.equal(body.get('session_id'), 'selection-json-session');
        return jsonResponse({ session_id: 'selection-json-session', type: 'agent', data: selection });
      },
    });
  assert.deepEqual(getPedestrianSearchResult(result), selection);
  for (const prompt of ['选择2', '取消选择']) {
    await sendAgentMessage(prompt, result.session_id, {
      fetchImpl: async (_url, { body }) => {
        assert.deepEqual(JSON.parse(body), { prompt, session_id: 'selection-json-session' });
        return jsonResponse({ session_id: 'selection-json-session', type: 'agent' });
      },
    });
  }
});

test('SSE 两轮续接：截图返回多人预览，选择沿用后端 session_id 且不重复上传图片', async () => {
  const selection = {
    type: 'pedestrian_selection', status: 'selection_required', source_asset_id: 'screenshot-stream',
    candidates: [{ candidate_id: '2', bbox: [120, 80, 300, 600], image_base64: '/9j/AA==' }],
  };
  let selectedResult;
  const frame = `event: result\ndata: ${JSON.stringify(selection)}\n\n`;
  const first = await streamAgentMessage('用截图在登记库找相似行人', 'selection-session', event => {
    if (event.event === 'result') selectedResult = getPedestrianSearchResult(event.data);
  }, {
    file: new Blob(['screenshot'], { type: 'image/png' }),
    fetchImpl: async (_url, { body }) => {
      assert.equal(body.get('session_id'), 'selection-session');
      assert.equal(await body.get('file').text(), 'screenshot');
      return sseResponse([frame.slice(0, 55), frame.slice(55),
        'event: done\ndata: {"session_id":"canonical-selection-session"}\n\n']);
    },
  });
  assert.deepEqual(selectedResult, selection);
  const search = { ...pedestrianResult, source_asset_id: selection.source_asset_id, selected_candidate_id: '2' };
  await streamAgentMessage('选择2', first.session_id, event => {
    if (event.event === 'result') selectedResult = getPedestrianSearchResult(event.data);
  }, {
    fetchImpl: async (_url, { body, headers }) => {
      assert.equal(headers['Content-Type'], 'application/json');
      assert.equal(headers['X-Session-ID'], 'canonical-selection-session');
      const request = JSON.parse(body);
      assert.equal(request.prompt, '选择2');
      assert.equal(request.session_id, 'canonical-selection-session');
      assert.equal(request.file, undefined);
      assert.equal(request.image, undefined);
      return sseResponse([`event: result\ndata: ${JSON.stringify(search)}\n\n`,
        'event: done\ndata: {"session_id":"canonical-selection-session"}\n\n']);
    },
  });
  assert.deepEqual(selectedResult, search);
});

test('流式聊天解析跨分片 SSE 并返回 done 数据', async () => {
  let request;
  const events = [];
  const fetchImpl = async (url, options) => {
    request = { url, options };
    return sseResponse([
      'event: status\r',
      '\ndata: {"stage":"processing"}\r\n\r\nevent: del',
      'ta\r\ndata: {"text":"最近一次"}\r\n\r\nevent: delta\ndata: {"text":"异常"}\n\n',
      'event: done\ndata: {"session_id":"stream-session","finish_reason":"final","steps":2}\n\n',
    ]);
  };

  const result = await streamAgentMessage(
    '最近一次异常是什么？',
    'stream-session',
    event => events.push(event),
    { fetchImpl },
  );

  assert.equal(request.url, '/api/chat/stream');
  assert.equal(request.options.headers.Accept, 'text/event-stream');
  assert.equal(request.options.headers['X-Session-ID'], 'stream-session');
  assert.equal(JSON.parse(request.options.body).session_id, 'stream-session');
  assert.deepEqual(events.map(item => item.event), ['status', 'delta', 'delta', 'done']);
  assert.equal(events[1].data.text + events[2].data.text, '最近一次异常');
  assert.equal(result.session_id, 'stream-session');
  assert.match(result.trace_id, /^[A-Za-z0-9._:-]{1,128}$/);
});

test('流式聊天处理 SSE error 事件', async () => {
  const fetchImpl = async () => sseResponse([
    'event: error\ndata: {"error":"处理请求失败","error_code":"INTERNAL_ERROR"}\n\n',
  ]);

  await assert.rejects(
    streamAgentMessage('hello', 'stream-session', () => {}, { fetchImpl }),
    error => error instanceof AgentApiError
      && error.message === '处理请求失败'
      && error.errorCode === 'INTERNAL_ERROR',
  );
});

test('图片分析通过流式接口上传文件并共用 SSE 事件处理', async () => {
  let request;
  const events = [];
  const file = new Blob(['image'], { type: 'image/png' });
  const result = await streamAgentMessage('', 'image-stream-session', event => events.push(event), {
    file,
    fetchImpl: async (url, options) => {
      request = { url, options };
      return sseResponse([
        'event: status\ndata: {"stage":"processing"}\n\n',
        'event: delta\ndata: {"text":"图片中有行人。"}\n\n',
        'event: done\ndata: {"session_id":"image-stream-session","finish_reason":"final"}\n\n',
      ]);
    },
  });
  assert.equal(request.url, '/api/chat/stream');
  assert.equal(request.options.headers['Content-Type'], undefined);
  assert.equal(request.options.headers.Accept, 'text/event-stream');
  assert.equal(request.options.body.get('prompt'), '');
  assert.equal(request.options.body.get('session_id'), 'image-stream-session');
  assert.equal(request.options.body.get('trace_id'), request.options.headers['X-Trace-ID']);
  assert.equal(await request.options.body.get('file').text(), 'image');
  assert.equal(request.options.body.has('image'), false);
  assert.deepEqual(events.map(event => event.event), ['status', 'delta', 'done']);
  assert.equal(result.session_id, 'image-stream-session');
});

test('流式图片请求保留上传校验错误与取消信号', async () => {
  await assert.rejects(streamAgentMessage('', 'image-session', () => {}, {
    file: new Blob(['image'], { type: 'image/gif' }),
    fetchImpl: async () => { throw new Error('不应发起请求'); },
  }), error => error.errorCode === 'UNSUPPORTED_IMAGE_FORMAT');

  const controller = new AbortController();
  await assert.rejects(streamAgentMessage('', 'image-session', () => {}, {
    file: new Blob(['image'], { type: 'image/jpeg' }),
    signal: controller.signal,
    fetchImpl: async (_url, { signal }) => {
      assert.equal(signal, controller.signal);
      controller.abort();
      throw new DOMException('Aborted', 'AbortError');
    },
  }), error => error instanceof AgentApiError && error.message === '请求已取消');
});

test('流式聊天处理开始 SSE 前的 JSON HTTP 错误', async () => {
  const fetchImpl = async () => jsonResponse({
    error: '缺少 prompt',
    error_code: 'MISSING_PROMPT',
  }, 400);

  await assert.rejects(
    streamAgentMessage('', 'stream-session', () => {}, { fetchImpl }),
    error => error instanceof AgentApiError
      && error.status === 400
      && error.errorCode === 'MISSING_PROMPT',
  );
});

test('流式聊天要求以 done 事件正常结束', async () => {
  const fetchImpl = async () => sseResponse([
    'event: delta\ndata: {"text":"未完成"}',
  ]);

  await assert.rejects(
    streamAgentMessage('hello', 'stream-session', () => {}, { fetchImpl }),
    error => error instanceof AgentApiError && error.message === 'Agent 流式响应意外中断',
  );
});

test('SSE最终响应保留按序到达的全部工具结果和图片放大结果', async () => {
  const directory = { type: 'person_directory', items: [{ display_name: '张三' }] };
  const image = { type: 'super_resolution', data: { image_base64: 'aGVsbG8=', scale: 2 } };
  const response = await streamAgentMessage('查询', 'multi-session', () => {}, {
    fetchImpl: async () => sseResponse([
      `event: result\ndata: ${JSON.stringify(directory)}\n\n`,
      `event: result\ndata: ${JSON.stringify(image)}\n\n`,
      'event: done\ndata: {"session_id":"multi-session"}\n\n',
    ]),
  });
  assert.deepEqual(response.results.map(value => value.type), ['person_directory', 'super_resolution']);
  assert.equal(response.results[1].image_base64, 'aGVsbG8=');
});
