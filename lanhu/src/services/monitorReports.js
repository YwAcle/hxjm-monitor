export function monitoringReports(reports) {
  return reports.filter(row => !['vad', 'joyai', 'anomaly'].includes(row.prompt_type?.toLowerCase())
    && !row.vad_id && !row.report_type?.startsWith('joyai_anomaly_review')
    && !['fight', 'fall', 'violence', 'non-violence', 'fire'].includes(row.report_json?.event_type));
}
