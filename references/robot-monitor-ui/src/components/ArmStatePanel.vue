<template>
  <div class="arm-panel panel panel-corner">
    <!-- 标题栏 -->
    <div class="panel-header">
      <span class="panel-title">DM-B601机械臂状态</span>
      <span class="status-dot" :class="connected ? 'online' : 'offline'"></span>
    </div>

    <div class="panel-body">
      <!-- 当前状态大色块 -->
      <div
        class="state-badge active"
        :style="{ backgroundColor: currentColor + '22', color: currentColor, border: `1px solid ${currentColor}` }"
      >
        {{ arm.state }}
      </div>

      <!-- 状态流转图 -->
      <div class="flow-section">
        <StateFlow
          :states="armStates"
          :current-state="arm.state"
          :colors="armStateColors"
        />
      </div>

      <!-- 参数信息 -->
      <div class="params-section">
        <div class="param-row">
          <span class="param-label">夹爪状态</span>
          <span class="gripper-indicator" :class="arm.gripper">
            <span class="gripper-icon">{{ arm.gripper === 'open' ? '◠◡' : '◠‿◠' }}</span>
            {{ arm.gripper === 'open' ? '张开' : '闭合' }}
          </span>
        </div>

        <div class="param-row">
          <span class="param-label">关节角度</span>
          <div class="joints-display">
            <span v-for="(angle, i) in arm.joints" :key="i" class="joint-item">
              J{{ i + 1 }}: {{ angle.toFixed(1) }}°
            </span>
          </div>
        </div>

        <div class="param-row">
          <span class="param-label">放置点坐标</span>
          <span class="param-value mono">
            ({{ arm.target_place.map(v => v.toFixed(1)).join(', ') }})
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import StateFlow from './StateFlow.vue'
import { ARM_STATES, ARM_STATE_COLORS } from '../config/index.js'

const props = defineProps({
  arm: { type: Object, required: true },
  connected: { type: Boolean, default: false }
})

const armStates = ARM_STATES
const armStateColors = ARM_STATE_COLORS

const currentColor = computed(() => ARM_STATE_COLORS[props.arm.state] || '#00e5ff')
</script>

<style scoped>
.arm-panel {
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
  gap: 14px;
  flex: 1;
}

.flow-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.params-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.param-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  background: rgba(0, 0, 0, 0.2);
  padding: 8px 12px;
  border-radius: 4px;
  border-left: 2px solid var(--border-cyan);
}

.param-label {
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
  min-width: 70px;
  line-height: 24px;
}

.param-value {
  font-size: 14px;
  font-weight: bold;
  color: var(--text-primary);
}
.param-value.mono {
  font-family: Consolas, 'Courier New', monospace;
}

.gripper-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: bold;
}
.gripper-indicator.open {
  color: var(--color-yellow);
}
.gripper-indicator.close {
  color: var(--color-green);
}
.gripper-icon {
  font-size: 16px;
}

.joints-display {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  flex: 1;
}
.joint-item {
  font-family: Consolas, 'Courier New', monospace;
  font-size: 12px;
  color: var(--text-primary);
  background: rgba(0, 229, 255, 0.08);
  padding: 2px 8px;
  border-radius: 3px;
  border: 1px solid rgba(0, 229, 255, 0.15);
}
</style>
