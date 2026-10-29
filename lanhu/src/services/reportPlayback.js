// Report cards use the same recording assets and player as historical queries.
function routePlayback(report) {
  const route = report.report_json?.route;
  for (const track of Array.isArray(route) ? route : []) {
    for (const recording of track.recordings || []) {
      if (recording.state === 'available' && recording.asset_id) {
        return {
          ...recording,
          source_id: track.source_id,
          stream_session_id: track.stream_session_id,
          offset_ms: Math.max(0, recording.first_media_pts_ms ?? 0),
        };
      }
    }
  }
  return null;
}

export async function resolveReportPlayback(report, api) {
  const playback = routePlayback(report);
  if (playback) return { playback };
  if (report.episode_id) {
    const reports = await api.reports({ subject_kind: 'activity', subject_id: report.episode_id });
    for (const current of reports.items || []) {
      const playback = routePlayback(current);
      if (playback) return { playback };
    }
    throw new Error('该报告对应的录像暂不可用，请稍后重试');
  }
  if (Array.isArray(report.report_json?.route)) throw new Error('该报告对应的录像暂不可用，请稍后重试');
  if (report.record_url) return { url: report.record_url };
  throw new Error('该报告暂无可用录像');
}
