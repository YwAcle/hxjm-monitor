<template>

  <div class="screen-container">
    <el-container class="monitoring-dashboard">
      <el-header class="dashboard-header">
        <el-row style="height: 100%;">
          <el-col :span="8"
                  class="left-section">
          </el-col>
          <el-col :span="8"
                  class="middle-section">
            <h1>智慧监控平台</h1>
          </el-col>
          <el-col :span="8"
                  class="right-section">
            <div class="tools-wrapper">
              <el-dropdown class="avatar-container right-menu-item"
                           @command="handleFuncCommand"
                           trigger="click">
                <div class="avatar-wrapper">
                  <img src="@/assets/images/screen/icons/model_selected.svg"
                       class="user-avatar rotating-img">
                </div>
                <el-dropdown-menu slot="dropdown">
                  <el-dropdown-item command="anomalyDetection"
                                    divided>异常检测</el-dropdown-item>
                  <el-dropdown-item command="superResolution"
                                    divided>人脸超分</el-dropdown-item>
                  <el-dropdown-item command="reIdentification"
                                    divided>行人重识别</el-dropdown-item>
                  <el-dropdown-item command="t-a"
                                    divided>文本-动作</el-dropdown-item>
                  <el-dropdown-item command="algDisplay"
                                    divided>算法展示</el-dropdown-item>
                </el-dropdown-menu>
              </el-dropdown>
            </div>
            <div class="time-wrapper ">
              <div class="time-tools">{{ formattedCurrentTime }}</div>
            </div>
          </el-col>
        </el-row>

      </el-header>
      <!-- 条件查询栏 -->
      <el-container>
        <el-aside width="30%"
                  class="dashboard-sidebar">
          <div class="device-stats">
            <div class="stats-header">
              <span class="stats-title">设备总览</span>
            </div>
            <div class="stats-body">
              <div class="stats-left">
                <div class="stats-row">
                  <div class="stats-item">
                    <i class="el-icon-video-camera stats-icon"></i>
                    <div class="stats-content">
                      <div class="left-part">
                        <div class="stats-label">设备总数</div>
                      </div>
                      <div class="stats-value">
                        <span class="number">1200</span>
                        <span class="unit">台</span>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="stats-row">
                  <div class="stats-item">
                    <div class="stats-value">
                      <span class="number">435</span>
                      <span class="unit">个</span>
                    </div>
                    <div class="stats-label">
                      <img src=""
                           class="stats-icon">
                      <span>事件总数</span>
                    </div>
                  </div>
                  <div class="stats-item">
                    <div class="stats-value">
                      <span class="number">232</span>
                      <span class="unit">个</span>
                    </div>
                    <div class="stats-label">
                      <img src=""
                           class="stats-icon">
                      <span>设备事件</span>
                    </div>
                  </div>
                </div>
                <div class="stats-row">
                  <div class="stats-item">
                    <div class="stats-value">
                      <span class="number">568</span>
                      <span class="unit">次</span>
                    </div>
                    <div class="stats-label">
                      <img src=""
                           class="stats-icon">
                      <span>预警次数</span>
                    </div>
                  </div>
                  <div class="stats-item">
                    <div class="stats-value">
                      <span class="number">568</span>
                      <span class="unit">次</span>
                    </div>
                    <div class="stats-label">
                      <img src=""
                           class="stats-icon">
                      <span>今日预警</span>
                    </div>
                  </div>
                  <div class="stats-item">
                    <div class="stats-value">
                      <span class="number">568</span>
                      <span class="unit">个</span>
                    </div>
                    <div class="stats-label">
                      <img src=""
                           class="stats-icon">
                      <span>已处理</span>
                    </div>
                  </div>
                </div>
              </div>
              <div class="stats-right">
                <div class="stats-item">
                  <div class="stats-value">
                    <span class="number">373</span>
                    <span class="unit">个</span>
                  </div>
                  <div class="stats-label">
                    <img src=""
                         class="stats-icon">
                    <span>异常设备</span>
                  </div>
                </div>
                <div class="stats-item">
                  <div class="stats-value">
                    <span class="number">122</span>
                    <span class="unit">组</span>
                  </div>
                  <div class="stats-label">
                    <img src=""
                         class="stats-icon">
                    <span>设备布控总数</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <dv-border-box-1 class="device-stats"></dv-border-box-1>
          <dv-border-box-1 class="device-stats"></dv-border-box-1>
          <!-- 左侧监控总览等 -->

        </el-aside>
        <el-main class="dashboard-main">
          <!-- 中间视频区域 -->
          <dv-border-box-1 class="video-section"></dv-border-box-1>
          <dv-border-box-1 class="main-foot-section"></dv-border-box-1>
        </el-main>
        <el-aside width="30%"
                  class="dashboard-sidebar">

        </el-aside>
      </el-container>
    </el-container>
    <reid-component ref="reidComponent"
                    :funcCode="dialogFuncCode" />
    <algi-display-component ref="algiDisplayComponent" />
  </div>

</template>
  <script>

import ReidComponent from './components/ReIDComponent.vue';
import AlgiDisplayComponent from './components/AlgDisplayComponent.vue';
export default {
  components: {
    ReidComponent,
    AlgiDisplayComponent
  },
  data () {
    return {
      dialogFuncCode: "",//功能框编码

      currentTime: '', // 存储格式化后的时间字符串
    };
  },
  computed: {
    formattedCurrentTime () {
      return this.currentTime;
    },
  },
  mounted () {
    this.updateTime();
    setInterval(this.updateTime, 1000); // 每秒更新时间
  },
  methods: {
    handleFuncCommand (funcCode) {
      this.dialogFuncCode = funcCode
      if (funcCode == "anomalyDetection") {
        // this.$refs.reidComponent.dialogMainTitle = "异常检测";
      } else if (funcCode == "superResolution") {
        // this.$refs.dialogComponent.dialogMainTitle = "人脸超分";
      } else if (funcCode == "reIdentification") {
        this.$refs.reidComponent.dialogMainTitle = "行人重识别";
        this.$refs.reidComponent.getList();
        this.$refs.reidComponent.reIdDialogVisible = true;
      } else if (funcCode == "t-a") {
        this.$refs.reidComponent.dialogMainTitle = "文本-动作";
      } else if (funcCode == "algDisplay") {
        this.$refs.algiDisplayComponent.algTypeDialogVisible = true;
      }




    },
    updateTime () {
      const now = new Date();
      const year = now.getFullYear();
      const month = this.pad(now.getMonth() + 1);
      const day = this.pad(now.getDate());
      const hours = this.pad(now.getHours());
      const minutes = this.pad(now.getMinutes());
      const seconds = this.pad(now.getSeconds());
      // 设置 currentTime 为格式化后的时间字符串
      this.currentTime = `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
    },
    pad (value) {
      // 如果数值小于10，前面补0
      return value < 10 ? '0' + value : value;
    },
  },
  beforeDestroy () {
    // 组件销毁时清除定时器
    clearInterval(this.updateTimer);
  },
}
  </script>
  <style lang="scss" scoped>
.monitoring-dashboard {
  width: 100%;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background-image: url('../../assets/images/screen/background.png');
  background-size: cover;
  color: #fff;
  overflow: hidden;
}

.el-container {
  flex: 1;
  min-height: 0;

  .dashboard-sidebar {
    height: 100%;
    overflow: hidden;

    .device-stats {
      height: calc(
        (100% - 3vw) / 3
      ); // 将容器高度三等分,每份占(总高度-3vw间隙)/3
      margin-bottom: 1vw;
      display: flex;
      flex-direction: column;

      .stats-header {
        flex: 0 0 2vw; // 固定高度，不伸缩
        min-height: 2vw;
        display: flex;
        align-items: center;
        padding: 0 1.5vw;
        margin-bottom: 0.5vw;
        position: relative;

        &::before {
          content: '';
          position: absolute;
          top: 0.3vw;
          left: 50%;
          transform: translateX(-50%);
          width: 95%;
          height: calc(100% - 0.3vw);
          background: linear-gradient(
            90deg,
            transparent,
            rgba(64, 158, 255, 0.1),
            rgba(64, 158, 255, 0.1),
            transparent
          );
          z-index: 0;
        }

        &::after {
          content: '';
          position: absolute;
          bottom: 0;
          left: 50%;
          transform: translateX(-50%);
          width: 95%;
          height: 0.15vw;
          background: linear-gradient(
            to right,
            transparent,
            rgba(87, 157, 255, 0.4),
            rgba(87, 157, 255, 0.4),
            transparent
          );
          box-shadow: 0 0 0.4vw rgba(87, 157, 255, 0.3);
        }

        .stats-title {
          position: relative;
          z-index: 1;
          font-size: 1.2vw;
          color: #fff;
          font-weight: 600;
          letter-spacing: 0.1vw;
          text-shadow: 0 0 0.5vw rgba(255, 255, 255, 0.3);

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
      .stats-body {
        flex: 1;
        display: flex;
        padding: 0vw 0vw 1vw 1.5vw;
        gap: 2vw;

        .stats-left {
          flex: 1;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          border-right: 0.15vw solid rgba(87, 157, 255, 0.15);
          padding-right: 1.5vw;

          .stats-row {
            display: flex;
            justify-content: space-between;
            gap: 1.5vw;

            &:not(:last-child) {
              margin-bottom: 0.5vw;
            }

            &:first-child .stats-item {
              height: 2vw;
              width: 100%;
              flex-direction: row !important;
              align-items: center;
              justify-content: space-between !important;
              padding: 0.5vw 1.2vw;
              border: 0.1vw solid #409eff;
              border-radius: 0.3vw;

              .stats-icon {
                font-size: 1.4vw;
                color: #409eff;
                text-shadow: 0 0 10px rgba(64, 158, 255, 0.3);
              }

              .stats-content {
                display: flex;
                align-items: center;
                justify-content: space-between;
                width: 100%;
                margin-left: 0.8vw;

                .left-part {
                  display: flex;
                  align-items: center;
                  gap: 0.8vw;

                  .stats-label {
                    font-size: 0.9vw;
                    color: rgba(255, 255, 255, 0.9);
                  }
                }

                .stats-value {
                  display: flex;
                  align-items: baseline;
                  margin: 0;

                  .number {
                    font-size: 1.2vw;
                    color: #409eff;
                  }

                  .unit {
                    font-size: 0.8vw;
                    color: rgba(255, 255, 255, 0.7);
                  }
                }
              }
            }

            .stats-item {
              flex: 1;
              display: flex;
              flex-direction: column;
              justify-content: center;
              align-items: center;

              .stats-value {
                display: flex;
                align-items: baseline;
                justify-content: center;
                margin-bottom: 0.3vw;

                .number {
                  font-size: 1.8vw;
                  font-weight: bold;
                  color: #409eff;
                  margin-right: 0.3vw;
                  line-height: 1;
                  text-shadow: 0 0 0.8vw rgba(64, 158, 255, 0.5);
                  animation: glow 1.5s ease-in-out infinite alternate;
                }

                .unit {
                  font-size: 0.8vw;
                  color: rgba(255, 255, 255, 0.7);
                }
              }

              .stats-label {
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 0.9vw;
                color: rgba(255, 255, 255, 0.9);
                white-space: nowrap;

                .stats-icon {
                  width: 1vw;
                  height: 1vw;
                  margin-right: 0.4vw;
                }
              }
            }
          }
        }

        .stats-right {
          flex: 1;
          display: flex;
          flex-direction: column;
          justify-content: space-around;
          padding-left: 1.5vw;
        }
      }
    }
  }
}

.dashboard-header {
  background-image: url('../../assets/images/screen/header.png');
  background-size: cover;
  height: 10% !important;
  background-position: center;
  background-size: contain; /* 背景图片会被缩放以完全适应元素，同时保持图片的宽高比 */
  background-repeat: no-repeat; /* 防止背景图片重复 */
  flex-direction: row;
  .left-section {
    display: flex;
    height: 100%;
    justify-content: center;
    align-items: center;
    font-size: 26px;
  }
  .middle-section {
    display: flex;
    height: 100%;
    justify-content: center;
    align-items: center;
    font-size: 1.5rem;
    padding-bottom: 1%;
  }
  .right-section {
    height: 100%;
    display: flex;
    align-items: center; // 垂直居中对齐
    justify-content: flex-end; // 子元素靠右对齐
  }

  .tools-wrapper,
  .time-wrapper {
    position: relative;
  }
  .time-tools {
    font-size: 1.2rem;
  }
}
.header-tittle {
  justify-content: center;
  align-items: center;
  text-align: center;
}
.dashboard-sidebar,
.dashboard-main {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: transparent;
}
.el-main {
  padding: 8px 0 8px 0 !important;
  display: flex;
  flex-direction: column;
  height: 100%; /* 确保主区域充满高度 */
  justify-content: flex-start; /* 从顶部开始排列 */
}
.video-section {
  flex: 2;
  margin-bottom: 10px;
}
.main-foot-section {
  flex: 1;
  margin-top: 0;
}

.search-section {
  margin-top: 0.5rem; /* 为每个 section 添加底部间距 */
  width: 100%;
  height: 2% !important;
  display: flex;
  align-items: center;
  text-align: center;
}

.rotating-img {
  width: 100%; /* 设置图片宽度为父元素宽度的 50% */
  height: 100%; /* 设置图片高度为父元素高度的 50% */
  animation: rotate 10s linear infinite;
}
.avatar-container {
  .avatar-wrapper {
    margin-top: 5px;
    position: relative;
    .user-avatar {
      cursor: pointer;
      width: 100%;
      height: 50px;
    }
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