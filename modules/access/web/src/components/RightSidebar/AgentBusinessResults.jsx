import React, { useState } from 'react';
import { agentResultItems, agentResultTitle } from '../../services/agentResults';
import { getRegistrationImageSrc } from '../../services/pedestrianSearch';
import VideoModal from '../VideoModal/VideoModal';
import styles from './PedestrianSearchResult.module.css';

const list = value => Array.isArray(value) ? value : [];
const time = value => typeof value === 'string' && Number.isFinite(Date.parse(value))
  ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : null;

export default function AgentBusinessResults({ results = [], queryImage }) {
  const [playback, setPlayback] = useState(null);
  return <>
    {results.map((result, resultIndex) => {
      const title = agentResultTitle(result);
      if (!title) return null;
      const items = agentResultItems(result);
      const coverage = result.coverage_json || result.coverage;
      const image = result.type === 'super_resolution' ? getRegistrationImageSrc(result.image_base64) : null;
      const pending = result.type === 'person_query' && result.state === 'waiting_input';
      return <section className={styles.result} key={resultIndex} aria-label={title}>
        <h4 className={styles.title}>{title}</h4>
        {result.message && <p role="status">{String(result.message)}</p>}
        {typeof result.summary === 'string' && <p>{result.summary}</p>}
        {['failed', 'cancelled', 'expired', 'waiting_input'].includes(result.state) && !pending && <p>{({ failed: '查询失败', cancelled: '查询已取消', expired: '查询已到期', waiting_input: '等待补充输入' })[result.state]}</p>}
        {result.type === 'person_query' && ['pending', 'running'].includes(result.state) && <p>正在处理图片查询。</p>}
        {pending && <p>按下方顺序在聊天中回复“选择第二个”等指令。</p>}
        {pending && queryImage && <div style={{ position: 'relative', width: '100%' }}>
          <img src={getRegistrationImageSrc(queryImage)} alt="本次查询原图" style={{ width: '100%', display: 'block' }} />
          {items.map((item, index) => {
            const box = item.bbox_json?.xyxy;
            if (!Array.isArray(box) || box.length !== 4 || !box.every(Number.isFinite)
                || box.some(value => value < 0 || value > 1) || box[2] <= box[0] || box[3] <= box[1]) return null;
            return <span key={index} style={{ position: 'absolute', boxSizing: 'border-box', border: '2px solid #56e9b1',
              left: `${box[0] * 100}%`, top: `${box[1] * 100}%`, width: `${(box[2] - box[0]) * 100}%`, height: `${(box[3] - box[1]) * 100}%` }}>
              <span style={{ background: '#074d3b', color: 'white' }}>{index + 1}</span>
            </span>;
          })}
        </div>}
        {image && <img src={image} alt="图片放大结果" style={{ maxWidth: '100%' }} />}
        {result.type === 'super_resolution' && list(result.result_size).length === 2 && <p>{result.result_size.join('×')}{result.scale ? ` · ${result.scale}倍` : ''}</p>}
        {result.type === 'time_parse' && <p>{time(result.start_at)} 至 {time(result.end_at)}{result.timezone ? `（${result.timezone}）` : ''}</p>}
        {result.selected_hit && <p>已选择：{result.selected_hit.display_name || result.selected_hit.identity_id || '查询命中'}</p>}
        <ol className={styles.candidates}>
          {items.map((item, index) => {
            const start = item.first_observed_at || item.event_start_at || item.start_at || item.start_ts;
            const end = item.last_observed_at || item.event_end_at || item.end_at || item.end_ts;
            const recordings = [
              ...(item.asset_id ? [item] : []), ...list(item.recordings),
              ...list(item.evidence).filter(evidence => evidence.asset_id),
              ...list(item.report_json?.route).flatMap(track => list(track.recordings).map(asset => ({ ...asset, source_id: track.source_id, stream_session_id: track.stream_session_id,
                offset_ms: asset.offset_ms ?? asset.first_media_pts_ms ?? 0 }))),
            ];
            const gaps = list(item.coverage_json?.gaps || item.coverage?.gaps);
            return <li className={styles.candidate} key={index}><div className={styles.details}>
              <strong>{index + 1}. {item.display_name || item.name || item.title || item.source_name || item.event_type || item.report_type || (pending ? `图片目标 ${index + 1}` : `记录 ${index + 1}`)}</strong>
              {item.source_name && <span>来源：{item.source_name}</span>}
              {start && <span>{time(start)}{end ? ` 至 ${time(end)}` : '（尚未结束）'}</span>}
              {item.event_type && <span>类型：{item.event_type}</span>}
              {item.conclusion_json?.description && <span>{String(item.conclusion_json.description)}</span>}
              {item.report_text && <p>{String(item.report_text)}</p>}
              {list(item.report_json?.route).map((track, routeIndex) => <span key={routeIndex}>路线 {routeIndex + 1}：{track.source_name || '视频来源'}{time(track.first_observed_at || track.start_at || track.start_ts) ? ` · ${time(track.first_observed_at || track.start_at || track.start_ts)}` : ''}{time(track.last_observed_at || track.end_at || track.end_ts) ? ` 至 ${time(track.last_observed_at || track.end_at || track.end_ts)}` : ''}</span>)}
              {item.revision != null && <span>修订：{item.revision}</span>}
              {item.completeness === 'partial' && <span>报告覆盖不完整</span>}
              {typeof item.score === 'number' && <span>相似度／评分：{item.score}（{item.score_metric || '按检索返回口径'}）</span>}
              {item.identity_id && <span>人员：{item.identity_id}</span>}
              {gaps.length > 0 && <span>存在 {gaps.length} 处处理缺口</span>}
              {recordings.map((asset, segmentIndex) => asset.asset_id && (!asset.state || asset.state === 'available') ?
                <button key={segmentIndex} type="button" className={styles.selectionButton}
                  onClick={() => setPlayback({ ...asset, offset_ms: asset.offset_ms ?? asset.first_media_pts_ms ?? 0 })}>播放分段 {segmentIndex + 1}</button> : null)}
            </div></li>;
          })}
        </ol>
        {items.length === 0 && ['person_directory', 'person_tracklets', 'report_search', 'event_search', 'person_activities'].includes(result.type) && <p>当前筛选下未返回记录。</p>}
        {result.has_more && <p>还有后续记录，可在对话中继续查询。</p>}
        {result.gallery_truncated && <p>本次查询范围已截断。</p>}
        {result.completeness === 'partial' && <p>当前结果覆盖不完整。</p>}
        {list(coverage?.gaps).length > 0 && <p>存在 {coverage.gaps.length} 处处理缺口。</p>}
        {list(result.gaps).length > 0 && <p>存在 {result.gaps.length} 处录像缺口。</p>}
        {list(result.unresolved_tracks).length > 0 && <p>部分轨迹暂不能定位录像。</p>}
        {Array.isArray(result.scope?.source_ids) && <p>来源范围：{result.scope.source_ids.length} 路</p>}
        {result.scope?.start_at && <p>查询范围：{time(result.scope.start_at)} 至 {time(result.scope.end_at)}</p>}
      </section>;
    })}
    <VideoModal visible={!!playback} playback={playback} title="录像回放" onClose={() => setPlayback(null)} />
  </>;
}
