<template>
  <div class="screen-container">
    <!-- 顶部导航 -->
    <div class="nav-header">
      <div class="nav-left">
        <img src=""
             class="logo" />
        <span class="title">智慧监控平台</span>
      </div>
      <div class="nav-center">
        <div class="nav-item"
             :class="{ active: currentRoute === item.path }"
             v-for="item in navItems"
             :key="item.path"
             @click="handleNavClick(item.path)">
          {{ item.name }}
        </div>
      </div>
      <div class="nav-right">
        <span class="time">{{ currentTime }}</span>

      </div>
    </div>

    <!-- 主体内容区域 - 通过路由动态加载 -->
    <router-view class="main-content" />
  </div>
</template>

<script>
export default {
  name: 'ScreenTest',
  data () {
    return {
      currentTime: '',
      currentRoute: '/screen/realtimemonitor',
      navItems: [
        { name: '实时监控', path: '/screen/realtimemonitor' },
        { name: '历史分析', path: '/screen/historyanalysis' },
        { name: '算法展示', path: '/screen/algorithmbukong' },
      ]
    }
  },
  mounted () {
    this.updateTime()
    setInterval(this.updateTime, 1000)
    // 设置初始路由
    if (this.$route.path === '/screen') {
      this.$router.replace('/screen/realtimemonitor')
    } else {
      this.currentRoute = this.$route.path
    }

  },
  methods: {
    updateTime () {
      const now = new Date()
      this.currentTime = now.toLocaleString('zh-CN', {
        hour12: false,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      })
    },
    handleNavClick (path) {
      this.currentRoute = path
      this.$router.push(path)
    },
  }
}
</script>

<style lang="scss" scoped>
.screen-container {
  width: 100vw;
  height: 100vh;
  background: linear-gradient(135deg, #001f3f, #003366);
  color: #fff;
  display: flex;
  flex-direction: column;
  overflow: hidden;

  .nav-header {
    height: 6vh;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 1.5vw;
    background: linear-gradient(
      90deg,
      rgba(0, 40, 85, 0.95),
      rgba(0, 80, 170, 0.95),
      rgba(0, 60, 130, 0.95)
    );
    border-bottom: 1px solid rgba(0, 149, 255, 0.3);
    z-index: 100;
    box-shadow: 0 2px 15px rgba(0, 0, 0, 0.3);

    .nav-left {
      display: flex;
      align-items: center;
      width: 20%;

      .logo {
        height: 3.5vh;
        margin-right: 1vw;
      }

      .title {
        font-size: calc(1.1vw + 0.2vh);
        color: #fff;
        font-weight: 600;
        letter-spacing: 0.1em;
        text-shadow: 0 0 20px rgba(0, 149, 255, 0.3);
        background: linear-gradient(45deg, #fff, #00bfff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
      }
    }

    .nav-center {
      display: flex;
      justify-content: center;
      flex: 1;
      gap: 3vw;

      .nav-item {
        font-size: calc(0.8vw + 0.2vh);
        color: rgba(255, 255, 255, 0.85);
        cursor: pointer;
        padding: 0.8vh 1.5vw;
        border-radius: 6px;
        position: relative;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

        &::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 149, 255, 0.1);
          border-radius: 6px;
          opacity: 0;
          transition: opacity 0.3s ease;
        }

        &.active {
          color: #00bfff;
          background: rgba(0, 149, 255, 0.15);

          &::after {
            content: '';
            position: absolute;
            bottom: -0.8vh;
            left: 50%;
            transform: translateX(-50%);
            width: 2.5vw;
            height: 3px;
            background: linear-gradient(
              90deg,
              rgba(0, 191, 255, 0),
              #00bfff,
              rgba(0, 191, 255, 0)
            );
            box-shadow: 0 0 12px rgba(0, 191, 255, 0.8);
          }
        }

        &:hover {
          color: #00bfff;
          transform: translateY(-1px);

          &::before {
            opacity: 1;
          }
        }
      }
    }

    .nav-right {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      width: 20%;
      gap: 1.5vw;

      .time {
        font-size: calc(0.8vw + 0.2vh);
        color: rgba(255, 255, 255, 0.9);
        position: relative;
        letter-spacing: 0.05em;
        font-weight: 500;
        text-shadow: 0 0 10px rgba(0, 149, 255, 0.3);
        padding: 0.5vh 0;

        &::after {
          content: '';
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          height: 1px;
          background: linear-gradient(
            90deg,
            transparent,
            rgba(0, 149, 255, 0.4),
            transparent
          );
        }
      }

      .tools-wrapper {
        display: flex;
        align-items: center;

        .avatar-container {
          margin-left: 1vw;

          .avatar-wrapper {
            position: relative;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            overflow: hidden;
            border: 2px solid rgba(0, 149, 255, 0.3);
            box-shadow: 0 0 20px rgba(0, 149, 255, 0.3);
            cursor: pointer;
            transition: all 0.3s ease;

            &:hover {
              border-color: rgba(0, 149, 255, 0.6);
              box-shadow: 0 0 25px rgba(0, 149, 255, 0.4);
            }

            .user-avatar {
              width: 100%;
              height: 100%;
              object-fit: cover;
            }

            .rotating-img {
              animation: rotate 10s linear infinite;
            }
          }
        }
      }
    }
  }

  .main-content {
    flex: 1;
    overflow: hidden;
    position: relative;
    padding: 1vh 1vw;
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

@keyframes shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}

// 优化下拉菜单样式
::v-deep .el-dropdown-menu {
  background: rgba(0, 40, 85, 0.95);
  border: 1px solid rgba(0, 149, 255, 0.3);
  border-radius: 4px;
  padding: 4px 0;
  box-shadow: 0 0 25px rgba(0, 0, 0, 0.3);

  .el-dropdown-menu__item {
    color: rgba(255, 255, 255, 0.85);
    font-size: calc(0.7vw + 0.2vh);
    padding: 8px 16px;
    transition: all 0.3s ease;

    &:hover {
      background: rgba(0, 149, 255, 0.15);
      color: #00bfff;
    }

    &.divided {
      border-top: 1px solid rgba(0, 149, 255, 0.2);
      margin-top: 4px;
      padding-top: 8px;
    }
  }
}

// 优化动画效果
@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

// 添加全局过渡效果
* {
  transition: all 0.3s ease;
}

// 添加全局阴影效果
.panel-box {
  box-shadow: 0 0 30px rgba(0, 149, 255, 0.1);
  border: 1px solid rgba(0, 149, 255, 0.3);
  background: rgba(0, 40, 85, 0.7);

  &:hover {
    box-shadow: 0 0 40px rgba(0, 149, 255, 0.15);
  }
}

// 数值显示优化
.number {
  color: #00bfff;
  text-shadow: 0 0 10px rgba(0, 149, 255, 0.5);
}

// 图表颜色优化
.chart {
  filter: drop-shadow(0 0 10px rgba(0, 149, 255, 0.2));
}
</style>
