<template>
  <div class="state-flow">
    <div
      v-for="(state, index) in states"
      :key="state"
      class="flow-step-wrapper"
    >
      <!-- 状态节点 -->
      <div class="flow-step">
        <div
          class="step-node"
          :class="{ active: isActive(state), passed: isPassed(state) }"
          :style="isActive(state) ? { backgroundColor: getColor(state), borderColor: getColor(state), boxShadow: `0 0 12px ${getColor(state)}` } : {}"
        >
          {{ state }}
        </div>
      </div>
      <!-- 箭头 -->
      <div v-if="index < states.length - 1" class="flow-arrow">
        <div
          class="arrow-line"
          :class="{ filled: isPassed(states[index + 1]) }"
        ></div>
        <div class="arrow-head" :class="{ filled: isPassed(states[index + 1]) }">▶</div>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  states: {
    type: Array,
    required: true
  },
  currentState: {
    type: String,
    required: true
  },
  colors: {
    type: Object,
    default: () => ({})
  }
})

function isActive(state) {
  return props.currentState === state
}

function isPassed(state) {
  const currentIndex = props.states.indexOf(props.currentState)
  const stateIndex = props.states.indexOf(state)
  return stateIndex < currentIndex
}

function getColor(state) {
  return props.colors[state] || '#00e5ff'
}
</script>

<style scoped>
.state-flow {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0;
}

.flow-step-wrapper {
  display: flex;
  align-items: center;
}

.step-node {
  padding: 6px 14px;
  border: 1px solid var(--border-cyan);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  background: rgba(0, 0, 0, 0.3);
  white-space: nowrap;
  transition: all 0.3s;
}

.step-node.active {
  color: #fff;
  font-weight: bold;
  animation: nodePulse 1.5s ease-in-out infinite;
}

.step-node.passed {
  border-color: rgba(0, 229, 255, 0.4);
  color: var(--text-dim);
  background: rgba(0, 229, 255, 0.05);
}

@keyframes nodePulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.75; }
}

.flow-arrow {
  display: flex;
  align-items: center;
  margin: 0 4px;
}

.arrow-line {
  width: 20px;
  height: 2px;
  background: var(--border-cyan);
  position: relative;
}
.arrow-line.filled {
  background: var(--border-glow);
  box-shadow: 0 0 4px var(--border-glow);
}

.arrow-head {
  font-size: 8px;
  color: var(--border-cyan);
  margin-left: -2px;
}
.arrow-head.filled {
  color: var(--border-glow);
}
</style>
