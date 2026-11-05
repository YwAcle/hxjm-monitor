<template>
  <div class="app-container">
    <!-- 顶部标题栏 -->
    <TopBar :connected="connected" />

    <!-- 主体内容区 -->
    <div class="main-content">
      <!-- 左侧：四路视频画面 -->
      <div class="video-section">
        <div class="video-grid">
          <VideoCard
            v-for="cam in cameras"
            :key="cam.id"
            :camera="cam"
          />
        </div>
      </div>

      <!-- 右侧：状态机面板 -->
      <div class="status-section">
        <DogStatePanel :dog="robotState.dog" :connected="connected" />
        <ArmStatePanel :arm="robotState.arm" :connected="connected" />
      </div>
    </div>

    <!-- 底部日志面板 -->
    <div class="log-section">
      <LogPanel />
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import TopBar from './components/TopBar.vue'
import VideoCard from './components/VideoCard.vue'
import DogStatePanel from './components/DogStatePanel.vue'
import ArmStatePanel from './components/ArmStatePanel.vue'
import LogPanel from './components/LogPanel.vue'
import { useRobotSocket } from './composables/useRobotSocket.js'
import { CAMERAS } from './config/index.js'
import { addLog } from './utils/logger.js'

const cameras = CAMERAS
const { connected, robotState, connect } = useRobotSocket()

onMounted(() => {
  addLog('系统启动，M20-Pro + DM-B601 监控面板初始化...', 'info')
  connect()
})
</script>

<style scoped>
.app-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background:
    radial-gradient(ellipse at top, rgba(0, 50, 80, 0.15) 0%, transparent 60%),
    var(--bg-darkest);
}

.main-content {
  flex: 1;
  display: flex;
  gap: 12px;
  padding: 12px;
  min-height: 0;
}

/* 左侧视频区域 */
.video-section {
  flex: 1.5;
  min-width: 0;
}

.video-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 12px;
  height: 100%;
}

/* 右侧状态区域 */
.status-section {
  flex: 1;
  min-width: 380px;
  max-width: 480px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 底部日志区域 */
.log-section {
  height: 130px;
  padding: 0 12px 12px 12px;
  flex-shrink: 0;
}

/* 响应式：窄屏时视频改为上下排列 */
@media (max-width: 1200px) {
  .main-content {
    flex-direction: column;
  }
  .status-section {
    max-width: none;
    min-width: 0;
    flex-direction: row;
  }
  .status-section > * {
    flex: 1;
  }
}
</style>
