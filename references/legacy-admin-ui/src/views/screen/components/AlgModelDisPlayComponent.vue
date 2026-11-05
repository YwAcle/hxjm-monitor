<template>
  <div>
    <el-drawer :visible.sync="modelDialogVisible"
               :with-header="false"
               size="100%"
               direction="rtl"
               :append-to-body="true"
               custom-class="custom-drawer"
               :before-close="handleDrawerClose">
      <div class="model-container">
        <div class="model-header">
          <div class="title-box">
            <div class="title-line"></div>
            <span class="title-text">{{ model.algmodelName }}</span>
          </div>
          <el-button class="close-btn"
                     icon="el-icon-close"
                     circle
                     @click="handleDrawerClose"></el-button>
        </div>
        <div class="model-content">
          <el-row :gutter="20">
            <el-col :span="8">
              <div class="info-group">
                <div class="info-header">基本信息</div>
                <div class="info-content"
                     style="height: calc(100vh - 260px); overflow-y: auto;">
                  <div class="info-item">
                    <span class="info-label">算法名称</span>
                    <span class="info-value">{{ model.algmodelName }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">算法引擎</span>
                    <span class="info-value">{{ model.algmodelEngines || '暂无数据' }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">输入/输出格式</span>
                    <div class="format-container">
                      <div class="format-tag">
                        <span class="format-label">输入</span>
                        <span class="format-type"
                              :class="getFormatClass(model.algmodelInput)">
                          {{ formatText(model.algmodelInput) }}
                        </span>
                      </div>
                      <div class="format-divider"></div>
                      <div class="format-tag">
                        <span class="format-label">输出</span>
                        <span class="format-type"
                              :class="getFormatClass(model.algmodelOutput)">
                          {{ formatText(model.algmodelOutput) }}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div class="info-item">
                    <span class="info-label">算法介绍</span>
                    <p class="info-desc">{{ model.remark || '暂无介绍' }}</p>
                  </div>
                  <div class="info-item">
                    <span class="info-label">设备选择</span>
                    <div class="machine-selection">
                      <el-button type="primary"
                                 size="small"
                                 icon="el-icon-plus"
                                 @click="openMachineDialog">
                        选择设备
                      </el-button>

                      <div class="selected-machines"
                           v-if="selectedMachines.length > 0">
                        <el-tag v-for="machine in selectedMachines"
                                :key="machine.machineId"
                                closable
                                type="info"
                                class="machine-tag"
                                @close="removeMachine(machine)">
                          {{ machine.machineName }}
                        </el-tag>
                      </div>
                      <div v-else
                           class="no-machine-tip">
                        暂未选择设备
                      </div>
                    </div>
                  </div>
                  <div class="info-item">
                    <span class="info-label">已上传图片</span>
                    <template v-if="isImageType">
                      <el-upload class="upload-demo"
                                 action="#"
                                 :on-remove="handleRemove"
                                 :file-list="imgList"
                                 list-type="picture"
                                 :before-upload="handleBeforeUpload"
                                 :show-file-list="true"
                                 multiple>
                        <el-button size="small"
                                   type="primary">选择图片</el-button>
                        <div slot="tip"
                             class="el-upload__tip">只能上传jpg/png文件</div>
                      </el-upload>
                    </template>
                    <template v-else-if="isVideoType">
                      <div class="video-tip">请先选择设备，然后点击运行按钮开始处理</div>
                    </template>
                  </div>
                </div>
                <div class="action-section">
                  <el-button type="primary"
                             size="medium"
                             class="run-button"
                             :loading="uploading"
                             @click="handleRun">
                    <i class="el-icon-video-play"></i>
                    {{ uploading ? '运行中...' : '运行' }}
                  </el-button>
                  <!-- <el-button v-if="uploading"
                             type="warning"
                             size="medium"
                             class="interrupt-button"
                             @click="handleInterrupt">
                    <i class="el-icon-warning"></i>
                    取消处理
                  </el-button> -->
                  <el-button v-if="uploading && videoSrc.length > 0"
                             type="danger"
                             size="medium"
                             class="stop-button"
                             @click="handleStop">
                    <i class="el-icon-video-pause"></i>
                    停止演示
                  </el-button>
                  <span class="upload-tip"
                        v-if="model.algmodelInput">
                    支持上传{{ formatText(model.algmodelInput) }}文件
                  </span>
                </div>
              </div>
            </el-col>
            <el-col :span="16">
              <div class="preview-area">
                <div class="preview-title">算法演示</div>
                <div class="preview-content"
                     ref="previewContent">
                  <template v-if="videoSrc.length > 0">
                    <div class="video-container">
                      <div :class="getGridClass(videoSrc.length)">
                        <VideoPlayer v-for="(videoUrl, index) in videoSrc"
                                     :key="videoUrl + index"
                                     :videoUrl="videoUrl"
                                     :index="index"
                                     :streamType="streamType[index]"
                                     :ref="`videoPlayer_${index}`" />
                      </div>
                    </div>
                  </template>
                  <template v-else-if="previewImages.length > 0">
                    <div class="preview-grid"
                         :class="getGridClass(previewImages.length)">
                      <div v-for="(image, index) in previewImages"
                           :key="index"
                           class="preview-item">
                        <el-image :src="image.src"
                                  :alt="image.name"
                                  fit="contain"
                                  :preview-src-list="previewSrcList"
                                  :initial-index="index">
                          <div slot="error"
                               class="image-slot">
                            <i class="el-icon-picture-outline"></i>
                          </div>
                        </el-image>
                        <div class="image-info">
                          <span class="image-name">{{ image.name }}</span>
                        </div>
                      </div>
                    </div>
                  </template>
                  <div v-else
                       class="placeholder-text">
                    算法演示区域
                  </div>
                </div>
              </div>
            </el-col>
          </el-row>
        </div>
      </div>
    </el-drawer>
    <el-dialog :close-on-click-modal="false"
               append-to-body
               title="选择设备"
               :visible.sync="machineDialogVisible"
               custom-class="custom-dialog"
               center>
      <div class="table-container">
        <el-table v-loading="loading"
                  :data="machineList"
                  @selection-change="handleSelectionChange"
                  height="calc(100% - 70px)"
                  ref="machineTable">
          <el-table-column type="selection"
                           width="55"
                           align="center" />
          <el-table-column label="主键"
                           align="center"
                           prop="machineId" />
          <el-table-column label="设备编码"
                           align="center"
                           prop="machineCode" />
          <el-table-column label="设备名称"
                           align="center"
                           prop="machineName" />
          <el-table-column label="设备流"
                           align="center"
                           prop="videoUrl"
                           show-tooltip-when-overflow>
            <template slot-scope="scope">
              <span>{{ scope.row.videoUrl }}</span>
            </template>
          </el-table-column>
          <el-table-column label="分辨率"
                           align="center"
                           prop="resolution"></el-table-column>
          <el-table-column label="解码器"
                           align="center"
                           prop="decoder"></el-table-column>
          <el-table-column label="设备状态"
                           align="center"
                           prop="status">
            <template slot-scope="scope">
              {{ statusMap[scope.row.status] }}
            </template>
          </el-table-column>
          <el-table-column label="启用标志"
                           align="center"
                           prop="isvalid">
            <template slot-scope="scope">
              {{ isvalidMap[scope.row.isvalid] }}
            </template>
          </el-table-column>
        </el-table>
        <pagination v-show="total>0"
                    :total="total"
                    :page.sync="queryParams.pageNum"
                    :limit.sync="queryParams.pageSize"
                    @pagination="getList" />
      </div>
      <span slot="footer"
            class="dialog-footer">
        <el-button @click="machineDialogVisible = false;cleanChooseMachine()">
          <i class="el-icon-close">取 消</i>
        </el-button>
        <el-button type="primary"
                   @click="confirmMachineselection">
          <i class="el-icon-check">确 定</i>
        </el-button>
      </span>
    </el-dialog>
  </div>
</template>
<script>
import { listMachine } from "@/api/basedata/machine";  // 确保引入了相关API
import { runAlgorithmModel, runReIDAlgorithm,runPoseEstimationAlgorithm,stopPoseEstimationAlgorithm, stopReIDAlgorithm } from '@/api/algorithm'
import config from '@/config'
import VideoPlayer from './VideoPlayer.vue';

export default {
  components: {
    VideoPlayer
  },
  name: 'AlgModelDisplay',
  props: {
    visible: {  // 父组件传入的 visible
      type: Boolean,
      default: false
    },
    model: {
      type: Object,
      required: true
    }
  },
  data () {
    return {
      streamServiceUrls: [],
      env: process.env.VUE_APP_BASE_API,
      selectedModel: null,
      uploading: false,
      uploadedFiles: [], // 存储上传的文件
      imgList: [], // 存储图片列表
      selectedMachines: [], // 存储选中的设备
      loading: false,
      machineList: [],
      total: 0,
      queryParams: {
        pageNum: 1,
        pageSize: 10,  // 可以调整每页显示数量
        machineName: null,
        status: null,
      },
      statusMap: {
        1: '在线',
        0: '离线',
        2: '检修中...'
      },
      isvalidMap: {
        1: '是',
        0: '否'
      },
      machineDialogVisible: false,
      tempSelectedMachines: [], // 临时存储选中的设备
      algorithmServiceUrl: config.algorithmServiceUrl,
      previewImages: [], // 存储预览图片数据
      streamServiceUrl: config.streamServiceUrl,
      videoSrc: [], // 存储视频源
      streamType: [], // 存储视频流类型
      reidMachineStatus: null, // 存储 ReID 机器状态
      poseStatus: null, // 存储姿态估计算法机器状态c
    }
  },
  created () {
  },
  computed: {
    modelDialogVisible: {
      get () {
        return this.visible
      },
      set (val) {
        this.$emit('update:visible', val)
      }
    },
    isImageType () {
      return this.model.algmodelInput?.toLowerCase().includes('image') || this.model.algmodelInput?.toLowerCase().includes('both')
    },
    isVideoType () {
      return this.model.algmodelInput?.toLowerCase().includes('video') || this.model.algmodelInput?.toLowerCase().includes('both')
    },
    // 添加预览图片列表计算属性
    previewSrcList () {
      return this.previewImages.map(img => img.src);
    }
  },
  methods: {
    formatText (type) {
      if (!type) return '未知';
      if (type.toLowerCase().includes('video')) return '视频';
      if (type.toLowerCase().includes('image')) return '图像';
      if (type.toLowerCase().includes('both')) return '图片和视频';
      return type;
    },
    getFormatClass (type) {
      if (!type) return '';
      const lowerType = type.toLowerCase();
      if (lowerType.includes('both')) return 'both-type';
      if (lowerType.includes('video')) return 'video-type';
      if (lowerType.includes('image')) return 'image-type';
      return '';
    },
    handleChange (file, fileList) {
      this.imgList = fileList
    },

    handleRemove (file, fileList) {
      this.imgList = fileList
    },

    async handleRun () {
      if (!this.model) {
        this.$message.error('请选择算法模型')
        return
      }

      if (this.selectedMachines.length === 0) {
        this.$message.warning('请先选择设备');
        return;
      }

      // if (this.isImageType && this.imgList.length === 0) {
      //   this.$message.warning('请先上传图片');
      //   return;
      // }
      // 检查是否是 ReID 算法
      if (this.model.algmodelCode === 'reid') {
        this.handleReIDAlgorithm()
        return
      }else if(this.model.algmodelCode === 'pose_estimation'){
        this.handlePoseEstimationAlgorithm()
        return
        }

      try {

        this.uploading = true;
        this.streamServiceUrls = [];
        this.selectedMachines.forEach((machine, index) => {
          machine.outputStreamUrl = this.streamServiceUrl + '/live.flv?app=live&stream=' + this.model.algmodelCode + '_' + 'machine' + machine.machineId + '/' + new Date().getTime() + index
        })
        // 构建请求数据
        const requestData = {
          modelCode: this.model.algmodelCode,
          modelName: this.model.algmodelName,
          modelType: this.model.algtypeName,
          modelInput: this.model.algmodelInput,
          modelOutput: this.model.algmodelOutput,
          modelPath: this.model.path,
          machines: this.selectedMachines,
          files: this.imgList.map(file => ({
            name: file.name,
            data: file.url
          }))
        };
        console.log(requestData)
        const response = await runAlgorithmModel(requestData);
        if (response.status === 'success') {
          this.$message.success('处理成功');

          if (this.model.algmodelOutput.toLowerCase().includes('video')) {
            // 处理视频输出
            this.videoSrc = this.selectedMachines.map(result => {
              // 替换最后一个/为_
              return result.outputStreamUrl.replace(/\/([^\/]*)$/, '_$1');
            });
            this.videoSrc.forEach((videoUrl, index) => {
              this.streamType[index] = this.determineStreamType(videoUrl);
            });
            this.previewImages = []; // 清空图片预览
          } else {
            // 处理图片输出
            this.previewImages = response.results.map(result => ({
              src: result.imgBase64,
              name: result.file_name
            }));
            this.videoSrc = []; // 清空视频源
          }

        } else {
          this.$message.error(response.message || '处理失败');
        }
      } catch (error) {
        console.error('处理出错:', error);
        this.$message.error('处理出错，请重试');
      } finally {
        this.uploading = false;
      }
    },

    // 处理上传前的文件
    handleBeforeUpload (file) {
      // 获取文件的扩展名
      const extension = file.name.slice((file.name.lastIndexOf(".") + 1)).toLowerCase();
      // 检查文件类型是否为jpg、jpeg或png
      if (extension === 'jpg' || extension === 'jpeg' || extension === 'png') {
        const reader = new FileReader();
        reader.onload = (e) => {
          const base64 = e.target.result;
          // 创建一个文件对象并添加到 imgList 中
          this.imgList.push({
            name: file.name,
            url: base64
          });
        };
        reader.readAsDataURL(file);
      } else {
        this.$message.error('只能上传jpg/png文件！');
      }
      // 阻止文件上传
      return false; // 返回 false 阻止文件上传
    },

    // 获取设备列表
    getList () {
      this.loading = true;
      listMachine(this.queryParams).then(response => {
        this.machineList = response.rows;
        this.total = response.total;
        this.loading = false;
      });
    },

    // 处理设备选择变化
    handleSelectionChange (selection) {
      this.tempSelectedMachines = selection.map(item => ({
        machineId: item.machineId,
        machineCode: item.machineCode,
        machineName: item.machineName,
        videoUrl: item.videoUrl,
        resolution: item.resolution,
        decoder: item.decoder
      }));
    },

    // 清空选择
    cleanChooseMachine () {
      if (this.$refs.machineTable) {
        this.$refs.machineTable.clearSelection();
      }
      this.selectedMachines = [];
      this.tempSelectedMachines = [];
      this.streamServiceUrls = [];
    },

    // 打开设备选弹窗
    openMachineDialog () {
      this.machineDialogVisible = true;
      // 如果设备列表为空，才请求数据
      if (this.machineList.length === 0) {
        this.getList();
      }
      this.tempSelectedMachines = [...this.selectedMachines];
      this.$nextTick(() => {
        // 设置已选设备的选中状态
        this.machineList.forEach(row => {
          if (this.tempSelectedMachines.some(machine => machine.machineId === row.machineId)) {
            this.$refs.machineTable.toggleRowSelection(row, true);
          }
        });
      });
    },

    // 取消设备选择
    cancelMachineselection () {
      this.machineDialogVisible = false;
      this.tempSelectedMachines = [];
    },

    // 确认设备选择
    confirmMachineselection () {
      this.selectedMachines = [...this.tempSelectedMachines];
      this.machineDialogVisible = false;
    },

    // 移除已选设备
    removeMachine (machine) {
      this.selectedMachines = this.selectedMachines.filter(
        item => item.machineId !== machine.machineId
      );
    },

    // 添加清空数据的方法
    cleanUpData () {
      // 清空图片列表
      this.imgList = [];
      // 清空已选设备
      this.selectedMachines = [];
      this.tempSelectedMachines = [];
      // 清空上传状态
      this.uploading = false;
      // 重置分页
      this.queryParams.pageNum = 1;
      this.queryParams.pageSize = 10;
      // 清空设备列表
      this.machineList = [];
      this.total = 0;
      // 关闭设备选择对话框
      this.machineDialogVisible = false;
      // 清空表格选中状态
      if (this.$refs.machineTable) {
        this.$refs.machineTable.clearSelection();
      }
    },

    // 添加抽屉关闭处理方法
    handleDrawerClose () {
      this.$confirm('确认关闭？')
        .then(_ => {
          // 清空所有页面信息
          this.resetPageData();
          // 更新父组件的visible状态
          this.modelDialogVisible = false;
        })
        .catch(_ => { });
    },

    // 重置所有页面数据
    resetPageData () {
      // 清空图片列表
      this.imgList = [];
      // 清空已选设备
      this.selectedMachines = [];
      this.tempSelectedMachines = [];
      this.streamServiceUrls = [];
      // 清空上传状态
      this.uploading = false;
      // 重置分页
      this.queryParams.pageNum = 1;
      this.queryParams.pageSize = 10;
      // 关闭设备选择对话框
      this.machineDialogVisible = false;
      // 清空表格选中状态
      if (this.$refs.machineTable) {
        this.$refs.machineTable.clearSelection();
      }
      // 重置预览区域
      const previewContent = document.querySelector('.preview-content');
      if (previewContent) {
        previewContent.innerHTML = '<div class="placeholder-text">算法演示区域</div>';
      }
      // 重置其他状态
      this.selectedModel = null;
      this.uploadedFiles = [];
      this.cleanupVideoPlayers();
    },

    // 确定视频流类型
    determineStreamType (videoUrl) {
      const url = videoUrl.toLowerCase();
      if (url.includes('rtsp') || url.includes('rtmp') || url.includes('flv')) {
        return 'flv';
      } else if (url.includes('m3u8') || url.includes('hls')) {
        return 'hls';
      } else if (url.includes('mp4')) {
        return 'mp4';
      }
      return 'flv';
    },

    // 添加清理视频播放器的方法
    cleanupVideoPlayers () {
      this.videoSrc.forEach((src, index) => {
        const videoPlayerRef = this.$refs[`videoPlayer_${index}`];
        if (videoPlayerRef) {
          videoPlayerRef.forEach(player => {
            player.destoryPlayer();
          });
        }
      });
      this.videoSrc = [];
      this.streamType = [];
    },

    getGridClass (count) {
      // 计算列数和行数，使得布局为正方形
      let size = Math.ceil(Math.sqrt(count));
      return `grid-${size}-${size}`;
    },

    // 处理姿态估计算法
    handlePoseEstimationAlgorithm() {
      this.uploading = true
      this.videoSrc = [] // 清空之前的视频源
      console.log('姿态估计算法请求设备:', this.selectedMachines)

      // 准备请求数据
      const requestData = {
        machineList: this.selectedMachines.map(machine => ({
          machineId: String(machine.machineId),
          videoUrl: machine.videoUrl,
          resolution: machine.resolution || '1920x1080',
          codec_type: machine.decoder || 'h264'
        }))
      }

      // 使用封装的API方法
      runPoseEstimationAlgorithm(requestData)
        .then(response => {
          if (response.code === 200) {
            this.$message.success('姿态估计算法启动成功')
            // 处理返回的视频流
            if (response.data && Array.isArray(response.data.machines)) {
              // 添加详细日志
              console.log('姿态估计返回的完整数据:', response.data);

              // 从返回数据中提取 rtmpUrl
              this.videoSrc = response.data.machines.map(item => {
                console.log('获取到的RTMP地址:', item.rtmpUrl);
                return item.rtmpUrl;
              });

              this.streamType = this.videoSrc.map(url => {
                const type = this.determineStreamType(url);
                console.log('流地址:', url, '判断的类型:', type);
                return type;
              });

              // 保存机器ID和状态信息，用于后续停止操作
              this.poseStatus = response.data.machines.map(item => ({
                machineId: item.machineId,
                status: item.status,
                streamId: item.streamId // 保存streamId
              }))
            } else {
              this.$message.warning('未收到视频流数据')
              this.uploading = false
            }
          } else {
            this.$message.error(response.msg || '姿态估计算法启动失败')
            this.uploading = false
          }
        })
        .catch(error => {
          this.uploading = false
          this.$message.error('姿态估计算法请求失败: ' + error.message)
        })
    },
    // 修改 ReID 算法处理方法
    handleReIDAlgorithm () {
      this.uploading = true
      this.videoSrc = [] // 清空之前的视频源
      // 处理图片转Base64的异步操作
      Promise.all(this.imgList.map(img => {
        if (img.raw) {
          return this.getBase64FromFile(img.raw).then(base64 => {
            // 返回包含图片名称和base64数据的对象
            return {
              name: img.name || img.raw.name,
              data: base64
            }
          })
        } else if (img.url) {
          // 如果已经有URL（可能是已经上传过的图片）
          return Promise.resolve({
            name: img.name,
            data: img.url.includes('base64,') ? img.url.split('base64,')[1] : img.url
          })
        } else {
          return Promise.resolve(null)
        }
      })).then(imageObjects => {
        // 准备请求数据
        const requestData = {
          machineList: this.selectedMachines.map(machine => ({
            machineId: machine.machineId,
            videoUrl: machine.videoUrl,
            resolution: machine.resolution || '1920x1080',
            codec_type: machine.decoder || 'h264'
          })),
          imgList: imageObjects.filter(img => img !== null).map(img => ({
            name: img.name,
            data: img.data
          }))
        }

        // 使用封装的 API 方法
        return runReIDAlgorithm(requestData)
      }).then(response => {
        if (response.code === 200) {
          this.$message.success('ReID 算法启动成功')
          // 处理返回的视频流
          if (response.data && Array.isArray(response.data.machines)) {
            // 添加详细日志
            console.log('ReID返回的完整数据:', response.data);

            // 从返回数据中提取 rtmpUrl
            this.videoSrc = response.data.machines.map(item => {
              console.log('获取到的RTMP地址:', item.rtmpUrl);
              return item.rtmpUrl;
            });

            this.streamType = this.videoSrc.map(url => {
              const type = this.determineStreamType(url);
              console.log('流地址:', url, '判断的类型:', type);
              return type;
            });

            // 保存机器ID和状态信息，用于后续停止操作
            this.reidMachineStatus = response.data.machines.map(item => ({
              machineId: item.machineId,
              status: item.status,
              streamId: item.streamId // 保存streamId
            }))
          } else {
            this.$message.warning('未收到视频流数据')
            this.uploading = false
          }
        } else {
          this.$message.error(response.msg || 'ReID 算法启动失败')
          this.uploading = false
        }
      }).catch(error => {
        this.uploading = false
        this.$message.error('ReID 算法请求失败: ' + error.message)
      })
    },

    // 修改停止预览方法
    handleStop () {
      if (!this.uploading || this.videoSrc.length === 0) {
        return
      }

      // 如果是 ReID 算法，需要调用停止接口
      if (this.model.algmodelCode === 'reid' && this.reidMachineStatus) {
        const streamIds = this.reidMachineStatus.map(item => item.streamId).filter(id => id)

        if (streamIds.length === 0) {
          this.$message.warning('没有可停止的流')
          this.resetPreviewState()
          return
        }

        // 使用封装的 API 方法调用停止 ReID 接口
        this.uploading = true
        stopReIDAlgorithm(streamIds).then(response => {
          if (response.code === 200) {
            this.$message.success('已停止 ReID 算法')
          } else {
            this.$message.error(response.msg || '停止 ReID 算法失败')
          }
        }).catch(error => {
          this.$message.error('停止 ReID 算法请求失败: ' + error.message)
        }).finally(() => {
          this.resetPreviewState()
        })
      } // 如果是姿态估计算法
      else if (this.model.algmodelCode === 'pose_estimation' && this.poseStatus) {
        const streamIds = this.poseStatus.map(item => item.streamId).filter(id => id)

        if (streamIds.length === 0) {
          this.$message.warning('没有可停止的流')
          this.resetPreviewState()
          return
        }

        // 使用封装的API方法调用停止姿态估计接口
        this.uploading = true
        stopPoseEstimationAlgorithm(streamIds).then(response => {
          if (response.code === 200) {
            this.$message.success('已停止姿态估计算法')
          } else {
            this.$message.error(response.msg || '停止姿态估计算法失败')
          }
        }).catch(error => {
          this.$message.error('停止姿态估计算法请求失败: ' + error.message)
        }).finally(() => {
          this.resetPreviewState()
        })
      }
      else {
        // 其他算法直接重置状态
        this.resetPreviewState()
      }
    },

    // 重置预览状态
    resetPreviewState () {
      this.uploading = false
      this.videoSrc = []
      this.streamType = []
      this.reidMachineStatus = null
      this.poseStatus = null
    },

    // 手动打断处理状态
    handleInterrupt() {
      this.$confirm('确定要取消当前处理吗?', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }).then(() => {
        // 重置处理状态
        this.uploading = false;
        this.$message({
          type: 'success',
          message: '已取消处理'
        });
      }).catch(() => {
        // 用户取消操作，不做任何处理
      });
    },

    // 修改 getBase64FromFile 方法，只返回base64数据部分
    getBase64FromFile (file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.readAsDataURL(file)
        reader.onload = () => {
          // 只返回base64部分，去掉前缀
          const base64Data = reader.result.split('base64,')[1]
          resolve(base64Data)
        }
        reader.onerror = error => reject(error)
      })
    },
  }
}
</script>

<style lang="scss" scoped>
::v-deep .custom-drawer {
  background: linear-gradient(
    90deg,
    rgba(0, 40, 85, 0.95),
    rgba(0, 80, 170, 0.95),
    rgba(0, 60, 130, 0.95)
  );
  backdrop-filter: blur(10px);
  border-left: 1px solid rgba(87, 157, 255, 0.3);
}

.model-container {
  padding: 30px;
  color: #fff;
  height: 100%;
  position: relative;
  overflow-y: auto;

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
}

.model-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
  padding-bottom: 20px;
  border-bottom: 1px solid rgba(87, 157, 255, 0.2);
}

.title-box {
  display: flex;
  align-items: center;
  gap: 15px;
}

.title-line {
  width: 4px;
  height: 24px;
  background: #409eff;
  box-shadow: 0 0 10px rgba(64, 158, 255, 0.5);
}

.title-text {
  font-size: 24px;
  font-weight: 500;
  background: linear-gradient(90deg, #fff, #88c0ff);
  -webkit-background-clip: text;
  color: transparent;
}

.close-btn {
  background: rgba(255, 255, 255, 0.1);
  border: none;
  transition: all 0.3s;

  &:hover {
    background: rgba(255, 255, 255, 0.2);
    transform: rotate(90deg);
  }
}

.model-content {
  padding: 20px;
  height: calc(100vh - 150px);
}

.info-group {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  border: 1px solid rgba(87, 157, 255, 0.2);
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
  backdrop-filter: blur(5px);
  margin-right: 20px;
  display: flex;
  flex-direction: column;
  height: calc(100vh - 200px);
}

.info-header {
  font-size: 18px;
  color: #409eff;
  position: relative;
  padding: 25px 25px 15px 37px;
  border-bottom: 1px solid rgba(87, 157, 255, 0.2);
  flex-shrink: 0; // 防止标题被压缩

  &::before {
    content: '';
    position: absolute;
    left: 25px;
    top: 50%;
    transform: translateY(-50%);
    width: 4px;
    height: 16px;
    background: #409eff;
    border-radius: 2px;
  }
}

.info-content {
  flex: 1;
  overflow-y: auto;
  padding: 25px;
  padding-bottom: 0; // 移除底部padding，为action-section出间

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-thumb {
    background: rgba(87, 157, 255, 0.3);
    border-radius: 3px;
  }

  &::-webkit-scrollbar-track {
    background: rgba(0, 0, 0, 0.1);
    border-radius: 3px;
  }
}

.info-item {
  margin-bottom: 20px;
  padding: 15px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 8px;
  transition: all 0.3s ease;

  &:hover {
    background: rgba(255, 255, 255, 0.05);
    transform: translateX(5px);
    .format-type {
      transform: none;
      box-shadow: none;
    }
  }

  .info-label {
    display: block;
    color: rgba(255, 255, 255, 0.6);
    margin-bottom: 10px;
    font-size: 14px;
    position: relative;
    padding-left: 15px;

    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 50%;
      transform: translateY(-50%);
      width: 6px;
      height: 6px;
      background: #409eff;
      border-radius: 50%;
    }
  }

  .info-value,
  .info-desc {
    color: rgba(255, 255, 255, 0.8);
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 1px;
    background: transparent;
    border: none;
    padding: 0;
  }
}

.preview-area {
  height: calc(100vh - 200px);
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  border: 1px solid rgba(87, 157, 255, 0.2);
  padding: 25px;
  backdrop-filter: blur(5px);
  display: flex;
  flex-direction: column;
}

.preview-title {
  font-size: 18px;
  color: #409eff;
  margin-bottom: 20px;
  position: relative;
  padding-left: 12px;

  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 4px;
    height: 16px;
    background: #409eff;
    border-radius: 2px;
  }
}

.preview-content {
  flex: 1;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 8px;
  position: relative;
  overflow: auto;
  padding: 20px;

  .preview-grid {
    display: grid;
    gap: 20px;
    height: 100%;

    // 单张图片
    &.single {
      grid-template-columns: 1fr;

      .preview-item {
        max-height: calc(100vh - 300px);

        img {
          max-height: 100%;
          margin: auto;
        }
      }
    }

    // 两张图片
    &.double {
      grid-template-columns: repeat(2, 1fr);
    }

    // 三张图片
    &.triple {
      grid-template-columns: repeat(3, 1fr);
    }

    // 四张图片
    &.quad {
      grid-template-columns: repeat(2, 1fr);
      grid-template-rows: repeat(2, 1fr);
    }

    // 多张图片
    &.multi {
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    }
  }

  .preview-item {
    background: rgba(0, 0, 0, 0.2);
    border-radius: 8px;
    padding: 10px;
    display: flex;
    flex-direction: column;
    border: 1px solid rgba(87, 157, 255, 0.2);
    transition: all 0.3s;

    &:hover {
      transform: translateY(-5px);
      box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
      border-color: rgba(87, 157, 255, 0.4);
    }

    img {
      width: 100%;
      height: 100%;
      object-fit: contain;
      border-radius: 4px;
    }

    .image-info {
      margin-top: 10px;
      padding: 8px;
      background: rgba(0, 0, 0, 0.3);
      border-radius: 4px;

      .image-name {
        color: rgba(255, 255, 255, 0.9);
        font-size: 14px;
        display: block;
        text-align: center;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
    }
  }

  .placeholder-text {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    color: rgba(255, 255, 255, 0.4);
    font-size: 40px;
    font-style: italic;
  }
}

.format-container {
  display: flex;
  align-items: center;
  gap: 20px;
}

.format-tag {
  display: flex;
  align-items: center;
  gap: 8px;
}

.format-label {
  color: rgba(255, 255, 255, 0.6);
  font-size: 14px;
}

.format-type {
  padding: 2px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 1px;
  transition: all 0.3s ease;

  &.video-type {
    background: rgba(82, 196, 26, 0.1);
    border: 1px solid rgba(82, 196, 26, 0.3);
    color: #52c41a;
  }

  &.image-type {
    background: rgba(24, 144, 255, 0.1);
    border: 1px solid rgba(24, 144, 255, 0.3);
    color: #1890ff;
  }

  &.both-type {
    background: rgba(250, 173, 20, 0.1);
    border: 1px solid rgba(250, 173, 20, 0.3);
    color: #faad14;
  }
}

.format-divider {
  width: 1px;
  height: 20px;
  background: rgba(255, 255, 255, 0.2);
}

.action-section {
  margin-top: 0;
  padding: 20px 25px !important;
  background: rgba(64, 158, 255, 0.1) !important;
  border-top: 1px solid rgba(87, 157, 255, 0.2);
  display: flex;
  align-items: center;
  gap: 15px;
  flex-shrink: 0; // 防止被压缩
}

.run-button {
  background: linear-gradient(135deg, #409eff, #88c0ff);
  border: none;
  padding: 12px 25px;
  font-size: 14px;
  font-weight: 500;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(64, 158, 255, 0.3);
  }

  i {
    margin-right: 8px;
  }
}

.stop-button {
  background: linear-gradient(135deg, #f56c6c, #f78989);
  border: none;
  padding: 12px 25px;
  font-size: 14px;
  font-weight: 500;
  margin-left: 10px;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(245, 108, 108, 0.3);
  }

  i {
    margin-right: 8px;
  }
}

.upload-tip {
  color: rgba(255, 255, 255, 0.6);
  font-size: 13px;
  font-style: italic;
}

.upload-preview {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 15px;
  margin-top: 10px;
}

.preview-item {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.2);
  aspect-ratio: 16/9;

  &:hover .preview-actions {
    opacity: 1;
  }
}

.preview-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.preview-video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.preview-actions {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  opacity: 0;
  transition: opacity 0.3s;

  i {
    color: #fff;
    font-size: 20px;
    cursor: pointer;
    padding: 8px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.2);

    &:hover {
      background: rgba(255, 255, 255, 0.3);
    }
  }
}

.video-tip {
  color: rgba(255, 255, 255, 0.6);
  font-style: italic;
  padding: 10px 0;
}

.upload-demo {
  ::v-deep .el-upload-list--picture {
    .el-upload-list__item {
      background-color: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(87, 157, 255, 0.2);
      &:hover {
        background-color: rgba(247, 14, 14, 0.1);
      }
      .el-icon-close {
        color: #fff;
      }
      .el-upload-list__item-thumbnail {
        object-fit: cover;
      }

      .el-upload-list__item-name {
        color: rgba(255, 255, 255, 0.8);
      }
    }
  }

  .el-upload__tip {
    color: rgba(255, 255, 255, 0.6);
    font-size: 12px;
    margin-top: 8px;
  }
}

.machine-selection {
  margin-top: 10px;

  .machine-tag {
    margin: 5px;
    background: rgba(64, 158, 255, 0.1);
    border-color: rgba(87, 157, 255, 0.2);
    color: #fff;

    .el-tag__close {
      color: rgba(255, 255, 255, 0.8);
      &:hover {
        background-color: rgba(255, 255, 255, 0.2);
        color: #fff;
      }
    }
  }
}

.selected- {
  margin-top: 10px;
  min-height: 32px;
  padding: 5px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 4px;
  border: 1px solid rgba(87, 157, 255, 0.15);
}

.no-machine-tip {
  margin-top: 10px;
  color: rgba(255, 255, 255, 0.4);
  font-style: italic;
  font-size: 13px;
}

::v-deep .custom-dialog {
  background: linear-gradient(
    135deg,
    rgba(16, 42, 67, 0.95) 0%,
    rgba(37, 83, 159, 0.95) 100%
  );
  backdrop-filter: blur(10px);
  border: 1px solid rgba(87, 157, 255, 0.3);
  width: 80% !important;
  margin-top: 15vh !important;

  .el-dialog__body {
    height: calc(100vh - 400px);
    padding: 20px;
    overflow: hidden;
  }
}

::v-deep .el-dialog__header {
  padding: 20px;
  border-bottom: 1px solid rgba(87, 157, 255, 0.2);
  background: rgba(0, 0, 0, 0.2);

  .el-dialog__title {
    color: #fff;
    font-size: 20px;
    font-weight: 500;
    background: linear-gradient(90deg, #fff, #88c0ff);
    -webkit-background-clip: text;
    color: transparent;
  }

  .el-dialog__headerbtn {
    .el-dialog__close {
      color: rgba(255, 255, 255, 0.8);
      &:hover {
        color: #409eff;
      }
    }
  }
}

::v-deep .el-dialog__body {
  padding: 30px;
  color: #fff;
  background: rgba(0, 0, 0, 0.2);
}

::v-deep .el-dialog__footer {
  padding: 20px;
  border-top: 1px solid rgba(87, 157, 255, 0.2);
  background: rgba(0, 0, 0, 0.2);
}

/* 表格容器样式 */
.table-container {
  background: rgba(255, 255, 255, 0.03);
  border-radius: 12px;
  border: 1px solid rgba(87, 157, 255, 0.2);
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
  backdrop-filter: blur(5px);
  padding: 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
}
/* 表格样式优化 */
::v-deep .el-table {
  flex: 1;
  background-color: transparent !important;

  // 移除默认边框
  &::before,
  &::after {
    display: none;
  }

  // 表头样式
  .el-table__header-wrapper {
    th {
      background: linear-gradient(
        90deg,
        rgba(64, 158, 255, 0.15) 0%,
        rgba(64, 158, 255, 0.25) 50%,
        rgba(64, 158, 255, 0.15) 100%
      );
      backdrop-filter: blur(5px);
      border-bottom: 1px solid rgba(87, 157, 255, 0.3);
      padding: 12px 0;
      height: 50px;
      font-size: 14px;
      font-weight: 500;
      text-align: center;
      position: relative;

      // 科技感文字样式
      .cell {
        background: linear-gradient(90deg, #88c0ff, #409eff);
        -webkit-background-clip: text;
        color: transparent;
        word-break: break-word;
        line-height: 20px;
        text-shadow: 0 0 10px rgba(64, 158, 255, 0.3);
        position: relative;
        font-weight: bold;
        letter-spacing: 1px;

        // 装性小图标
        &::before {
          content: '';
          position: absolute;
          left: -15px;
          top: 50%;
          transform: translateY(-50%);
          width: 4px;
          height: 4px;
          background: #409eff;
          border-radius: 50%;
          box-shadow: 0 0 5px rgba(64, 158, 255, 0.5);
        }
      }

      // 发光边框效果
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
          rgba(64, 158, 255, 0.5),
          transparent
        );
      }
    }
  }

  // 表格内容
  .el-table__body-wrapper {
    background-color: transparent;
    overflow-y: auto;
    height: calc(100% - 50px);

    td {
      background-color: transparent;
      border-bottom: 1px solid rgba(87, 157, 255, 0.08); // 降低边框透明度
      padding: 12px 0;
      height: 50px;
      color: rgba(255, 255, 255, 0.8); // 稍微降低对比度
      text-align: center;

      .cell {
        word-break: break-word;
        line-height: 20px;
      }
    }

    tr {
      background-color: transparent;
      transition: background-color 0.3s;

      &:hover > td {
        background-color: rgba(64, 158, 255, 0.05); // 降低hover背景透明度
      }
    }
  }

  // 选择框样式
  .el-checkbox {
    .el-checkbox__inner {
      background-color: rgba(255, 255, 255, 0.1);
      border-color: rgba(87, 157, 255, 0.3);
      width: 16px;
      height: 16px;

      &:hover {
        border-color: #409eff;
      }

      &::after {
        height: 8px;
        left: 5px;
        width: 3px;
      }
    }

    &.is-checked {
      .el-checkbox__inner {
        background-color: #409eff;
        border-color: #409eff;
      }

      .el-checkbox__label {
        color: #409eff;
      }
    }
  }

  // 空数据样式
  .el-table__empty-block {
    background-color: transparent;
    min-height: 60px;

    .el-table__empty-text {
      color: rgba(255, 255, 255, 0.6);
      font-size: 14px;
    }
  }

  // 修复表格底部边框
  .el-table__body {
    border-collapse: collapse;
    width: 100% !important;
  }

  // 修复表格右侧边框
  .el-table__fixed-right {
    height: 100% !important;
    background-color: transparent;
  }

  // 修复表格滚动条样式
  .el-table__body-wrapper::-webkit-scrollbar {
    width: 6px;
    height: 6px;
  }

  .el-table__body-wrapper::-webkit-scrollbar-thumb {
    background: rgba(87, 157, 255, 0.3);
    border-radius: 3px;
  }

  .el-table__body-wrapper::-webkit-scrollbar-track {
    background: rgba(0, 0, 0, 0.1);
    border-radius: 3px;
  }
}
/* 分页容器和分页样式 */
.pagination-container {
  margin-top: 20px;
  padding: 10px 0;
  background: transparent; // 移除背景色

  ::v-deep .el-pagination {
    text-align: right;

    .btn-prev,
    .btn-next,
    .el-pager li {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(87, 157, 255, 0.15);
      color: rgba(255, 255, 255, 0.8);
      transition: all 0.3s;

      &:hover {
        background-color: rgba(64, 158, 255, 0.05);
        border-color: rgba(87, 157, 255, 0.2);
      }

      &.active {
        background: rgba(64, 158, 255, 0.15);
        border: 1px solid rgba(87, 157, 255, 0.3);
        color: #fff;
      }
    }

    .el-pagination__total,
    .el-pagination__jump {
      color: rgba(255, 255, 255, 0.7);
    }
  }
}

/* 按钮样式优化 */
.dialog-footer {
  .el-button {
    height: 40px;
    padding: 0 25px;
    font-weight: 500;
    letter-spacing: 1px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

    i {
      margin-right: 6px;
      font-size: 16px;
      vertical-align: middle;
    }

    &:not(.el-button--primary) {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(87, 157, 255, 0.2);
      color: rgba(255, 255, 255, 0.9);

      &:hover {
        background: rgba(255, 255, 255, 0.1);
        border-color: rgba(87, 157, 255, 0.4);
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
      }
    }

    &.el-button--primary {
      background: linear-gradient(135deg, #409eff, #88c0ff);
      border: none;
      color: white;

      &:hover {
        background: linear-gradient(135deg, #5aafff, #98c8ff);
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(64, 158, 255, 0.3);
      }
    }
  }
}

// 状态标签样式
.status-tag {
  padding: 2px 8px;
  border-radius: 2px;
  font-size: 12px;

  &.online {
    background-color: rgba(82, 196, 26, 0.1);
    border: 1px solid rgba(82, 196, 26, 0.2);
    color: #52c41a;
  }

  &.offline {
    background-color: rgba(245, 34, 45, 0.1);
    border: 1px solid rgba(245, 34, 45, 0.2);
    color: #f5222d;
  }

  &.maintenance {
    background-color: rgba(250, 173, 20, 0.1);
    border: 1px solid rgba(250, 173, 20, 0.2);
    color: #faad14;
  }
}

.result-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.result-item {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 15px;

  .result-image {
    width: 100%;
    height: auto;
    border-radius: 4px;
  }

  .result-info {
    margin-top: 10px;
    color: rgba(255, 255, 255, 0.9);

    .result-name {
      font-size: 14px;
      margin-bottom: 5px;
    }

    .result-detail {
      font-size: 12px;
      color: rgba(255, 255, 255, 0.7);
    }
  }
}

// 优化预览弹窗样式
::v-deep .el-image-viewer__wrapper {
  .el-image-viewer__mask {
    background: rgba(0, 0, 0, 0.9);
    backdrop-filter: blur(10px);
  }

  .el-image-viewer__btn {
    background: rgba(0, 0, 0, 0.3);
    border-radius: 50%;
    padding: 8px;

    i {
      font-size: 20px;
      color: #fff;
    }

    &:hover {
      background: rgba(64, 158, 255, 0.3);
      transform: scale(1.1);
    }
  }

  .el-image-viewer__close {
    width: 40px;
    height: 40px;
    top: 20px;
    right: 20px;

    &:hover {
      transform: rotate(90deg);
    }
  }

  .el-image-viewer__canvas {
    img {
      border-radius: 8px;
      box-shadow: 0 0 30px rgba(0, 0, 0, 0.3);
    }
  }

  .el-image-viewer__actions {
    padding: 15px;
    background: rgba(0, 0, 0, 0.5);
    border-radius: 20px;
    backdrop-filter: blur(5px);

    .el-image-viewer__actions__inner {
      i {
        font-size: 18px;
        color: #fff;
        margin: 0 10px;

        &:hover {
          color: #409eff;
          transform: scale(1.1);
        }
      }
    }
  }
}

.video-container {
  width: 100%;
  height: 100%;
  display: grid;


  &.single {
    grid-template-columns: 1fr;
  }

  &.double {
    grid-template-columns: repeat(2, 1fr);
  }

  &.triple {
    grid-template-columns: repeat(3, 1fr);
  }

  &.quad {
    grid-template-columns: repeat(2, 1fr);
    grid-template-rows: repeat(2, 1fr);
  }

  &.multi {
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  }
}

::v-deep .video-player {
  width: 100%;
  height: 100%;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
  border: 1px solid rgba(87, 157, 255, 0.2);

  &:hover {
    transform: scale(1.01);
    transition: transform 0.3s ease;
  }
}

/* 网格布局样式优化 */
.grid-1-1,
.grid-2-2,
.grid-3-3,
.grid-4-4 {
  width: 100%;
  height: 100%;
  display: grid;
  gap: 20px;


}

.grid-1-1 {
  grid-template-columns: 1fr;
  grid-template-rows: 1fr;
}

.grid-2-2 {
  grid-template-columns: repeat(2, 1fr);
  grid-template-rows: repeat(2, 1fr);
}

.grid-3-3 {
  grid-template-columns: repeat(3, 1fr);
  grid-template-rows: repeat(3, 1fr);
}

.grid-4-4 {
  grid-template-columns: repeat(4, 1fr);
  grid-template-rows: repeat(4, 1fr);
}

.preview-content {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 12px;
  border: 1px solid rgba(87, 157, 255, 0.2);

  .video-container {
    flex: 1;
    display: flex;
    justify-content: center;
    align-items: center;
    overflow: hidden;
  }

  .preview-grid {
    width: 100%;
    height: 100%;
    display: grid;
    gap: 20px;
    padding: 20px;
  }

  .preview-item {
    position: relative;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
    border: 1px solid rgba(87, 157, 255, 0.2);

    &:hover {
      transform: scale(1.01);
      transition: transform 0.3s ease;
    }

    .el-image {
      width: 100%;
      height: 100%;
      object-fit: contain;
    }
  }
}
</style>
