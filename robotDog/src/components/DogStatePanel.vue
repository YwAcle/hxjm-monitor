<template>
  <div class="dog-panel panel panel-corner">
    <!-- 标题栏 -->
    <div class="panel-header">
      <span class="panel-title">M20-Pro机器狗状态</span>
      <span class="status-dot" :class="connected ? 'online' : 'offline'"></span>
    </div>

    <div class="panel-body">
      <!-- 当前状态大色块 -->
      <div
        class="state-badge active"
        :style="{ backgroundColor: currentColor + '22', color: currentColor, border: `1px solid ${currentColor}` }"
      >
        {{ dog.state }}<span v-if="dog.state === '移动'" class="state-sub">（抓取姿态调整）</span>
      </div>

      <!-- 状态流转条 -->
      <div class="flow-section">
        <StateFlow
          :states="dogStates"
          :current-state="dog.state"
          :colors="dogStateColors"
        />
        <!-- 进度条 -->
        <div class="progress-bar">
          <div
            class="progress-fill"
            :style="{ width: progressPercent + '%', backgroundColor: currentColor }"
          ></div>
        </div>
      </div>

      <!-- 参数信息 -->
      <div class="params-grid">
        <div class="param-item">
          <span class="param-label">底盘速度</span>
          <span class="param-value">{{ dog.velocity.toFixed(2) }} m/s</span>
        </div>
        <div class="param-item">
          <span class="param-label">目标垃圾坐标</span>
          <span class="param-value mono">
            ({{ dog.target_trash.map(v => v.toFixed(1)).join(', ') }})
          </span>
        </div>
        <div class="param-item">
          <span class="param-label">当前位置</span>
          <span class="param-value mono">
            ({{ dog.position.map(v => v.toFixed(2)).join(', ') }})
          </span>
        </div>
        <div class="param-item">
          <span class="param-label">电量</span>
          <span class="param-value" :style="{ color: batteryColor }">{{ dog.battery }}%</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import StateFlow from './StateFlow.vue'
import { DOG_STATES, DOG_STATE_COLORS } from '../config/index.js'

const props = defineProps({
  dog: { type: Object, required: true },
  connected: { type: Boolean, default: false }
})

const dogStates = DOG_STATES
const dogStateColors = DOG_STATE_COLORS

const currentColor = computed(() => DOG_STATE_COLORS[props.dog.state] || '#00e5ff')

const progressPercent = computed(() => {
  const idx = DOG_STATES.indexOf(props.dog.state)
  if (idx === -1) return 0
  return ((idx + 1) / DOG_STATES.length) * 100
})

const batteryColor = computed(() => {
  if (props.dog.battery > 50) return 'var(--color-green)'
  if (props.dog.battery > 20) return 'var(--color-yellow)'
  return 'var(--color-red)'
})
</script>

<style scoped>
.dog-panel {
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid rgba(26, 107, 138, 0.3);
}
.panel-title {
  font-size: 16px;
  font-weight: bold;
  letter-spacing: 1px;
}

.panel-body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
}

.state-sub {
  font-size: 13px;
  font-weight: normal;
  opacity: 0.8;
}

.flow-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.progress-bar {
  width: 100%;
  height: 4px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 2px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.5s ease, background-color 0.5s ease;
  box-shadow: 0 0 6px currentColor;
}

.params-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.param-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: rgba(0, 0, 0, 0.2);
  padding: 8px 12px;
  border-radius: 4px;
  border-left: 2px solid var(--border-cyan);
}

.param-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.param-value {
  font-size: 15px;
  font-weight: bold;
  color: var(--text-primary);
}
.param-value.mono {
  font-family: Consolas, 'Courier New', monospace;
  font-size: 13px;
}
</style>
