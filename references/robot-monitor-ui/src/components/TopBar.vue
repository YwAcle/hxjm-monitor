<template>
  <div class="topbar">
    <!-- 左侧装饰 -->
    <div class="topbar-deco left"></div>

    <!-- 标题 -->
    <div class="topbar-title">
      <span class="title-icon">⬡</span>
      M20-Pro机器狗 + DM-B601机械臂综合监控面板
    </div>

    <!-- 右侧状态信息 -->
    <div class="topbar-right">
      <div class="topbar-item">
        <span class="status-dot" :class="connected ? 'online' : 'offline'"></span>
        <span class="item-label">{{ connected ? '已连接' : '未连接' }}</span>
      </div>
      <div class="topbar-item">
        <span class="item-icon">⏱</span>
        <span class="item-value mono">{{ currentTime }}</span>
      </div>
      <div class="topbar-item">
        <span class="item-icon">📶</span>
        <span class="item-value mono">{{ ping }}ms</span>
      </div>
    </div>

    <!-- 右侧装饰 -->
    <div class="topbar-deco right"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  connected: { type: Boolean, default: false }
})

const currentTime = ref('')
const ping = ref('--')
let timer = null

function updateTime() {
  const now = new Date()
  currentTime.value = [
    String(now.getHours()).padStart(2, '0'),
    String(now.getMinutes()).padStart(2, '0'),
    String(now.getSeconds()).padStart(2, '0')
  ].join(':')
}

onMounted(() => {
  updateTime()
  timer = setInterval(updateTime, 1000)
  // 模拟 ping 值
  setInterval(() => {
    if (props.connected) {
      ping.value = Math.floor(Math.random() * 20) + 5
    } else {
      ping.value = '--'
    }
  }, 2000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.topbar {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  background: linear-gradient(180deg, rgba(10, 20, 40, 0.9) 0%, rgba(6, 10, 20, 0.5) 100%);
  border-bottom: 1px solid var(--border-cyan);
  flex-shrink: 0;
}

.topbar-deco {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 200px;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--border-glow), transparent);
}
.topbar-deco.left { left: 20px; }
.topbar-deco.right { right: 20px; }

.topbar-title {
  font-size: 22px;
  font-weight: bold;
  letter-spacing: 4px;
  color: var(--text-primary);
  text-shadow: 0 0 10px rgba(0, 229, 255, 0.5);
  display: flex;
  align-items: center;
  gap: 12px;
}
.title-icon {
  color: var(--border-glow);
  font-size: 24px;
}

.topbar-right {
  position: absolute;
  right: 30px;
  display: flex;
  align-items: center;
  gap: 20px;
}

.topbar-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}
.item-icon {
  font-size: 14px;
}
.item-value {
  color: var(--border-glow);
}
.mono {
  font-family: Consolas, monospace;
}
</style>
