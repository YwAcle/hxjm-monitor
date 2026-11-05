import React from 'react';
import ReactDOM from 'react-dom';
import { businessApi } from '../../services/businessApi';
import VideoModal from '../VideoModal/VideoModal';
import styles from './BusinessPanel.module.css';
import BusinessObjects from './BusinessObjects';

function localInput(date) {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 19);
}

function displayTime(value) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—';
}

function HistoryPanel({ onClose }) {
  const [checking, setChecking] = React.useState(true);
  const [sources, setSources] = React.useState([]);
  const [sourceId, setSourceId] = React.useState('');
  const [startAt, setStartAt] = React.useState(() => localInput(new Date(Date.now() - 60 * 60_000)));
  const [endAt, setEndAt] = React.useState(() => localInput(new Date()));
  const [result, setResult] = React.useState(null);
  const [query, setQuery] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const [playback, setPlayback] = React.useState(null);
  const requestRef = React.useRef(null);
  const panelRef = React.useRef(null);

  const loadSources = React.useCallback(async signal => {
    const data = await businessApi.sources(signal);
    setSources(data.items || []);
    setSourceId(data.items?.[0]?.source_id || '');
  }, []);

  React.useEffect(() => {
    const controller = new AbortController();
    const previousFocus = document.activeElement;
    panelRef.current?.focus();
    (async () => {
      try {
        await loadSources(controller.signal);
      } catch (exception) {
        if (exception.name !== 'AbortError') setError(exception.message);
      } finally {
        if (!controller.signal.aborted) setChecking(false);
      }
    })();
    return () => {
      controller.abort();
      requestRef.current?.abort();
      previousFocus?.focus();
    };
  }, [loadSources]);

  const handleError = exception => {
    if (exception.name === 'AbortError') return;
    setError(`${exception.message}${exception.traceId ? `（请求编号：${exception.traceId}）` : ''}`);
  };

  const search = async (event, next = false) => {
    event?.preventDefault();
    if (busy) return;
    const from = Date.parse(startAt), to = Date.parse(endAt);
    if (!next && (!sourceId || !Number.isFinite(from) || !Number.isFinite(to) || from >= to)) {
      setError('请选择摄像头，并填写开始时间早于结束时间的查询范围');
      return;
    }
    const body = next ? { ...query, cursor: result.next_cursor } : {
      source_id: sourceId, start_at: new Date(from).toISOString(), end_at: new Date(to).toISOString(),
      result_type: 'detection.frame', page_size: 50,
    };
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setBusy(true);
    setError('');
    if (!next) setResult(null);
    try {
      const data = await businessApi.results(body, controller.signal);
      setQuery(body);
      setResult(previous => next ? { ...data, items: [...(previous?.items || []), ...(data.items || [])] } : data);
    } catch (exception) { handleError(exception); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };

  const openFrame = async frame => {
    setError('');
    setBusy(true);
    try {
      let asset = result?.recordings?.find(item => item.asset_id === frame.media_asset_id);
      if (!asset) {
        const data = await businessApi.assets({ asset_ids: [frame.media_asset_id], page_size: 1 });
        asset = data.items?.[0];
      }
      if (!asset || asset.state !== 'available') throw new Error('该帧对应的录像尚未就绪或已过期');
      setPlayback({ ...asset, offset_ms: frame.media_pts_ms });
    } catch (exception) { handleError(exception); }
    finally { setBusy(false); }
  };

  const trapFocus = event => {
    if (event.key === 'Escape' && !playback) { onClose(); return; }
    if (event.key !== 'Tab') return;
    const controls = [...panelRef.current.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex="0"]')];
    const first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === panelRef.current)) {
      event.preventDefault(); last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault(); first?.focus();
    }
  };

  return ReactDOM.createPortal(
    <div className={styles.backdrop} onClick={onClose}>
      <section ref={panelRef} className={styles.panel} role="dialog" aria-modal="true" aria-labelledby="history-title"
        tabIndex={-1} onKeyDown={trapFocus} onClick={event => event.stopPropagation()}>
        <header className={styles.header}>
          <h2 id="history-title">历史结果与录像</h2>
          <div><button type="button" aria-label="关闭历史查询" onClick={onClose}>关闭</button></div>
        </header>
        {error && <p className={styles.error} role="alert">{error}</p>}
        {checking ? <p role="status">正在加载摄像头…</p> : (
          <>
            <BusinessObjects sources={sources} onError={handleError} />
            <h3>按摄像头回看</h3>
            <form className={styles.query} onSubmit={event => search(event)}>
              <label>摄像头<select required value={sourceId} onChange={event => setSourceId(event.target.value)}>
                <option value="">选择摄像头</option>
                {sources.map(source => <option key={source.source_id} value={source.source_id}>{source.display_name || source.camera_code}</option>)}
              </select></label>
              <label>开始时间<input type="datetime-local" step="1" required value={startAt} onChange={event => setStartAt(event.target.value)} /></label>
              <label>结束时间<input type="datetime-local" step="1" required value={endAt} onChange={event => setEndAt(event.target.value)} /></label>
              <button type="submit" disabled={busy || !sourceId}>{busy ? '查询中…' : '查询'}</button>
            </form>
            {!sources.length && <p>暂无可查询的视频来源。</p>}
            {result && <div className={styles.results}>
              <p>查询范围：{displayTime(query.start_at)} 至 {displayTime(query.end_at)}（不含结束时刻），已加载 {result.items?.length || 0} 个算法处理帧。</p>
              {!!result.coverage?.gaps?.length && <div className={styles.gaps}>
                <strong>此范围存在数据缺口</strong>
                <ul>{result.coverage.gaps.map((gap, index) => <li key={index}>{gap.stage || gap.scope || '处理'}：{displayTime(gap.start_at)} 至 {displayTime(gap.end_at)} · {gap.reason || gap.reason_code || gap.state || '未完成'}</li>)}</ul>
              </div>}
              <h3>录像分段</h3>
              {!result.recordings?.length ? <p>此范围没有录像分段。</p> : <ul className={styles.recordings}>
                {result.recordings.map(asset => <li key={asset.asset_id}>
                  <span>{displayTime(asset.start_at)} — {displayTime(asset.end_at)} · {asset.state === 'available' ? '可回放' : asset.state === 'preparing' ? '正在录制' : '暂不可用'}</span>
                  <button type="button" disabled={asset.state !== 'available'} onClick={() => setPlayback({ ...asset, offset_ms: 0 })}>播放</button>
                </li>)}
              </ul>}
              <h3>逐帧结果</h3>
              {!result.items?.length ? <p>此范围没有已保存的处理帧；空目标帧也会在下表独立显示。</p> : <div className={styles.tableScroll}>
                <table><thead><tr><th>发生时间</th><th>帧号</th><th>目标 / 预测</th><th>录像定位</th></tr></thead>
                  <tbody>{result.items.map(frame => <tr key={frame.result_id}>
                    <td>{displayTime(frame.occurred_at)}</td><td>{frame.frame_seq}</td>
                    <td>{frame.targets?.length || 0} / {frame.targets?.filter(target => target.is_prediction).length || 0}</td>
                    <td>{frame.media_asset_id && Number.isFinite(frame.media_pts_ms) ?
                      <button type="button" disabled={busy} onClick={() => openFrame(frame)}>从 {(frame.media_pts_ms / 1000).toFixed(3)} 秒回看</button> : '录像尚未完成定位'}</td>
                  </tr>)}</tbody>
                </table>
              </div>}
              {result.has_more && <button type="button" disabled={busy} onClick={() => search(null, true)}>加载更多帧</button>}
            </div>}
          </>
        )}
        <VideoModal visible={Boolean(playback)} playback={playback} title="历史录像与检测框" time={displayTime(playback?.start_at)} onClose={() => setPlayback(null)} />
      </section>
    </div>, document.body,
  );
}

export default function BusinessPanel() {
  const [visible, setVisible] = React.useState(false);
  return <>
    <button className={styles.launcher} type="button" onClick={() => setVisible(true)}>历史结果与录像</button>
    {visible && <HistoryPanel onClose={() => setVisible(false)} />}
  </>;
}
