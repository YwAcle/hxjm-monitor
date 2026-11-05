<template>
  <div class="alg-display-container">
    <div class="content-layout">
      <!-- 左侧算法类型列表 -->
      <div class="type-list">
        <div class="type-header">算法类型</div>
        <div class="type-items">
          <div v-for="(item, index) in algTypeList"
               :key="item.algTypeId"
               class="type-item"
               :class="{ active: activeIndex === index }"
               @click="handleTypeClick(index)">
            {{ item.algTypeName }}
          </div>
        </div>
      </div>

      <!-- 右侧算法展示区 -->
      <div class="model-display">
        <div class="model-header">
          {{ currentType ? currentType.algTypeName : '请选择算法类型' }}
        </div>
        <div class="model-content"
             v-if="currentType">
          <el-container class="item-container">
            <el-main>
              <el-row :gutter="20">
                <el-col :span="8"
                        v-for="model in currentType.modelList"
                        :key="model.algmodeId">
                  <el-card shadow="hover"
                           @click.native="handleCardClick(model)">
                    <div class="image-container">
                      <img :src="env + model.preview"
                           class="alg-image"
                           style="width: 100%; height: 180px; object-fit: cover;">
                      <div class="icon-span-box">
                        <span class="icon-span hot">热门</span>
                      </div>
                    </div>
                    <div class="text-container">
                      <div class="title-container">
                        <span class="title">{{ model.algmodelName }}</span>
                      </div>
                      <div class="tags">输入：{{ model.algmodelInput }} 输出：{{ model.algmodelOutput }}</div>
                      <div class="description"
                           :title="model.remark">{{ model.remark }}</div>
                    </div>
                  </el-card>
                </el-col>
              </el-row>
            </el-main>
          </el-container>
        </div>
      </div>
    </div>

    <!-- 模型展示对话框 -->
    <alg-model-display v-if="selectedModel"
                       :visible.sync="modelDialogVisible"
                       :model="selectedModel" />
  </div>
</template>

<script>
import { getDisplayModel } from "@/api/basedata/algtype"
import AlgModelDisplay from './components/AlgModelDisPlayComponent.vue'

export default {
  name: 'AlgDisplay',
  components: {
    AlgModelDisplay
  },
  data () {
    return {
      env: process.env.VUE_APP_BASE_API,
      algTypeList: [],
      activeIndex: 0,
      modelDialogVisible: false,
      selectedModel: null
    }
  },
  computed: {
    currentType () {
      return this.algTypeList[this.activeIndex] || null
    }
  },
  created () {
    this.displayModelList()
  },
  methods: {
    // 获取展示模型列表
    displayModelList () {
      getDisplayModel().then(res => {
        this.algTypeList = []
        for (const [key, value] of Object.entries(res.data)) {
          this.algTypeList.push({
            algTypeId: key,
            ...value
          })
        }
      })
    },

    handleCardClick (model) {
      this.selectedModel = model
      this.modelDialogVisible = true
    },

    handleTypeClick (index) {
      this.activeIndex = index
    }
  }
}
</script>

<style lang="scss" scoped>
.alg-display-container {
  position: relative;
  width: 100%;
  height: 100vh;
  background: linear-gradient(
    90deg,
    rgba(0, 40, 85, 0.95),
    rgba(0, 80, 170, 0.95),
    rgba(0, 60, 130, 0.95)
  );
  padding: 20px;
}

.content-layout {
  display: flex;
  height: 100%;
  gap: 20px;
}

.type-list {
  flex: 1;
  border-radius: 12px;
  border: 1px solid rgba(87, 157, 255, 0.2);
  backdrop-filter: blur(5px);
  display: flex;
  flex-direction: column;
}

.type-header {
  padding: 20px;
  font-size: 20px;
  font-weight: bold;
  color: #fff;
  text-align: center;
  border-bottom: 1px solid rgba(87, 157, 255, 0.2);
}

.type-items {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
}

.type-item {
  padding: 15px 20px;
  color: rgba(255, 255, 255, 0.8);
  cursor: pointer;
  border-radius: 8px;
  margin-bottom: 8px;
  transition: all 0.3s ease;

  &:hover {
    background: rgba(87, 157, 255, 0.1);
  }

  &.active {
    background: rgba(87, 157, 255, 0.2);
    color: #fff;
    font-weight: bold;
  }
}

.model-display {
  flex: 4;
  border-radius: 12px;
  border: 1px solid rgba(87, 157, 255, 0.2);
  backdrop-filter: blur(5px);
  display: flex;
  flex-direction: column;
}

.model-header {
  padding: 20px;
  font-size: 24px;
  font-weight: bold;
  color: #fff;
  text-align: center;
  border-bottom: 1px solid rgba(87, 157, 255, 0.2);
}

.model-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.item-container {
  height: 100%;
  padding: 0;
}

.item-header {
  font-size: 24px;
  font-weight: 500;
  color: #fff;
  text-align: center;
  padding: 20px 0;
  position: relative;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
  height: 80px;
  line-height: 40px;
}

.el-main {
  height: 100%;
  padding: 0 20px;
  overflow-y: auto;
}

::v-deep .el-row {
  height: 100%;
  display: flex;
  flex-wrap: wrap;
  align-content: flex-start;
}

::v-deep .el-col {
  margin-bottom: 20px;
  height: 400px;
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

.disabled-card {
  pointer-events: none;
  opacity: 0.7;
}
</style>
