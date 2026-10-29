import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { videoProxies } from './video-proxy.js';

const backendOrigin = process.env.VITE_BACKEND_ORIGIN || 'http://192.168.109.191:18080';
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
    open: 'http://192.168.109.191:3000/',
    proxy: {
      ...videoProxies(),
      '/api/chat': {
        target: 'http://192.168.96.201:8002',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/api/sessions': {
        target: 'http://192.168.96.201:8002',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/auth': {
        target: backendOrigin,
        changeOrigin: true,
        rewrite: path => path.replace(/^\/auth(?=\/|$)/, ''),
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
