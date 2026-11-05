import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { videoProxies } from './video-proxy.js';
import { readFileSync } from 'node:fs';

const backendOrigin = process.env.VITE_BACKEND_ORIGIN || 'http://192.168.109.191:18080';
const backendWebSocketOrigin = backendOrigin.replace(/^http/, 'ws');

export default defineConfig({
  cacheDir: process.env.VITE_CACHE_DIR || 'node_modules/.vite',
  plugins: [react()],
  css: {
    modules: {
      localsConvention: 'camelCaseOnly',
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    strictPort: true,
    // Shared development hosts can exhaust the per-user inotify watch quota.
    watch: { usePolling: true, interval: 1000 },
    open: 'http://192.168.109.191:3000/',
    proxy: {
      ...videoProxies(),
      '/joyai-tool': {
        target: process.env.JOYAI_TOOL_ORIGIN || 'http://127.0.0.1:34204',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/joyai-tool(?=\/|$)/, ''),
        configure(proxy) {
          proxy.on('proxyReq', (upstream, request) => {
            if (request.method !== 'POST' || upstream.path !== '/reviews/restart'
                || request.headers['x-joyai-action'] !== 'restart-review') return;
            if (request.headers.origin && request.headers.origin !== `http://${request.headers.host}`
                && request.headers.origin !== `https://${request.headers.host}`) return;
            try {
              const config = JSON.parse(readFileSync(new URL('../.run/joyai/config.json', import.meta.url), 'utf8'));
              upstream.setHeader('X-JoyAI-Token', config.token);
            } catch { /* The tool returns an authentication error if private configuration is unavailable. */ }
          });
        },
      },
      '/api/chat': {
        target: 'http://192.168.96.202:8012',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/api/sessions': {
        target: 'http://192.168.96.202:8012',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/api': {
        target: backendOrigin,
        changeOrigin: true,
      },
      '/ws': {
        target: backendWebSocketOrigin,
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
});
