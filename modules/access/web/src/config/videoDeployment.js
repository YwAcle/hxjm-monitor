export function videoMediaBase(env, location) {
  if (env.VITE_VIDEO_ANALYSIS_MODE !== 'local') return '/shared-media/live';
  const host = location.hostname || '127.0.0.1';
  return `${location.protocol}//${host}:${env.VITE_MEDIA_PORT || '18889'}/live`;
}

export function videoAnalysisEnabled(env) {
  return env.VITE_VIDEO_ANALYSIS_MODE !== 'local' || env.VITE_VIDEO_ANALYSIS_ENABLED !== 'false';
}

export function detectionSocketPath(synchronized = false) {
  return `/ws/detections${synchronized ? '?frames=1' : ''}`;
}

export function synchronizedAnalysisAllowed(env) {
  return env.VITE_VIDEO_ANALYSIS_SUBSCRIBER !== 'true';
}
