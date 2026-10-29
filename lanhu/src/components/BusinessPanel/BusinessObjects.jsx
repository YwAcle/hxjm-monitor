import React from 'react';
import { businessApi } from '../../services/businessApi';
import VideoModal from '../VideoModal/VideoModal';
import styles from './BusinessPanel.module.css';

// getRandomValues also works when a LAN deployment uses HTTP.
function id() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = [...bytes].map(value => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
const time = value => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—';
const stateName = { pending: '等待处理', running: '处理中', waiting_input: '请选择图中目标', succeeded: '已完成', partial: '部分完成', failed: '处理失败', expired: '已过期', cancelled: '已取消' };

export default function BusinessObjects({ sources, onError }) {
  const [tab, setTab] = React.useState('search');
  const [file, setFile] = React.useState(null);
  const [preview, setPreview] = React.useState('');
  const [name, setName] = React.useState('');
  const [employee, setEmployee] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [notice, setNotice] = React.useState('');
  const [query, setQuery] = React.useState(null);
  const [identities, setIdentities] = React.useState([]);
  const [activities, setActivities] = React.useState([]);
  const [reports, setReports] = React.useState({});
  const [playback, setPlayback] = React.useState(null);
  const [playbackAssets, setPlaybackAssets] = React.useState([]);
  const logicalRequest = React.useRef(null);
  const selectionRequest = React.useRef(null);
  const sourceNames = Object.fromEntries(sources.map(source => [source.source_id, source.display_name || source.camera_code]));

  React.useEffect(() => {
    if (!file) { setPreview(''); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  React.useEffect(() => {
    if (!query || !['pending', 'running'].includes(query.state)) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try { setQuery(await businessApi.query(query.query_id || query.id, controller.signal)); }
      catch (error) { if (error.name !== 'AbortError') onError(error); }
    }, 1500);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, onError]);

  const loadIdentities = async () => {
    setBusy(true);
    try { setIdentities((await businessApi.identities({ limit: 100 })).items || []); }
    catch (error) { onError(error); }
    finally { setBusy(false); }
  };

  const submit = async event => {
    event.preventDefault();
    if (!file || busy) return;
    setBusy(true); setNotice('');
    if (!logicalRequest.current) logicalRequest.current = { asset: id(), upload: id(), business: id(), query: id(), identity: id(), sample: id() };
    const keys = logicalRequest.current;
    try {
      const upload = await businessApi.uploadImage(file, { request_id: keys.upload, asset_id: keys.asset, purpose: tab === 'enrollment' ? 'enrollment' : 'query' });
      if (tab === 'enrollment') {
        const registered = await businessApi.registerIdentity({ request_id: keys.business, identity_id: keys.identity, object_type: 'person',
          display_name: name.trim(), ...(employee.trim() ? { employee_id: employee.trim() } : {}),
          enrollment_assets: [{ asset_id: upload.asset_id, sample_id: keys.sample }] });
        setNotice(`已登记 ${registered.display_name || name}，照片特征正在后台处理。`);
        logicalRequest.current = null;
        await loadIdentities();
      } else {
        const created = await businessApi.createQuery({ request_id: keys.business, query_id: keys.query, query_kind: 'image', object_type: 'person', input_asset_id: upload.asset_id });
        setQuery({ ...created, query_id: created.query_id || keys.query });
      }
    } catch (error) { onError(error); }
    finally { setBusy(false); }
  };

  const choose = async candidate => {
    if (busy) return;
    setBusy(true);
    try {
      const queryId = query.query_id || query.id;
      const key = JSON.stringify([queryId, query.revision, candidate.candidate_id]);
      if (selectionRequest.current?.key !== key) selectionRequest.current = { key, request_id: id() };
      const selected = await businessApi.selectCandidate({ request_id: selectionRequest.current.request_id, query_id: queryId, candidate_id: candidate.candidate_id, expected_revision: query.revision });
      setQuery(previous => ({ ...previous, ...selected, query_id: queryId }));
      setQuery(await businessApi.query(queryId));
    } catch (error) { onError(error); }
    finally { setBusy(false); }
  };

  const showActivities = async identityId => {
    setBusy(true);
    try { setActivities((await businessApi.activities({ identity_id: identityId, limit: 100 })).items || []); setTab('activities'); }
    catch (error) { onError(error); }
    finally { setBusy(false); }
  };
  const loadReports = async activity => {
    setBusy(true);
    try {
      const data = await businessApi.reports({ subject_kind: 'activity', subject_id: activity.activity_id, limit: 100 });
      setReports(previous => ({ ...previous, [activity.activity_id]: data.items || [] }));
    } catch (error) { onError(error); }
    finally { setBusy(false); }
  };
  const playTrack = async track => {
    setBusy(true);
    try {
      const from = new Date(track.first_observed_at || track.start_ts), to = new Date(track.last_observed_at || track.end_ts);
      const data = await businessApi.resolve({ request_id: id(), purpose: 'playback', source_id: track.source_id, start_at: from.toISOString(), end_at: new Date(Math.max(to.getTime(), from.getTime() + 1)).toISOString() });
      const segments = data.items?.filter(item => item.state === 'available') || [];
      const asset = segments[0];
      if (!asset) throw new Error('对应录像尚未就绪或已过期');
      setPlaybackAssets(segments);
      setPlayback({ ...asset, offset_ms: Math.max(0, from.getTime() - Date.parse(asset.start_at)) });
    } catch (error) { onError(error); }
    finally { setBusy(false); }
  };

  return <section className={styles.objects}>
    <nav className={styles.tabs} aria-label="人员业务">
      {[['search', '以图查人'], ['enrollment', '登记人员'], ['identities', '人员与活动']].map(([value, label]) =>
        <button key={value} type="button" aria-pressed={tab === value} onClick={() => { setTab(value); logicalRequest.current = null; setNotice(''); if (value === 'identities') loadIdentities(); }}>{label}</button>)}
    </nav>
    {['search', 'enrollment'].includes(tab) && <form className={styles.objectForm} onSubmit={submit}>
      <label>人员图片<input type="file" accept="image/jpeg,image/png" required onChange={event => { setFile(event.target.files?.[0] || null); setQuery(null); logicalRequest.current = null; }} /></label>
      {preview && <div className={styles.queryPreview}><img className={styles.queryImage} src={preview} alt="所选人员图片" />
        {tab === 'search' && query?.state === 'waiting_input' && query.candidates?.map(candidate => {
          const box = candidate.bbox_json?.xyxy;
          if (!Array.isArray(box) || box.length !== 4) return null;
          return <button className={styles.candidateBox} key={candidate.candidate_id} type="button" disabled={busy}
            aria-label={`选择目标 ${candidate.candidate_id}`} onClick={() => choose(candidate)}
            style={{ left: `${box[0] * 100}%`, top: `${box[1] * 100}%`, width: `${(box[2] - box[0]) * 100}%`, height: `${(box[3] - box[1]) * 100}%` }}>
            <span>{candidate.candidate_id}</span></button>;
        })}</div>}
      {tab === 'enrollment' && <><label>姓名<input required value={name} onChange={event => { setName(event.target.value); logicalRequest.current = null; }} /></label>
        <label>人员编号（可选）<input value={employee} onChange={event => { setEmployee(event.target.value); logicalRequest.current = null; }} /></label></>}
      <button type="submit" disabled={busy || !file}>{busy ? '正在提交…' : tab === 'enrollment' ? '登记' : '查找相似人员'}</button>
      <p>{tab === 'enrollment' ? '正式登记资料持续保存，照片特征由后台生成。' : '同时检索登记图库和可用历史人员记录；查询素材最长保留七天。'}</p>
    </form>}
    {notice && <p role="status">{notice}</p>}
    {tab === 'search' && query && <div>
      <p role="status">查询状态：{stateName[query.state] || query.state} · 查询编号：{query.query_id || query.id}</p>
      {query.state === 'waiting_input' && <div className={styles.candidates}>{query.candidates?.map(candidate =>
        <button type="button" key={candidate.candidate_id} disabled={busy} onClick={() => choose(candidate)}>选择目标 {candidate.candidate_id}</button>)}</div>}
      {query.state === 'succeeded' && !query.hits?.length && <p>当前可检索数据中未找到符合条件的人员。</p>}
      {!!query.hits?.length && <table><thead><tr><th>结果</th><th>范围</th><th>相似度</th><th>查看</th></tr></thead><tbody>{query.hits.map(hit =>
        <tr key={hit.hit_id}><td>{hit.rank_no}</td><td>{hit.hit_kind === 'gallery' ? '登记图库' : '历史出现记录'}</td><td>{Number(hit.score).toFixed(3)}</td>
          <td>{hit.identity_id ? <button type="button" disabled={busy} onClick={() => showActivities(hit.identity_id)}>查看活动与录像</button> : '身份处理中'}</td></tr>)}</tbody></table>}
    </div>}
    {tab === 'identities' && <div><button type="button" disabled={busy} onClick={loadIdentities}>刷新人员列表</button>
      <table><thead><tr><th>人员</th><th>类型</th><th>最近出现</th><th>活动</th></tr></thead><tbody>{identities.map(person => <tr key={person.identity_id}>
        <td>{person.display_name || `临时人员 ${person.display_no}`}</td><td>{person.identity_kind === 'registered' ? '正式登记' : '临时身份'}</td><td>{time(person.last_seen_at)}</td>
        <td><button type="button" disabled={busy} onClick={() => showActivities(person.identity_id)}>查看</button></td></tr>)}</tbody></table>
      {!identities.length && <p>暂无可访问的人员记录。</p>}</div>}
    {tab === 'activities' && <div><h3>人员活动路线</h3>{!activities.length && <p>暂无可访问的历史活动。</p>}{activities.map(activity => <article className={styles.activity} key={activity.activity_id}>
      <h4>{time(activity.start_ts)} — {time(activity.end_ts)} · {activity.state === 'open' ? '活动进行中' : activity.state === 'interrupted' ? '观测中断' : '活动已结束'}</h4>
      <table><thead><tr><th>摄像头</th><th>首次出现</th><th>最后出现</th><th>录像</th></tr></thead><tbody>{activity.tracks?.map(track => <tr key={track.tracklet_id}>
        <td>{sourceNames[track.source_id] || '视频来源'}</td><td>{time(track.first_observed_at)}</td><td>{time(track.last_observed_at)}</td>
        <td><button type="button" disabled={busy} onClick={() => playTrack(track)}>回放</button></td></tr>)}</tbody></table>
      <button type="button" disabled={busy} onClick={() => loadReports(activity)}>查看最新报告</button>
      {reports[activity.activity_id]?.map(report => <div key={report.report_id}><p>报告修订 {report.revision} · {report.completeness === 'complete' ? '覆盖完整' : '部分覆盖'}</p><p className={styles.reportText}>{report.report_text || report.report_json?.summary || '活动路线及录像见上表。'}</p></div>)}
      {reports[activity.activity_id]?.length === 0 && <p>该活动尚未生成报告。</p>}
    </article>)}</div>}
    {playbackAssets.length > 1 && <div><h4>本次活动的录像分段</h4>{playbackAssets.map((asset, index) =>
      <button type="button" key={asset.asset_id} onClick={() => setPlayback(asset)}>第 {index + 1} 段：{time(asset.start_at)}</button>)}</div>}
    <VideoModal visible={Boolean(playback)} playback={playback} title="活动录像" onClose={() => setPlayback(null)} />
  </section>;
}
