import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { mockWebSocketPlugin } from './src/mock/mockPlugin.js'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    // 开发模式下内置 Mock WebSocket 服务，无需真实硬件即可演示
    // 生产构建时此插件不会生效，前端将连接 config 中配置的真实后端地址
    mockWebSocketPlugin()
  ],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // 如需对接真实后端，取消下面注释并修改 target 地址
    // proxy: {
    //   '/api': {
    //     target: 'http://192.168.1.100:8080',
    //     changeOrigin: true
    //   }
    // }
  }
})
