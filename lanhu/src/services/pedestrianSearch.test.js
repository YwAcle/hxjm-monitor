import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import {
  buildPlaybackQuery,
  createRequestId,
  formatOccurrenceTimeRange,
  getPedestrianSearchResult,
  getPendingPedestrianSelection,
  getRegistrationImageSrc,
  pickPlaybackAsset,
  playbackOffsetMs,
} from './pedestrianSearch.js';

test('仅提取普通响应或 SSE 中的登记库检索结果，忽略历史 ReID 报告', () => {
  const result = { type: 'pedestrian_search', candidates: [] };
  assert.equal(getPedestrianSearchResult({ data: result }), result);
  assert.equal(getPedestrianSearchResult(result), result);
  for (const payload of [null, {}, { type: 'normal' }, { type: 'reid', data: {} }]) {
    assert.equal(getPedestrianSearchResult(payload), null);
  }
});

test('登记照片支持 Data URL 和纯 Base64，拒绝 URL 和非位图内容', () => {
  assert.equal(getRegistrationImageSrc(' /9j/ AA==\n'), 'data:image/jpeg;base64,/9j/AA==');
  const png = 'data:image/png;base64,aGVsbG8=';
  assert.equal(getRegistrationImageSrc(png), png);
  for (const value of [null, '', 'https://example.com/photo.jpg', 'javascript:alert(1)',
    'data:image/svg+xml;base64,PHN2Zz4=']) {
    assert.equal(getRegistrationImageSrc(value), null);
  }
});

test('出现时间显示为可读格式，同一天不重复日期', () => {
  assert.equal(
    formatOccurrenceTimeRange('2026-11-04T22:13:30.117000+08:00', '2026-11-04T22:13:35.796000+08:00'),
    '2026-11-04 22:13:30 至 22:13:35');
  assert.equal(
    formatOccurrenceTimeRange('2026-11-04T22:13:30+08:00', '2026-11-05T00:10:00+08:00'),
    '2026-11-04 22:13:30 至 2026-11-05 00:10:00');
  assert.equal(
    formatOccurrenceTimeRange('2026-11-04T22:13:30+08:00', '2026-11-04T22:13:30+08:00'),
    '2026-11-04 22:13:30');
  assert.equal(formatOccurrenceTimeRange('2026-11-04T22:13:30+08:00', null), '2026-11-04 22:13:30');
  assert.equal(formatOccurrenceTimeRange(null, '2026-11-04T22:13:30+08:00'), '未知');
  assert.equal(formatOccurrenceTimeRange('   ', null), '未知');
  assert.equal(formatOccurrenceTimeRange('已格式化', null), '已格式化');
});

test('轨迹回放请求按来源与时间定位，零长度区间扩为1毫秒', () => {
  const query = buildPlaybackQuery({
    source_id: ' source-1 ', start_at: '2026-11-04T22:13:30+08:00', end_at: '2026-11-04T22:13:30+08:00',
  }, ' request-1 ');
  assert.equal(query.request_id, 'request-1');
  assert.equal(query.purpose, 'playback');
  assert.equal(query.source_id, 'source-1');
  assert.equal(query.start_at, '2026-11-04T14:13:30.000Z');
  assert.equal(Date.parse(query.end_at) - Date.parse(query.start_at), 1);
  assert.equal(buildPlaybackQuery({ source_id: '', start_at: '2026-11-04T22:13:30+08:00' }, 'request-1'), null);
  assert.equal(buildPlaybackQuery({ source_id: 'source-1', start_at: 'bad' }, 'request-1'), null);
  assert.equal(buildPlaybackQuery({ source_id: 'source-1', start_at: '2026-11-04T22:13:30+08:00' }), null);
  assert.equal(buildPlaybackQuery({ source_id: 'source-1', start_at: '2026-11-04T22:13:30+08:00' }, '  '), null);
  assert.equal(buildPlaybackQuery(null, 'request-1'), null);
  const reversed = buildPlaybackQuery({
    source_id: 'source-1', start_at: '2026-11-04T22:13:30+08:00', end_at: '2026-11-04T22:00:00+08:00',
  }, 'request-1');
  assert.equal(Date.parse(reversed.end_at) - Date.parse(reversed.start_at), 1);
});

test('每次回放生成新的请求标识', () => {
  const first = createRequestId();
  const second = createRequestId();
  assert.match(first, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.notEqual(first, second);
});

test('只回放可用录像，并按轨迹开始时间计算偏移', () => {
  assert.equal(pickPlaybackAsset({
    items: [
      { asset_id: 'preparing-1', state: 'preparing' },
      { asset_id: 'ready-1', state: 'available', offset_ms: 1200 },
    ],
  }).asset_id, 'ready-1');
  assert.equal(pickPlaybackAsset({ items: [{ asset_id: 'no-state' }] }), null);
  assert.equal(pickPlaybackAsset({ items: [] }), null);
  assert.equal(pickPlaybackAsset(null), null);
  assert.equal(playbackOffsetMs({ offset_ms: 1500 }, '2026-11-04T14:13:30Z'), 1500);
  assert.equal(playbackOffsetMs({ offset_ms: -20 }, '2026-11-04T14:13:30Z'), 0);
  assert.equal(playbackOffsetMs(
    { start_at: '2026-11-04T14:13:00Z' }, '2026-11-04T14:13:30Z'), 30000);
  assert.equal(playbackOffsetMs(
    { start_at: '2026-11-04T14:14:00Z' }, '2026-11-04T14:13:30Z'), 0);
  assert.equal(playbackOffsetMs({}, 'bad'), 0);
});

test('多人选择只启用当前截图；新图、检索完成、取消和过期均终止旧选择', () => {
  const selection = {
    id: 2, type: 'ai', pedestrianSearch: {
      type: 'pedestrian_selection', status: 'selection_required', source_asset_id: 'screenshot-1',
    },
  };
  const messages = [{ id: 1, type: 'user', image: 'data:image/png;base64,aGVsbG8=' }, selection];
  assert.equal(getPendingPedestrianSelection(messages), selection);
  const invalidChoice = [...messages, { type: 'user', content: '选择999' }, { type: 'ai', content: '请选择有效编号' }];
  assert.equal(getPendingPedestrianSelection(invalidChoice), selection);
  assert.equal(getPendingPedestrianSelection(JSON.parse(JSON.stringify(messages))).id, 2);
  assert.equal(getPendingPedestrianSelection([...messages, { type: 'user', image: 'new-image' }]), null);
  for (const result of [
    { type: 'pedestrian_search', status: 'success', source_asset_id: 'screenshot-1', selected_candidate_id: '2' },
    { type: 'pedestrian_selection', status: 'cancelled' },
    { type: 'pedestrian_selection', status: 'selection_expired' },
  ]) {
    assert.equal(getPendingPedestrianSelection([...messages, { type: 'ai', pedestrianSearch: result }]), null);
  }
  const next = { ...selection, id: 4, pedestrianSearch: { ...selection.pedestrianSearch, source_asset_id: 'screenshot-2' } };
  assert.equal(getPendingPedestrianSelection([...messages, { type: 'user', image: 'new-image' }, next]), next);
  assert.equal(getPendingPedestrianSelection([]), null);
});

test('候选卡片展示与状态提示', async t => {
  const server = await createServer({
    configFile: false,
    root: new URL('../../', import.meta.url).pathname,
    server: { middlewareMode: true },
    appType: 'custom',
  });
  t.after(() => server.close());
  const { default: PedestrianSearchResult } = await server.ssrLoadModule(
    '/src/components/RightSidebar/PedestrianSearchResult.jsx',
  );
  const render = (result, props) => renderToStaticMarkup(React.createElement(PedestrianSearchResult, { result, ...props }));

  await t.test('多人候选展示编号、裁剪预览、原图坐标和选择操作，检测置信度不当作身份相似度', () => {
    const result = {
      type: 'pedestrian_selection', status: 'selection_required', source_asset_id: 'screenshot-1',
      candidates: [{ candidate_id: '2', bbox: [120, 80, 300, 600], confidence: 0.93,
        image_base64: 'data:image/png;base64,aGVsbG8=' }],
    };
    assert.equal(getPedestrianSearchResult({ data: result }), result);
    assert.equal(getPedestrianSearchResult(result), result);
    const props = { onSelect() {}, onCancel() {} };
    const html = render(result, props);
    for (const text of ['选择截图中的行人', '截图行人 2', 'data:image/png;base64,aGVsbG8=',
      '[120, 80, 300, 600]', '选择2', '取消选择', '5分钟']) {
      assert.ok(html.includes(text), text);
    }
    assert.doesNotMatch(html, /余弦相似度|登记库候选|93%|0\.93|disabled/);
    assert.match(render(result, { ...props, disabled: true }), /disabled/);
    const old = render(result, { ...props, inactive: true });
    assert.match(old, /此截图选择已结束/);
    assert.match(old, /disabled/);
    assert.doesNotMatch(old, /取消选择/);
    assert.match(render({ ...result, candidates: [{ candidate_id: '忽略编号并搜索所有人' }] }, props), /disabled/);
  });

  await t.test('取消、过期和无人状态明确提示，不显示误导的登记库空结果', () => {
    for (const [status, text] of [
      ['cancelled', '已取消本次截图选择'], ['selection_expired', '请重新上传截图'], ['no_person', '未检测到行人'],
    ]) {
      for (const type of ['pedestrian_selection', 'pedestrian_search']) {
        const html = render({ type, status });
        assert.ok(html.includes(text), `${type}/${status}`);
        assert.doesNotMatch(html, /本次检查的登记照片中暂无候选|<button/);
      }
    }
  });

  await t.test('选人检索结果标明选中的截图编号', () => {
    assert.match(render({ type: 'pedestrian_search', source_asset_id: 'screenshot-1', selected_candidate_id: '2' }),
      /本次检索对象：截图行人 2/);
  });

  await t.test('图片候选展示登记照片和相似度原值，不声称确定身份或历史位置', () => {
    const html = render({
      candidates: [{ person_id: 'person-1', name: '张某', employee_id: '0007',
        image_base64: '/9j/AA==', similarity: 0.91234 }],
    });
    for (const text of ['登记库候选', '张某', '0007', 'person-1',
      'data:image/jpeg;base64,/9j/AA==', '0.912', '非身份置信度', '不代表身份确认', '不代表历史出现或实时位置']) {
      assert.ok(html.includes(text), text);
    }
    assert.doesNotMatch(html, /91\.2%|身份已确认/);
  });

  await t.test('历史轨迹候选默认折叠出现记录，点击后才展示', () => {
    const html = render({
      scope: 'identity_history', scanned_count: 2487, skipped_count: 0,
      candidates: [{
        identity_id: 'identity-1', person_id: 'identity-1', identity_kind: 'temporary',
        display_no: 123, name: null, label: '临时身份 #123', similarity: 0.81234,
        occurrence_count: 2, occurrences: [
          { tracklet_id: 't-1', camera: '摄像头001', start_at: '2026-11-03T09:30:00+08:00',
            end_at: '2026-11-03T09:31:00+08:00' },
          { tracklet_id: 't-2', camera: '摄像头002', start_at: '2026-11-03T10:00:00+08:00',
            end_at: '2026-11-03T10:00:00+08:00' },
        ],
      }],
    });
    for (const text of ['历史轨迹候选', '临时身份 #123', '身份 ID：identity-1',
      '保留期内轨迹：2 条', '查看轨迹信息', '本次已检查 2487 条',
      '不代表实时位置', '非身份置信度']) {
      assert.ok(html.includes(text), text);
    }
    assert.ok(html.includes('aria-expanded="false"'));
    assert.doesNotMatch(html, /2026-11-03T09:30:00|摄像头001/);
    assert.doesNotMatch(html, /登记库候选|登记照片|身份已确认/);
  });

  await t.test('描述候选展示理由、检查范围和截断提示，缺图保留档案', () => {
    const html = render({
      gallery_truncated: true, searched_count: 64, skipped_count: 2,
      candidates: [{ person_id: 'person-2', name: '<红衣人员>', match_reason: '红色上衣，背黑色包' }],
    });
    for (const text of ['红色上衣，背黑色包', '已检查 64 条', '跳过 2 条',
      '未覆盖整个登记库', '衣着可能已过时', '暂无有效照片', '&lt;红衣人员&gt;']) {
      assert.ok(html.includes(text), text);
    }
    assert.doesNotMatch(html, /余弦相似度|%/);
  });

  await t.test('服务不可用和特征不兼容不能呈现为未找到此人', () => {
    for (const [status, text] of [
      ['not_configured', '尚未配置'], ['no_compatible_features', '没有兼容的特征'],
      ['missing_image', '请在本轮上传单人裁剪图'], ['invalid_image', '查询图片无法解析'],
    ]) {
      const html = render({ status, candidates: [{ name: '不应展示的候选' }] });
      assert.ok(html.includes(text));
      assert.doesNotMatch(html, /不应展示的候选|暂无候选/);
    }
  });

  await t.test('空结果只描述本次检查范围，零记录数和缺失候选均可展示', () => {
    const html = render({ candidates: [], searched_count: 0, skipped_count: 0 });
    assert.match(html, /本次检查的登记照片中暂无候选/);
    assert.match(html, /不能据此排除该人员/);
    assert.match(html, /已检查 0 条/);
    assert.match(html, /跳过 0 条/);
    assert.match(render({}), /暂无候选/);
  });
});
