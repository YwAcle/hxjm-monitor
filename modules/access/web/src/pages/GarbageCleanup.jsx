import React, { useEffect, useState } from 'react';
import { businessApi } from '../services/businessApi';
import { createTraceId } from '../services/agentChat';
import './GarbageCleanup.css';

const states = { pending: '待执行', running: '执行中', succeeded: '已完成', failed: '失败', unknown: '结果未知', cancelled: '已取消', expired: '已过期' };
export default function GarbageCleanup() {
  const [data, setData] = useState({ items: [], routes: {} });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(null);
  const refresh = async () => {
    try { setData(await businessApi.garbageEvents()); setError(''); }
    catch (e) { setError(e.message); }
  };
  useEffect(() => { refresh(); const timer = setInterval(refresh, 5000); return () => clearInterval(timer); }, []);
  async function submit(event) {
    setBusy(event.event_id);
    try { await businessApi.cleanupGarbage({ event_id: event.event_id, request_id: createTraceId() }); await refresh(); }
    catch (e) { setError(e.message); }
    finally { setBusy(null); }
  }
  return <main className="garbage-cleanup">
    <header><div><a href="/">返回视频监控</a><h1>垃圾检测与清理</h1></div><button onClick={refresh}>刷新</button></header>
    <p>检测事件独立记录。清理使用已确认的机器狗路线；路线执行完成后仍需核实垃圾是否清除；模拟结果仅用于流程检查。</p>
    {!data.cleanup_enabled && <p role="status">机器狗清理未启用，事件查询可正常使用。</p>}
    {error && <p role="alert" className="cleanup-error">{error}</p>}
    {!data.items.length && !error && <p>暂无垃圾事件。</p>}
    <section aria-label="垃圾事件列表">{data.items.map(event => {
      const detection = event.detection || {}, task = event.cleanup, device = task?.device;
      const unknown = ['REMOTE_OUTCOME_UNKNOWN', 'DEVICE_SESSION_LOST', 'DEVICE_RECONCILIATION_REQUIRED'].includes(task?.error_code);
      return <article key={event.event_id}>
        <h2>{detection.category || '垃圾候选'} <small>{event.state === 'closed' ? '已清理' : '待处理'}</small></h2>
        <dl><dt>检测时间</dt><dd>{new Date(event.start_at).toLocaleString()}</dd>
          <dt>视频来源</dt><dd>{event.source_id}</dd><dt>图片区域</dt><dd>{detection.region} · {JSON.stringify(detection.bbox)}</dd>
          <dt>检测置信度</dt><dd>{detection.confidence == null ? '未提供' : `${(detection.confidence * 100).toFixed(1)}%`}</dd>
          <dt>事件 ID</dt><dd>{event.event_id}</dd><dt>检测成果</dt><dd>{detection.result_id || '未提供'}</dd>
          <dt>截图</dt><dd>{event.evidence?.some(e => e.asset_id) ? '已关联媒体证据' : '当前成果未提供截图'}</dd>
          <dt>清理路线</dt><dd>{data.routes[event.source_id] || '未配置定位映射'}</dd>
          <dt>清理任务</dt><dd>{task?.task_id || '尚未提交'}</dd>
          <dt>执行状态</dt><dd>{unknown ? '执行结果未知，请人工核对，禁止自动重发' : states[task?.state] || '未提交'}{device?.simulated && '（本地模拟）'}</dd>
          <dt>外部任务 ID</dt><dd>{device?.external_task_id || '当前协议未提供'}</dd>
          {task?.error_code && <><dt>错误</dt><dd>{task.error_code}</dd></>}
          {device && <><dt>执行反馈</dt><dd><pre>{JSON.stringify(device, null, 2)}</pre></dd></>}
        </dl>
        <button disabled={busy === event.event_id || !!task || event.state !== 'open' || !data.cleanup_enabled || !data.routes[event.source_id]} onClick={() => submit(event)}>
          {busy === event.event_id ? '提交中…' : task ? '已关联清理任务' : '提交清理任务'}
        </button>
      </article>;
    })}</section>
  </main>;
}
