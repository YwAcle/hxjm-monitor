import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const frontendRoot = fileURLToPath(new URL('.', import.meta.url));
const playerRoot = fileURLToPath(new URL(
  '../../lanhu/src/components/CenterPanel/components/MonitorGrid/WebRTCPlayer/',
  import.meta.url,
));

export default defineConfig({
  plugins: [react()],
  resolve: {
    dedupe: ['react', 'react-dom'],
  },
  server: {
    host: '0.0.0.0',
    port: 3010,
    strictPort: true,
    fs: {
      allow: [frontendRoot, playerRoot],
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 3010,
    strictPort: true,
  },
});
