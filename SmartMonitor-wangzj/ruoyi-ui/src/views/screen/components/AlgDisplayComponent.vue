<template>
  <el-dialog :close-on-click-modal="false"
             append-to-body
             :visible.sync="algTypeDialogVisible"
             custom-class="custom-dialog"
             center>
    <div class="container">
      <el-carousel :interval="10000"
                   type="card"
                   @change="handleCarouselChange">
        <el-carousel-item v-for="(item, index) in algTypeList"
                          :key="item.algTypeId">
          <el-container class="item-container">
            <el-header class="item-header">{{ item.algTypeName }}</el-header>
            <el-main>
              <el-row :gutter="20">
                <el-col :span="8"
                        v-for="model in item.modelList"
                        :key="model.algmodeId">
                  <el-card shadow="hover"
                           @click.native="activeIndex === index && handleCardClick(model)"
                           :class="{ 'disabled-card': activeIndex !== index }">
                    <div class="image-container">
                      <img :src="env + model.preview"
                           class="alg-image"
                           style="width: 100%; height: 180px; object-fit: cover;">
                      <div class="icon-span-box">
                        <span class="icon-span hot">热门</span>
                      </div>
                    </div>
                    <div class="text-container">

                      <div class="text-container">
                        <div class="title-container">
                          <span class="title">{{ model.algmodelName }}</span>
                        </div>
                        <div class="tags">输入：{{ model.algmodelInput }} 输出：{{ model.algmodelOutput }}</div>
                        <div class="description"
                             :title="model.remark ">
                          {{ model.remark }}
                        </div>
                      </div>
                    </div>
                  </el-card>
                </el-col>
              </el-row>
            </el-main>

          </el-container>
        </el-carousel-item>
      </el-carousel>
    </div>
    <!-- 添加模型展示组件 -->
    <alg-model-display v-if="selectedModel"
                       :visible.sync="modelDialogVisible"
                       :model="selectedModel" />
  </el-dialog>

</template>

<script>
import "../js/webrtcstreamer.js" //此处两个js也可全局引用
import "../js/adapter.min.js"
import { getDisplayModel } from "@/api/basedata/algtype";
import AlgModelDisplay from './AlgModelDisPlayComponent.vue'

export default {
  components: {
    AlgModelDisplay
  },
  props: {
  },
  data () {
    return {
      env: process.env.VUE_APP_BASE_API,
      algTypeList: [],
      algTypeDialogVisible: false,
      activeIndex: 0,
      modelDialogVisible: false,
      selectedModel: null
    };
  }, created () {
    this.displayModelList();
  },
  methods: {
    displayModelList () {
      // 获取展示模型列表
      getDisplayModel().then(res => {
        this.algTypeList = [];
        for (const [key, value] of Object.entries(res.data)) {
          this.algTypeList.push({
            algTypeId: key,
            ...value
          });
        }
      })
    },
    handleCardClick (model) {
      this.selectedModel = model;
      this.modelDialogVisible = true;
    },
    handleCarouselChange (index) {
      this.activeIndex = index;
    }
  }
};
</script>

<style lang="scss" scoped>
::v-deep .el-dialog.custom-dialog {
  background: transparent;
  border: rgb(70, 113, 229, 1) 0.5rem;
  backdrop-filter: blur(3px);
  width: 80%;
  height: 80%;
  display: flex;
  flex-direction: column;
}
.container {
  position: absolute; /* 使用绝对定位 */
  width: 100%; /* 容器宽度为父容器的80% */
  height: 100%; /* 容器高度为父容器的80% */
  margin: 0; /* 移除默认的外边距 */
  padding: 0; /* 移除默认的内边距 */
}
.el-carousel {
  height: 100%;
  width: 100%;
  padding: 20px;
  position: relative;
}
::v-deep .el-carousel__container {
  height: 80%;
}

::v-deep .el-carousel__item {
  transition: all 0.4s ease;
  position: absolute;
  left: 50%;
  transform: translateX(-50%) scale(0.9);
  opacity: 0.6;

  &.is-active {
    transform: translateX(-50%) scale(1.05) !important;
    box-shadow: 0 0 30px rgba(64, 158, 255, 0.3);
    z-index: 2;
    opacity: 1;
  }

  &:not(.is-active) {
    &.el-carousel__item--left {
      transform: translateX(-90%) scale(0.9);
    }

    &.el-carousel__item--right {
      transform: translateX(-10%) scale(0.9);
    }
  }
}

// 调整箭头按钮位置
::v-deep .el-carousel__arrow {
  &--left {
    left: 20%;
  }

  &--right {
    right: 20%;
  }
}

.el-carousel__item:nth-child(2n),
.el-carousel__item:nth-child(2n + 1) {
  background: linear-gradient(
    135deg,
    rgba(16, 42, 67, 0.95) 0%,
    rgba(37, 83, 159, 0.95) 100%
  );
  border: 1px solid rgba(87, 157, 255, 0.3);
  border-radius: 20px;
  backdrop-filter: blur(10px);
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
    background: linear-gradient(
      90deg,
      transparent,
      rgba(87, 157, 255, 0.5),
      transparent
    );
  }

  &::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 2px;
    background: linear-gradient(
      90deg,
      transparent,
      rgba(87, 157, 255, 0.5),
      transparent
    );
  }
}

.item-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 20px;
}

.item-header {
  font-size: 24px;
  font-weight: 500;
  padding: 15px 0;
  margin-bottom: 20px;
  border-bottom: 1px solid rgba(87, 157, 255, 0.2);
  background: linear-gradient(90deg, #fff, #88c0ff);
  -webkit-background-clip: text;
  color: transparent;
  text-align: center;
  position: relative;

  &::before,
  &::after {
    content: '';
    position: absolute;
    bottom: -1px;
    width: 30%;
    height: 2px;
  }

  &::before {
    left: 0;
    background: linear-gradient(90deg, transparent, rgba(87, 157, 255, 0.5));
  }

  &::after {
    right: 0;
    background: linear-gradient(-90deg, transparent, rgba(87, 157, 255, 0.5));
  }
}

.el-main {
  height: calc(100% - 80px);
  padding: 0 20px;
}

.el-row {
  height: 100%;
  overflow-y: auto;
  padding-right: 10px;
}

.el-col {
  height: 50%;
  margin-bottom: 20px;
  padding: 10px;
}

.el-card {
  height: 100%;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(87, 157, 255, 0.2);
  backdrop-filter: blur(5px);
  transition: all 0.3s ease;
  display: flex;
  flex-direction: column;

  &:not(.disabled-card):hover {
    transform: translateY(-5px);
    box-shadow: 0 15px 30px rgba(0, 0, 0, 0.2);
    border-color: rgba(87, 157, 255, 0.5);
  }
}

::v-deep .el-card__body {
  padding: 0;
}

.image-container {
  width: 100%;
  height: 45%;
  min-height: 180px;
  position: relative;
  overflow: hidden;
  border-radius: 8px 8px 0 0;
  background: #ffffff;

  .alg-image {
    width: 100%;
    height: 100%;
    object-fit: cover;
    transition: transform 0.3s ease;

    &:hover {
      transform: scale(1.1);
    }
  }

  &::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(to bottom, transparent 70%, rgba(0, 0, 0, 0.5));
    pointer-events: none;
  }
}

.text-container {
  height: 55%;
  padding: 15px;
  display: flex;
  flex-direction: column;

  .title-container {
    margin-bottom: 10px;

    .title {
      font-size: 24px;
      font-weight: bold;
      background: linear-gradient(90deg, #fff, #88c0ff);
      -webkit-background-clip: text;
      color: transparent;
      line-height: 1.4;
      display: block;
      text-align: left;
    }
  }

  .tags {
    margin: 10px 0;
    padding: 5px 10px;
    background: rgba(87, 157, 255, 0.1);
    border-radius: 4px;
    font-size: 12px;
    color: rgba(255, 255, 255, 0.8);
    text-align: left;
  }

  .description {
    color: rgba(255, 255, 255, 0.8);
    font-size: 12px;
    line-height: 1.5;
    height: 3em;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    margin-bottom: 10px;
    text-align: left;
  }
}

.el-col {
  margin-bottom: 20px;
  height: fit-content;
}

.icon-span-box {
  display: flex;
  position: absolute;
  left: 0;
  bottom: 0;
  font-size: 0.8rem;
  line-height: 1.83334em;
  font-weight: 600;
  color: #ffffff;
}
.hot {
  background-color: #d80000;
  padding: 0 0.5em;
}
.icon-box {
  transform: translate(0, -50%);
  position: absolute;
  top: 0;
  right: 20px;
}

.disabled-card {
  pointer-events: none;
  opacity: 0.7;
}

::v-deep .el-dialog__headerbtn {
  font-size: 24px;
  width: 40px;
  height: 40px;
  right: 10px;
  top: 10px;
}

::v-deep .el-dialog__close {
  color: #fff;
  font-weight: bold;

  &:hover {
    color: #409eff;
  }
}

::v-deep .el-carousel__indicators--outside {
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  margin: 0;
  padding: 0;
  height: auto;
  background: transparent;

  .el-carousel__button {
    width: 30px;
    height: 4px;
    border-radius: 2px;
    background: rgba(255, 255, 255, 0.2);
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;

    &::after {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: linear-gradient(90deg, #409eff, #88c0ff);
      opacity: 0;
      transition: opacity 0.3s ease;
    }
  }

  .el-carousel__indicator {
    padding: 12px 4px;

    &.is-active {
      .el-carousel__button {
        background: transparent;

        &::after {
          opacity: 1;
        }
      }
    }

    &:hover {
      .el-carousel__button {
        transform: scaleX(1.2);
      }
    }
  }
}
</style>
