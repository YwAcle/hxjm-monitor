import React, { useState } from 'react';
import { getPedestrianSearchStatus, getRegistrationImageSrc } from '../../services/pedestrianSearch';
import styles from './PedestrianSearchResult.module.css';

function CandidatePhoto({ image, alt }) {
  const [failed, setFailed] = useState(false);
  const src = getRegistrationImageSrc(image);
  return src && !failed ? (
    <img className={styles.photo} src={src} alt={alt}
      loading="lazy" onError={() => setFailed(true)} />
  ) : <span className={styles.photoPlaceholder}>暂无有效照片</span>;
}

export default function PedestrianSearchResult({ result, onSelect, onCancel, disabled = false, inactive = false }) {
  const candidates = Array.isArray(result.candidates)
    ? result.candidates.filter(candidate => candidate && typeof candidate === 'object')
    : [];
  const statusText = getPedestrianSearchStatus(result);
  const unavailable = ['not_configured', 'no_compatible_features', 'missing_image', 'invalid_image',
    'no_person', 'selection_expired', 'cancelled']
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
    <section className={styles.result} aria-label="登记库行人检索候选">
      <h4 className={styles.title}>登记库候选</h4>
      <p className={styles.note}>姓名来自候选登记档案，不代表身份确认；登记照片不代表历史出现或实时位置，衣着可能已过时。</p>
      {(Number.isInteger(result.searched_count) || Number.isInteger(result.skipped_count)) && (
        <p className={styles.note}>
          {Number.isInteger(result.searched_count) && `本次已检查 ${result.searched_count} 条`}
          {Number.isInteger(result.searched_count) && Number.isInteger(result.skipped_count) && ' · '}
          {Number.isInteger(result.skipped_count) && `跳过 ${result.skipped_count} 条无效记录`}
        </p>
      )}
      {result.gallery_truncated === true && (
        <p className={styles.warning}>本次仅检索了部分有效登记记录，未覆盖整个登记库。</p>
      )}
      {statusText && <p className={styles.warning} role="status">{statusText}</p>}
      {!unavailable && candidates.length > 0 && (
        <ol className={styles.candidates}>
          {candidates.map((candidate, index) => (
            <li className={styles.candidate} key={`${candidate.person_id ?? 'candidate'}-${index}`}>
              <CandidatePhoto image={candidate.image_base64} alt={`${candidate.name || '未命名人员'}的登记照片`} />
              <div className={styles.details}>
                <strong>候选 {index + 1} · {candidate.name || '未命名人员'}</strong>
                {candidate.person_id != null && <span>登记 ID：{candidate.person_id}</span>}
                {candidate.employee_id != null && candidate.employee_id !== '' && (
                  <span>工号：{candidate.employee_id}</span>
                )}
                {typeof candidate.similarity === 'number' && Number.isFinite(candidate.similarity) && (
                  <span>余弦相似度：{candidate.similarity.toFixed(3)}（非身份置信度）</span>
                )}
                {typeof candidate.match_reason === 'string' && candidate.match_reason && (
                  <span>匹配理由：{candidate.match_reason}</span>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
      {result.source_asset_id && result.selected_candidate_id != null && (
        <p className={styles.note}>本次检索对象：截图行人 {result.selected_candidate_id}。</p>
      )}
      <p className={styles.note}>支持上传截图选择行人，或上传单人裁剪图检索；再次检索请重新上传。</p>
    </section>
  );
}
