import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { videoProxies } from './video-proxy.js';

const backendOrigin = process.env.VITE_BACKEND_ORIGIN || 'http://127.0.0.1:18080';
const backendWebSocketOrigin = backendOrigin.replace(/^http/, 'ws');

export default defineConfig({
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
    open: false,
    proxy: {
      ...videoProxies(),
      '/api/chat': {
        target: process.env.AGENT_ORIGIN || 'http://127.0.0.1:9',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/api/sessions': {
        target: process.env.AGENT_ORIGIN || 'http://127.0.0.1:9',
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
