<template>
  <div class="screen-container">
    <header class="header">
      <div class="header-left">
        <div class="company-logo"></div>
      </div>
      <div class="header-center">
        <h1 class="main-title">国区运营管理平台</h1>
      </div>
      <div class="header-right">
        <div class="datetime">{{ currentTime }}</div>
        <div class="header-tools">
          <el-dropdown trigger="click"
                       @command="handleCommand">
            <span class="tool-btn">
              <i class="el-icon-menu"></i>
            </span>
            <el-dropdown-menu slot="dropdown">
              <el-dropdown-item command="fullscreen">全屏显示</el-dropdown-item>
              <el-dropdown-item command="refresh">刷新页面</el-dropdown-item>
            </el-dropdown-menu>
          </el-dropdown>
        </div>
      </div>
    </header>
    <main class="main-content">
      <section class="left-panel">
        <div class="panel-item device-overview">
          <div class="panel-header">
            <h3 class="panel-title">基础统计</h3>
          </div>
          <div class="panel-content">
            <div class="data-overview">
              <div class="overview-item total-devices">
                <div class="item-icon">
                  <i class="el-icon-video-camera"></i>
                </div>
                <div class="item-info">
                  <div class="item-label">设备总数</div>
                  <div class="item-value">
                    <span class="number">1200</span>
                    <span class="unit">台</span>
                  </div>
                </div>
              </div>
              <div class="stats-grid">
                <div class="grid-item">
                  <div class="item-value">
                    <span class="number">435</span>
                    <span class="unit">个</span>
                  </div>
                  <div class="item-label">事件总数</div>
                </div>
                <div class="grid-item">
                  <div class="item-value">
                    <span class="number">232</span>
                    <span class="unit">个</span>
                  </div>
                  <div class="item-label">设备事件</div>
                </div>
              </div>
              <div class="stats-grid three-columns">
                <div class="grid-item">
                  <div class="item-value">
                    <span class="number">568</span>
                    <span class="unit">次</span>
                  </div>
                  <div class="item-label">预警次数</div>
                </div>
                <div class="grid-item">
                  <div class="item-value">
                    <span class="number">568</span>
                    <span class="unit">次</span>
                  </div>
                  <div class="item-label">今日预警</div>
                </div>
                <div class="grid-item">
                  <div class="item-value">
                    <span class="number">568</span>
                    <span class="unit">个</span>
                  </div>
                  <div class="item-label">已处理</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="panel-item passage-chart">
          <div class="panel-header">
            <h3 class="panel-title">人员通行图表</h3>
          </div>
          <div class="panel-content">
            <div id="passageChart"
                 class="chart"></div>
          </div>
        </div>

        <div class="panel-item vehicle-chart">
          <div class="panel-header">
            <h3 class="panel-title">车辆通行图表</h3>
          </div>
          <div class="panel-content">
            <div id="vehicleChart"
                 class="chart"></div>
          </div>
        </div>
      </section>

      <section class="center-panel">
        <div class="scene-container">
          <!-- 3D场景将在这里渲染 -->
        </div>

        <div class="bottom-stats">
          <!-- 实时数据展示 -->
        </div>
      </section>

      <section class="right-panel">
        <div class="panel-item realtime-monitor">
          <div class="panel-header">
            <h3 class="panel-title">实时监控</h3>
          </div>
          <div class="panel-content">
            <div class="monitor-grid">
              <div class="camera-item"
                   v-for="n in 4"
                   :key="n">
                <div class="camera-feed">
                  <!-- 摄像头画面 -->
                </div>
                <div class="camera-info">
                  <span class="camera-name">摄像头 {{n}}</span>
                  <span class="camera-status">在线</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="panel-item alarm-info">
          <div class="panel-header">
            <h3 class="panel-title">告警信息</h3>
          </div>
          <div class="panel-content">
            <div class="alarm-list">
              <!-- 告警列表项 -->
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<script>
export default {
  name: 'ScreenTest',
  data () {
    return {
      currentTime: '',
      timer: null
    }
  },
  mounted () {
    this.startTimer()
    this.initCharts()
  },
  beforeDestroy () {
    if (this.timer) {
      clearInterval(this.timer)
    }
  },
  methods: {
    startTimer () {
      this.updateTime()
      this.timer = setInterval(this.updateTime, 1000)
    },
    updateTime () {
      const now = new Date()
      this.currentTime = now.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      })
    },
    initCharts () {
      // 初始化图表
    },
    handleCommand (command) {
      switch (command) {
        case 'fullscreen':
          this.toggleFullScreen()
          break
        case 'refresh':
          window.location.reload()
          break
      }
    },
    toggleFullScreen () {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen()
      } else {
        document.exitFullscreen()
      }
    }
  }
}
</script>

<style lang="scss" scoped>
.screen-container {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background-image: url('../../assets/images/screen/background.png');
  background-size: cover;
  color: #fff;
  display: flex;
  flex-direction: column;

  .header {
    height: 10vh;
    display: flex;
    align-items: center;
    padding: 0 2vw;
    background-image: url('../../assets/images/screen/header.png');
    background-size: contain;
    background-position: center;
    background-repeat: no-repeat;

    .header-left {
      width: 15vw;
    }

    .header-center {
      flex: 1;
      text-align: center;

      .main-title {
        font-size: calc(1.8vw + 0.5vh);
        color: #fff;
        text-shadow: 0 0 1vw rgba(255, 255, 255, 0.3);
        padding-bottom: 1vh;
      }
    }

    .header-right {
      width: 15vw;
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: 1vw;

      .datetime {
        font-size: calc(0.9vw + 0.2vh);
      }

      .tool-btn {
        cursor: pointer;
        font-size: calc(1.2vw + 0.2vh);
      }
    }
  }

  .main-content {
    flex: 1;
    display: flex;
    padding: 1vh 1vw;
    gap: 1vw;
    min-height: 0;

    .left-panel,
    .right-panel {
      width: 25vw;
      display: flex;
      flex-direction: column;
      gap: 1vh;
    }

    .center-panel {
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 1vh;

      .scene-container {
        flex: 2;
        background: rgba(0, 24, 65, 0.6);
        border-radius: 0.3vw;
      }

      .bottom-stats {
        flex: 1;
        background: rgba(0, 24, 65, 0.6);
        border-radius: 0.3vw;
      }
    }

    .panel-item {
      background: rgba(0, 24, 65, 0.6);
      border-radius: 0.3vw;
      height: calc((100% - 2vh) / 3);

      .panel-header {
        height: 5vh;
        display: flex;
        align-items: center;
        padding: 0 1.5vw;
        position: relative;

        &::before {
          content: '';
          position: absolute;
          top: 0.3vh;
          left: 50%;
          transform: translateX(-50%);
          width: 95%;
          height: calc(100% - 0.3vh);
          background: linear-gradient(
            90deg,
            transparent,
            rgba(64, 158, 255, 0.1),
            rgba(64, 158, 255, 0.1),
            transparent
          );
          z-index: 0;
        }

        .panel-title {
          position: relative;
          z-index: 1;
          font-size: calc(1.2vw + 0.2vh);
          font-weight: 600;
          letter-spacing: 0.1vw;

          &::before {
            content: '';
            display: inline-block;
            width: 0.3vw;
            height: 1.2vw;
            background: linear-gradient(to bottom, #409eff, #88c0ff);
            margin-right: 0.8vw;
            vertical-align: middle;
            border-radius: 0.15vw;
            box-shadow: 0 0 0.5vw rgba(64, 158, 255, 0.5);
          }
        }
      }

      .panel-content {
        padding: 1vh 1vw;
        height: calc(100% - 5vh);
        overflow: auto;
      }
    }
  }
}

.data-overview {
  .overview-item {
    display: flex;
    align-items: center;
    padding: 0.5vh 1vw;
    background: rgba(0, 24, 65, 0.6);
    border: 0.1vw solid #409eff;
    border-radius: 0.3vw;
    margin-bottom: 1vh;

    .item-icon {
      font-size: calc(1.4vw + 0.2vh);
      color: #409eff;
    }

    .item-info {
      flex: 1;
      margin-left: 0.8vw;

      .item-label {
        font-size: calc(0.9vw + 0.2vh);
      }

      .item-value {
        .number {
          font-size: calc(1.8vw + 0.2vh);
          color: #409eff;
          animation: glow 1.5s ease-in-out infinite alternate;
        }

        .unit {
          font-size: calc(0.8vw + 0.2vh);
        }
      }
    }
  }

  .stats-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1vw;
    margin-top: 1vh;

    &.three-columns {
      grid-template-columns: repeat(3, 1fr);
    }
  }
}

.chart {
  width: 100%;
  height: 100%;
  min-height: 20vh;
}

.monitor-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1vw;
  height: 100%;

  .camera-item {
    aspect-ratio: 16/9;
    background: #000;
    border-radius: 0.3vw;
  }
}

@keyframes glow {
  from {
    text-shadow: 0 0 0.4vw rgba(64, 158, 255, 0.5);
  }
  to {
    text-shadow: 0 0 0.8vw rgba(64, 158, 255, 0.8),
      0 0 1.2vw rgba(64, 158, 255, 0.3);
  }
}
</style>


