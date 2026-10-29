<template>
  <div class="building-container">
    <div class="building-content">
      <i class="el-icon-loading building-icon"></i>
      <div class="building-text">功能建设中...</div>
      <div class="building-desc">敬请期待</div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'Building'
}
</script>

<style lang="scss" scoped>
.building-container {
  width: 100%;
  height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(
    90deg,
    rgba(0, 40, 85, 0.95),
    rgba(0, 80, 170, 0.95),
    rgba(0, 60, 130, 0.95)
  );
}

.building-content {
  text-align: center;
  color: #fff;
  animation: fadeIn 1s ease-in-out;
}

.building-icon {
  font-size: 48px;
  margin-bottom: 20px;
  display: block;
  color: #409eff;
  animation: rotate 2s linear infinite;
}

.building-text {
  font-size: 24px;
  font-weight: bold;
  margin-bottom: 10px;
  background: linear-gradient(90deg, #fff, #88c0ff);
  -webkit-background-clip: text;
  color: transparent;
}

.building-desc {
  font-size: 16px;
  color: rgba(255, 255, 255, 0.8);
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
