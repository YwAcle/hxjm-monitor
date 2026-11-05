// Behavior reports have their own alarm cards; other VAD functions (e.g. fire) remain visible.
export function monitoringReports(reports) {
  return reports.filter(row => !row.report_type?.startsWith('joyai_anomaly_review')
    && !['fight', 'fall', 'violence', 'non-violence'].includes(row.report_json?.event_type));
}
