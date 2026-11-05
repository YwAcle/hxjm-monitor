import React, { useEffect, useId, useState } from 'react';
import { businessApi } from '../../services/businessApi';
import {
  buildPlaybackQuery,
  createRequestId,
  formatOccurrenceTimeRange,
  getPedestrianSearchStatus,
  getRegistrationImageSrc,
  pickPlaybackAsset,
  playbackOffsetMs,
} from '../../services/pedestrianSearch';
import VideoModal from '../VideoModal/VideoModal';
import styles from './PedestrianSearchResult.module.css';

function CandidatePhoto({ image, alt, placeholder = '暂无有效照片', assetId = null }) {
  const [failed, setFailed] = useState(false);
  const [ticketUrl, setTicketUrl] = useState(null);
  const [ticketFailed, setTicketFailed] = useState(false);

  // 历史轨迹裁剪图优先使用 Agent 内嵌的 base64；没有时才用短期 playback ticket 换取同源图片地址。
  useEffect(() => {
    if (!assetId || getRegistrationImageSrc(image)) return undefined;
    const controller = new AbortController();
    let active = true;
    setTicketUrl(null);
    setTicketFailed(false);
    businessApi.playbackTicket(assetId, controller.signal)
      .then(ticket => { if (active) setTicketUrl(ticket.url); })
      .catch(error => { if (active && error?.name !== 'AbortError') setTicketFailed(true); });
    return () => { active = false; controller.abort(); };
  }, [assetId, image]);

  const src = getRegistrationImageSrc(image) || ticketUrl;
  const pending = !src && assetId && !ticketFailed;
  return src && !failed ? (
    <img className={styles.photo} src={src} alt={alt}
      loading="lazy" onError={() => setFailed(true)} />
  ) : (
    <span className={styles.photoPlaceholder}>
      {image || !assetId ? placeholder : ticketFailed ? '轨迹图加载失败' : pending ? '轨迹图加载中…' : placeholder}
    </span>
  );
}

function OccurrencePanel({ occurrences }) {
  const [expanded, setExpanded] = useState(false);
  const [loadingTrackletId, setLoadingTrackletId] = useState(null);
  const [videoError, setVideoError] = useState(null);
  const [playback, setPlayback] = useState(null);
  const panelId = useId();

  // 轨迹只保存来源和时间，录像资产由业务后端按时间区间解析后再换播放票据。
  const openVideo = async (item, trackletId) => {
    const query = buildPlaybackQuery(item, createRequestId());
    if (!query) {
      setVideoError('该轨迹缺少来源或时间信息，无法定位录像');
      return;
    }
    setVideoError(null);
    setLoadingTrackletId(trackletId);
    try {
      const response = await businessApi.resolve(query);
      const asset = pickPlaybackAsset(response);
      if (!asset) throw new Error('该时间段没有可访问的录像（可能未录制、仍在生成或存储不可用）');
      setPlayback({
        ...asset,
        source_id: query.source_id,
        offset_ms: playbackOffsetMs(asset, item.start_at),
        occurrence_start_at: item.start_at,
        occurrence_end_at: item.end_at,
      });
    } catch (error) {
      setVideoError(error?.message || '录像加载失败，请稍后重试');
    } finally {
      setLoadingTrackletId(null);
    }
  };

  if (occurrences.length === 0) return null;
  return (
    <div className={styles.occurrenceSection}>
      <button type="button" className={styles.toggleButton}
        aria-expanded={expanded} aria-controls={panelId}
        onClick={() => setExpanded(value => !value)}>
        {expanded ? '收起轨迹信息' : '查看轨迹信息'}
      </button>
      {expanded && (
        <>
          <ul className={styles.occurrences} id={panelId}>
            {occurrences.map((item, itemIndex) => {
              const trackletId = item.tracklet_id ?? String(itemIndex);
              const loading = loadingTrackletId === trackletId;
              return (
                <li key={trackletId}>
                  出现时间：{formatOccurrenceTimeRange(item.start_at, item.end_at)}
                  {' · '}{item.camera || '未知摄像头'}
                  <button type="button" className={styles.videoButton}
                    disabled={loadingTrackletId !== null}
                    onClick={() => openVideo(item, trackletId)}>
                    {loading ? '加载中…' : '查看视频'}
                  </button>
                </li>
              );
            })}
          </ul>
          {videoError && <p className={styles.videoError} role="status">{videoError}</p>}
        </>
      )}
      <VideoModal visible={Boolean(playback)} playback={playback} title="轨迹录像回放"
        time={playback ? formatOccurrenceTimeRange(playback.occurrence_start_at, playback.occurrence_end_at) : ''}
        onClose={() => setPlayback(null)} />
    </div>
  );
}

export default function PedestrianSearchResult({ result, onSelect, onCancel, disabled = false, inactive = false }) {
  const candidates = Array.isArray(result.candidates)
    ? result.candidates.filter(candidate => candidate && typeof candidate === 'object')
    : [];
  const statusText = getPedestrianSearchStatus(result);
  const history = result.scope === 'identity_history';
  const unavailable = ['not_configured', 'no_compatible_features', 'missing_image', 'invalid_image',
    'no_person', 'selection_expired', 'cancelled', 'feature_space_missing',
    'feature_space_incompatible', 'empty_history', 'no_identity_candidates']
    .includes(result.status);

  if (result.type === 'pedestrian_selection') {
    const pending = result.status === 'selection_required';
    return (
      <section className={styles.result} aria-label="截图行人选择">
        <h4 className={styles.title}>选择截图中的行人</h4>
        <p className={styles.note} role="status">
          {pending
            ? '点击下方编号，或在聊天中回复“选择2”。编号仅对应本次截图，不代表人员身份。'
            : statusText}
        </p>
        {pending && (
          <>
            <ol className={styles.candidates}>
              {candidates.map((candidate, index) => {
                const validId = typeof candidate.candidate_id === 'string' && /^\d+$/.test(candidate.candidate_id);
                const bbox = candidate.bbox;
                return (
                  <li className={styles.candidate} key={`${candidate.candidate_id ?? 'candidate'}-${index}`}>
                    <CandidatePhoto image={candidate.image_base64} alt={`截图行人 ${candidate.candidate_id ?? index + 1} 的裁剪预览`} />
                    <div className={styles.details}>
                      <strong>截图行人 {candidate.candidate_id ?? index + 1}</strong>
                      {Array.isArray(bbox) && bbox.length === 4 && bbox.every(Number.isInteger) && (
                        <span>原图坐标：[{bbox.join(', ')}]</span>
                      )}
                      <button type="button" className={styles.selectionButton}
                        disabled={disabled || inactive || !validId || !onSelect}
                        onClick={() => onSelect(candidate.candidate_id)}>
                        选择{candidate.candidate_id ?? index + 1}
                      </button>
                    </div>
                  </li>
                );
              })}
            </ol>
            {inactive ? (
              <p className={styles.note}>此截图选择已结束，请使用最新截图的候选。</p>
            ) : (
              <>
                <p className={styles.note}>选择有效期为5分钟；上传新截图会替换旧选择。</p>
                <button type="button" className={styles.selectionButton}
                  disabled={disabled || !onCancel} onClick={onCancel}>取消选择</button>
              </>
            )}
          </>
        )}
      </section>
    );
  }

  return (
    <section className={styles.result} aria-label={history ? '历史轨迹身份候选' : '登记库行人检索候选'}>
      <h4 className={styles.title}>{history ? '历史轨迹候选' : '登记库候选'}</h4>
      <p className={styles.note}>
        {history
          ? '候选来自已入库的真实轨迹特征；临时身份不代表身份确认，出现记录只覆盖当前保留期，不代表实时位置。'
          : '姓名来自候选登记档案，不代表身份确认；登记照片不代表历史出现或实时位置，衣着可能已过时。'}
      </p>
      {(Number.isInteger(result.scanned_count) || Number.isInteger(result.searched_count)
        || Number.isInteger(result.skipped_count)) && (
        <p className={styles.note}>
          {Number.isInteger(result.scanned_count ?? result.searched_count)
            && `本次已检查 ${result.scanned_count ?? result.searched_count} 条`}
          {Number.isInteger(result.scanned_count ?? result.searched_count)
            && Number.isInteger(result.skipped_count) && ' · '}
          {Number.isInteger(result.skipped_count) && `跳过 ${result.skipped_count} 条无效记录`}
        </p>
      )}
      {result.gallery_truncated === true && (
        <p className={styles.warning}>本次仅检索了部分有效登记记录，未覆盖整个登记库。</p>
      )}
      {statusText && <p className={styles.warning} role="status">{statusText}</p>}
      {!unavailable && candidates.length > 0 && (
        <ol className={styles.candidates}>
          {candidates.map((candidate, index) => {
            const label = candidate.name || candidate.label || (history ? '临时身份' : '未命名人员');
            const occurrences = Array.isArray(candidate.occurrences)
              ? candidate.occurrences.filter(item => item && typeof item === 'object')
              : [];
            // occurrences 已按最近出现时间倒序，用第一条的裁剪图作为候选预览。
            const previewAssetId = history
              ? occurrences.find(item => typeof item.asset_id === 'string' && item.asset_id)?.asset_id ?? null
              : null;
            return (
              <li className={styles.candidate} key={`${candidate.identity_id ?? candidate.person_id ?? 'candidate'}-${index}`}>
                <CandidatePhoto image={candidate.image_base64} alt={`${label}的照片`}
                  assetId={previewAssetId}
                  placeholder={history ? '暂无轨迹图' : '暂无有效照片'} />
                <div className={styles.details}>
                  <strong>候选 {index + 1} · {label}</strong>
                  {candidate.identity_id != null && <span>身份 ID：{candidate.identity_id}</span>}
                  {candidate.identity_id == null && candidate.person_id != null && (
                    <span>{history ? '身份 ID' : '登记 ID'}：{candidate.person_id}</span>
                  )}
                  {candidate.employee_id != null && candidate.employee_id !== '' && (
                    <span>工号：{candidate.employee_id}</span>
                  )}
                  {typeof candidate.similarity === 'number' && Number.isFinite(candidate.similarity) && (
                    <span>余弦相似度：{candidate.similarity.toFixed(3)}（非身份置信度）</span>
                  )}
                  {history && Number.isInteger(candidate.occurrence_count) && (
                    <span>保留期内轨迹：{candidate.occurrence_count} 条</span>
                  )}
                  {occurrences.length > 0 && (
                    <OccurrencePanel occurrences={occurrences} />
                  )}
                  {typeof candidate.match_reason === 'string' && candidate.match_reason && (
                    <span>匹配理由：{candidate.match_reason}</span>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {result.source_asset_id && result.selected_candidate_id != null && (
        <p className={styles.note}>本次检索对象：截图行人 {result.selected_candidate_id}。</p>
      )}
      <p className={styles.note}>支持上传截图选择行人，或上传单人裁剪图检索；再次检索请重新上传。</p>
    </section>
  );
}
