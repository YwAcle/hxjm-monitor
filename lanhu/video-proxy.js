export function videoProxies(env = process.env) {
  const local = env.VITE_VIDEO_ANALYSIS_MODE === 'local';
  const mediaOrigin = env.SHARED_MEDIA_ORIGIN || 'http://127.0.0.1:18889';
  return {
    '/ws/detections': {
      target: local ? env.VITE_VIDEO_ANALYSIS_ORIGIN || 'http://127.0.0.1:28010'
        : env.VIDEO_ANALYSIS_SHARED_ORIGIN || 'http://127.0.0.1:28010',
      ws: true,
      changeOrigin: true,
    },
    '/shared-media': {
      target: mediaOrigin,
      changeOrigin: true,
      rewrite: path => path.replace(/^\/shared-media(?=\/|$)/, ''),
      configure(proxy) {
        proxy.on('proxyRes', (response, request) => {
          const location = response.headers.location;
          if (!location) return;
          const upstreamPath = request.url.replace(/^\/shared-media(?=\/|$)/, '');
          const session = new URL(location, new URL(upstreamPath, mediaOrigin));
          // Keep WHEP session PATCH/DELETE on the same proxy as the initial POST.
          if (session.origin === new URL(mediaOrigin).origin) {
            response.headers.location = `/shared-media${session.pathname}${session.search}`;
          }
        });
      },
    },
  };
}
