import React, { useEffect, useRef, useState } from 'react';
import { businessApi } from '../../../../services/businessApi';
import { joyAlarmCards, queryJoyAlarms, restartJoyReview, queryBehaviorStatus, queryReviewHistory } from '../../../../services/joyaiAlarms';
import VideoModal from '../../../VideoModal/VideoModal';
import styles from './RealTimeAlarm.module.css';

export default function JoyAlarmCards() {
  const [reports, setReports] = useState([]);
  const [monitor, setMonitor] = useState(null);
  const [status, setStatus] = useState('正在读取异常监控状态…');
  const [error, setError] = useState('');
  const [modal, setModal] = useState(null);
  const [history, setHistory] = useState([]);
  const [submitting, setSubmitting] = useState(null);
  const submittingRef = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    let timer;
    async function refreshReports() {
      try {
        setReports(await queryJoyAlarms(controller.signal));
        setError('');
      } catch (e) {
        if (e.name !== 'AbortError') setError('异常告警查询失败，请稍后重试');
      }
    }
    async function refreshMonitor() {
      try {
        const data = await queryBehaviorStatus(controller.signal);
        setMonitor(data);
        const cameras = Object.values(data.cameras || {});
        const active = cameras.filter(camera => camera.state === 'observing'
          && Date.now() / 1000 - camera.last_observed_at < 60).length;
        const review = { stopped: '按需待命', starting: '正在加载', ready: '已就绪',
          reviewing: '正在复核', releasing: '正在释放资源', error: '等待重试' }[data.reviewer?.state] || '等待状态';
        setStatus(data.status === 'running' ? `异常预警模型：${active}/4 路正在观察 · ${data.pending_reviews} 条等待复核 · 复核模型：${review}`
          : data.status === 'stopping' ? '异常预警模型：正在停止' : '异常预警模型：未启动');
      } catch (e) {
        if (e.name !== 'AbortError') setStatus('异常预警模型：服务未连接，事件状态暂未更新');
      }
    }
    async function refresh() {
      await Promise.allSettled([refreshReports(), refreshMonitor()]);
      if (!controller.signal.aborted) timer = setTimeout(refresh, 5000);
    }
    refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, []);

  async function open(row) {
    try {
      const ticket = await businessApi.playbackTicket(row.report_json.video_asset_id);
      setModal({ row, url: ticket.url });
      setHistory(await queryReviewHistory(row.subject_id));
      setError('');
    } catch (e) { setError('视频暂不可读或已过期，请稍后重试'); }
  }
  async function restart(row) {
    if (submittingRef.current) return;
    submittingRef.current = true;
    setSubmitting(row.alarm_id);
    try {
      await restartJoyReview(row.report_id);
      setMonitor(await queryBehaviorStatus());
      setError('');
    } catch (e) { setError(e.message); }
    finally { submittingRef.current = false; setSubmitting(null); }
  }
  const time = value => new Date(value).toLocaleString('zh-CN', { hour12: false });
  const rows = joyAlarmCards(reports, monitor);
  const labels = { suspected: '疑似异常', confirmed: '已确认异常', excluded: '已排除', uncertain: '复核未确认' };
  const colors = { suspected: styles.joySuspected, confirmed: styles.joyConfirmed,
    excluded: styles.joyExcluded, uncertain: styles.joySuspected };
  const selected = modal && (rows.find(row => row.alarm_id === modal.row.alarm_id) || modal.row);
  return <>
    <div className={styles.joyStatus} role="status">{status}{error && <span role="alert"> · {error}</span>}</div>
    <div className={styles.joyCards}>
      {rows.map(row => {
        const report = row.report_json;
        const playable = Boolean(report.video_asset_id);
        return <article className={`${styles.joyCard} ${colors[row.alarm_state]}`} key={row.alarm_id}>
          <button className={styles.joyPlayback}
          onClick={() => playable && open(row)} aria-disabled={!playable}
          aria-label={`${labels[row.alarm_state]} · ${report.event_type === 'fight' ? '打架' : '跌倒'}，${report.camera_name}，${row.review_stage || '复核完成'}，${playable ? '点击播放视频与分析报告' : '视频准备中'}`}>
          <span className={styles.joyBadge}>{labels[row.alarm_state]} · {report.event_type === 'fight' ? '打架' : '跌倒'}</span>
          <span className={styles.joyStage}>{row.review_stage || (row.alarm_state === 'uncertain' ? '证据不足或模型判断不一致' : '复核完成')}</span>
          {report.thumbnail_asset_id && <img className={styles.joyThumbnail}
            src={`/api/v1/business/assets/${encodeURIComponent(report.thumbnail_asset_id)}/content`} alt="异常片段截图" />}
          <strong>{report.location || report.camera_name}</strong>
          <time>{time(report.occurred_at)}</time>
          <span className={styles.joySummary} title={report.processing_error || report.review?.reason}>
            {report.processing_error || report.review?.reason}</span>
          <span>{playable ? `▶ 播放约 ${Math.round(report.clip_seconds)} 秒视频 · 查看${row.alarm_state === 'suspected' ? '进度' : '报告'}` : '视频准备中，完成后可播放'}</span>
          </button>
          <button type="button" className={styles.joyReviewButton}
            disabled={row.alarm_state === 'suspected' || !row.report_id || submitting !== null}
            onClick={() => restart(row)}
            aria-label={`保留 JoyAI 判断，仅重新运行 Qwen，${report.camera_name}，${report.event_type === 'fight' ? '打架' : '跌倒'}`}>
            {submitting === row.alarm_id ? '正在提交…' : row.alarm_state === 'suspected' ? '复核处理中' : '保留 JoyAI 判断，仅重新运行 Qwen'}
          </button>
        </article>;
      })}
      {!rows.length && <div className={styles.joyEmpty}>暂无疑似或已确认的异常事件</div>}
    </div>
    {modal && <VideoModal visible url={modal.url} title={`${labels[selected.alarm_state]} · ${selected.report_json.event_type === 'fight' ? '打架' : '跌倒'}`}
      time={time(selected.report_json.occurred_at)} onClose={() => setModal(null)}
      report={<div className={styles.joyReport}>
        <p>人工复核保留原 JoyAI 判断，仅重新运行 Qwen；历次报告均保留。</p>
        <details><summary>历史复核报告（{history.length}）</summary>{history.map(item => <article key={item.report_id}><time>{time(item.processed_at)}</time><pre>{item.report_text}</pre></article>)}</details>
        <p>地点：{selected.report_json.location || `${selected.report_json.camera_name}（尚未配置具体地点）`}</p>
        <p>时间：{time(selected.report_json.occurred_at)} · {labels[selected.alarm_state]}</p>
        <h3>{selected.alarm_state === 'suspected' ? selected.review_stage : '大模型分析报告'}</h3>
        <p>{selected.report_json.processing_error || selected.report_json.review?.reason}</p>
        {selected.report_json.review?.report && <>
          <ol>{selected.report_json.review.report.observations?.map((item, i) => <li key={i}>{item}</li>)}</ol>
          <p>正常活动解释：{selected.report_json.review.report.normalExplanation}</p>
          <p>判断限制：{selected.report_json.review.report.limitations || '未报告额外限制'}</p>
        </>}
      </div>} />}
  </>;
}
