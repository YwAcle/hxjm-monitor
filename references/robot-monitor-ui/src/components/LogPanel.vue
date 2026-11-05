<template>
  <div class="log-panel panel panel-corner">
    <div class="log-header">
      <span class="log-title">系统日志</span>
      <div class="log-actions">
        <span class="log-count">{{ logs.length }} 条</span>
        <button class="btn btn-sm" @click="clearLogs">清空</button>
      </div>
    </div>
    <div class="log-body" ref="logBody">
      <div
        v-for="(log, index) in logs"
        :key="index"
        class="log-line"
        :class="'log-' + log.level"
      >
        <span class="log-time">[{{ log.time }}]</span>
        <span class="log-msg">{{ log.message }}</span>
      </div>
      <div v-if="logs.length === 0" class="log-empty">暂无日志</div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { useLogger } from '../utils/logger.js'

const { logs, clearLogs } = useLogger()
const logBody = ref(null)

// 自动滚动到底部
watch(() => logs.length, async () => {
  await nextTick()
  if (logBody.value) {
    logBody.value.scrollTop = logBody.value.scrollHeight
  }
})
</script>

<style scoped>
.log-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 14px;
  border-bottom: 1px solid rgba(26, 107, 138, 0.3);
  flex-shrink: 0;
}

.log-title {
  font-size: 13px;
  font-weight: bold;
  color: var(--text-secondary);
  letter-spacing: 1px;
}

.log-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.log-count {
  font-size: 11px;
  color: var(--text-dim);
}

.btn-sm {
  padding: 2px 10px;
  font-size: 11px;
}

.log-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 14px;
  font-family: Consolas, 'Courier New', monospace;
}

.log-line {
  font-size: 13px;
  line-height: 1.8;
  white-space: nowrap;
}

.log-time {
  color: var(--text-dim);
  margin-right: 8px;
}

.log-info .log-msg { color: var(--color-green); }
.log-warn .log-msg { color: var(--color-yellow); }
.log-error .log-msg { color: var(--color-red); }
.log-success .log-msg { color: var(--color-green); }

.log-empty {
  color: var(--text-dim);
  font-size: 13px;
  text-align: center;
  padding: 20px;
}
</style>
