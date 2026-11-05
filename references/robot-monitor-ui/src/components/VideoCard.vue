<template>
  <div class="video-card panel panel-corner">
    <!-- 标题栏 -->
    <div class="video-header">
      <span class="video-title">{{ camera.name }}</span>
      <div class="video-header-right">
        <!-- RGB/深度切换开关 -->
        <div v-if="camera.supportDepth" class="view-toggle">
          <button
            class="toggle-btn"
            :class="{ active: currentView === 'rgb' }"
            @click="switchView('rgb')"
          >RGB</button>
          <span class="toggle-sep">/</span>
          <button
            class="toggle-btn"
            :class="{ active: currentView === 'depth' }"
            @click="switchView('depth')"
          >深度</button>
        </div>
        <span v-else class="toggle-placeholder">RGB</span>
        <!-- 连接指示灯 -->
        <span class="status-dot" :class="online ? 'online' : 'offline'"></span>
      </div>
    </div>

    <!-- 视频画面区域 -->
    <div class="video-body">
      <!-- MJPEG 模式: img 标签 -->
      <img
        v-if="streamType === 'mjpeg'"
        ref="imgRef"
        class="video-element"
        alt="video stream"
      />
      <!-- Canvas 模式: ws-jpeg / mock / ws-h264 -->
      <canvas
        v-else
        ref="canvasRef"
        class="video-element"
      ></canvas>

      <!-- 离线遮罩 -->
      <div v-if="!online" class="video-offline">
        <div class="offline-icon">⚠</div>
        <div class="offline-text">视频流断开，等待连接...</div>
      </div>

      <!-- 深度模式标识 -->
      <div v-if="currentView === 'depth' && online" class="depth-badge">DEPTH</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useVideoStream } from '../composables/useVideoStream.js'
import { USE_MOCK } from '../config/index.js'

const props = defineProps({
  camera: {
    type: Object,
    required: true
  }
})

const {
  canvasRef,
  imgRef,
  online,
  currentView,
  start,
  switchView
} = useVideoStream(props.camera)

const streamType = computed(() => {
  if (USE_MOCK) return 'mock'
  return props.camera.type
})

onMounted(() => {
  start()
})
</script>

<style scoped>
.video-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.video-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 14px;
  border-bottom: 1px solid rgba(26, 107, 138, 0.3);
  flex-shrink: 0;
}

.video-title {
  font-size: 15px;
  font-weight: bold;
  color: var(--text-primary);
  letter-spacing: 1px;
}

.video-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.view-toggle {
  display: flex;
  align-items: center;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 4px;
  padding: 2px 4px;
}

.toggle-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 12px;
  padding: 2px 8px;
  cursor: pointer;
  border-radius: 3px;
  transition: all 0.2s;
}
.toggle-btn.active {
  background: rgba(0, 229, 255, 0.2);
  color: var(--border-glow);
}
.toggle-btn:hover:not(.active) {
  color: var(--text-primary);
}
.toggle-sep {
  color: var(--text-dim);
  font-size: 12px;
}
.toggle-placeholder {
  font-size: 12px;
  color: var(--text-dim);
  background: rgba(0, 0, 0, 0.3);
  padding: 2px 8px;
  border-radius: 3px;
}

.video-body {
  flex: 1;
  position: relative;
  background: #000;
  min-height: 0;
  overflow: hidden;
}

.video-element {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.video-offline {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.75);
  z-index: 2;
}
.offline-icon {
  font-size: 32px;
  margin-bottom: 8px;
}
.offline-text {
  font-size: 13px;
  color: var(--text-secondary);
}

.depth-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  background: rgba(118, 255, 3, 0.2);
  border: 1px solid var(--color-green);
  color: var(--color-green);
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: Consolas, monospace;
  z-index: 1;
}
</style>
