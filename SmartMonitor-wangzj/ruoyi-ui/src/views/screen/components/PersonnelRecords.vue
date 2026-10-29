<template>
  <div class="personnel-records">
    <div class="record-list"
        
         ref="recordList">
      <div v-if="!displayRecords.length"
           class="empty-tip">
        暂无人员
      </div>
      <div class="record-item"
           v-for="(record, index) in displayRecords"
           :key="index">
        <div class="record-avatar">
          <img :src="getImageUrl(record.detectionImg)"
               alt="检测图片"
               @click="showImagePreview(record.detectionImg)"
               class="clickable-image" />
        </div>
        <div class="record-info">
          <div class="record-name">{{ record.userName }}</div>
          <div class="record-title">{{ record.location || '未知位置' }}</div>
          <div class="record-details">
            <span class="time">检测时间: {{ record.time }}</span>
            <span class="confidence">相似度: {{ record.confidence }}</span>
            <span class="duration">停留时长: {{ record.duration }}</span>
          </div>
        </div>
      </div>
    </div>
    <!-- 图片预览模态框 -->
    <div class="image-preview"
         v-if="previewVisible"
         @click="closePreview">
      <div class="preview-content">
        <img :src="getImageUrl(previewImage)"
             alt="预览图片" />
      </div>
    </div>
  </div>
</template>

<script>
import { getTodayEvents } from "@/api/algdeployment/face_recognition_events/index";

export default {
  name: 'PersonnelRecords',
  data () {
    return {
      records: [],
      currentIndex: 0,
      scrollInterval: null,
      pollInterval: null,  // 添加轮询定时器
      previewVisible: false,
      previewImage: '',
      listHeight: 0
    }
  },
  computed: {
    displayRecords () {
      // 按时间倒序排列
      return [...this.records].sort((a, b) => {
        return new Date(b.recognition_time) - new Date(a.recognition_time)
      })
    }
  },
  mounted () {
    this.getRecords()
    this.startPolling()
    this.calculateListHeight()
    window.addEventListener('resize', this.calculateListHeight)
  },
  beforeDestroy () {
    this.stopPolling()
    window.removeEventListener('resize', this.calculateListHeight)
  },
  methods: {
    calculateListHeight () {
      // 获取父容器高度并减去padding
      const containerHeight = this.$el.clientHeight
      this.listHeight = containerHeight - 20 // 减去上下padding各10px
    },
    getImageUrl (base64) {
      if (!base64) {
        return '';
      }
      try {
        // 检查是否已经是完整的data URL
        if (base64.startsWith('data:image')) {
          return base64;
        }
        // 检查是否是有效的base64字符串
        const validBase64 = /^([A-Za-z0-9+/]{4})*([A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{2}==)?$/;
        if (validBase64.test(base64)) {
          return `data:image/jpeg;base64:${base64}`;
        }
        return '';
      } catch (error) {
        console.error('Invalid image data:', error);
        return '';
      }
    },
    // 格式化时间
    formatTime (time) {
      if (!time) return '';
      const date = new Date(time);
      const hours = date.getHours().toString().padStart(2, '0');
      const minutes = date.getMinutes().toString().padStart(2, '0');
      const seconds = date.getSeconds().toString().padStart(2, '0');
      return `${hours}:${minutes}:${seconds}`;
    },
    async getRecords () {
      try {
        const res = await getTodayEvents()
        if (res.code === 200) {
          this.records = res.data.map(item => ({
            id: item.id,
            location: item.deviceName || '未知位置',
            recognition_time: item.recognition_time, // 保存原始时间戳用于排序
            time: this.formatTime(item.recognition_time),
            detectionImg: item.detection_img || '',
            userName: item.faceName,
            confidence: (item.confidence * 100).toFixed(1) + '%',
            duration: this.formatDuration(item.recognition_time, item.departure_time)
          }))
        }
      } catch (error) {
        console.error('获取记录失败:', error)
      }
    },
    formatDuration (startTime, endTime) {
      if (!startTime || !endTime) return '未知';
      const start = new Date(startTime);
      const end = new Date(endTime);
      const diff = Math.floor((end - start) / 1000); // 转换为秒
      if (diff < 60) {
        return diff + '秒';
      } else {
        const minutes = Math.floor(diff / 60);
        const seconds = diff % 60;
        return `${minutes}分${seconds}秒`;
      }
    },
    // 开始轮询
    startPolling () {
      this.pollInterval = setInterval(() => {
        this.updateRecords()
      }, 30000) // 每30秒轮询一次
    },
    // 停止轮询
    stopPolling () {
      if (this.pollInterval) {
        clearInterval(this.pollInterval)
        this.pollInterval = null
      }
    },
    // 更新记录
    async updateRecords () {
      try {
        const res = await getTodayEvents()
        if (res.code === 200) {
          const newRecords = res.data.map(item => ({
            id: item.id,
            location: item.deviceName || '未知位置',
            recognition_time: item.recognition_time, // 保存原始时间戳用于排序
            time: this.formatTime(item.recognition_time),
            detectionImg: item.detection_img || '',
            userName: item.faceName,
            confidence: (item.confidence * 100).toFixed(1) + '%',
            duration: this.formatDuration(item.recognition_time, item.departure_time)
          }))

          // 比较新旧数据，只更新变化的部分
          if (JSON.stringify(newRecords) !== JSON.stringify(this.records)) {
            // 保存当前滚动位置
            const currentRecord = this.records[this.currentIndex]

            // 更新数据
            this.records = newRecords

            // 如果当前显示的记录还存在，保持其显示位置
            if (currentRecord) {
              const newIndex = this.records.findIndex(record =>
                record.id === currentRecord.id
              )
              if (newIndex !== -1) {
                this.currentIndex = newIndex
              } else {
                this.currentIndex = 0
              }
            }
          }
        }
      } catch (error) {
        console.error('更新记录失败:', error)
      }
    },
    showImagePreview (imageData) {
      this.previewImage = imageData
      this.previewVisible = true
    },
    closePreview () {
      this.previewVisible = false
      this.previewImage = ''
    }
  }
}
</script>

<style lang="scss" scoped>
.personnel-records {
  height: 100%;
  padding: 10px;
  position: relative;
  box-sizing: border-box;

  .record-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
    overflow-y: auto;
    position: absolute;
    top: 10px;
    left: 10px;
    right: 10px;
    bottom: 10px;

    &::-webkit-scrollbar {
      width: 4px;
    }

    &::-webkit-scrollbar-thumb {
      background: rgba(0, 149, 255, 0.2);
      border-radius: 2px;

      &:hover {
        background: rgba(0, 149, 255, 0.4);
      }
    }

    &::-webkit-scrollbar-track {
      background: rgba(0, 40, 85, 0.1);
      border-radius: 2px;
    }

    .empty-tip {
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      color: rgba(255, 255, 255, 0.6);
      font-size: 2rem;
      letter-spacing: 1px;
    }
  }

  .record-item {
    min-height: 70px;
    flex-shrink: 0; // 防止项目被压缩
    display: flex;
    align-items: center;
    padding: 10px;
    background: rgba(0, 40, 85, 0.3);
    border: 1px solid rgba(0, 149, 255, 0.2);
    border-radius: 4px;

    .record-avatar {
      width: 50px;
      height: 50px;
      border-radius: 4px;
      overflow: hidden;
      margin-right: 12px;
      border: 1px solid rgba(0, 149, 255, 0.3);

      img {
        width: 100%;
        height: 100%;
        object-fit: cover;
      }

      .clickable-image {
        cursor: pointer;
      }
    }

    .record-info {
      flex: 1;

      .record-name {
        color: #fff;
        font-size: 14px;
        margin-bottom: 4px;
        font-weight: 500;
      }

      .record-title {
        color: #fff;
        font-size: 14px;
        margin-bottom: 4px;
        color: rgba(255, 255, 255, 0.8);
      }

      .record-details {
        color: rgba(255, 255, 255, 0.6);
        font-size: 12px;
        display: flex;
        gap: 10px;

        .time {
          color: #00bfff;
        }

        .confidence {
          color: #52c41a;
        }

        .duration {
          color: #ffd700;
        }
      }
    }
  }

  .image-preview {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.8);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1000;
    cursor: pointer;

    .preview-content {
      max-width: 90%;
      max-height: 90%;

      img {
        max-width: 100%;
        max-height: 90vh;
        object-fit: contain;
        border: 2px solid rgba(0, 149, 255, 0.3);
        border-radius: 4px;
      }
    }
  }
}
</style> 