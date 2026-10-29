<template>
  <el-dialog :close-on-click-modal="false"
             append-to-body
             :title="dialogMainTitle + dialogSubTitle"
             :visible.sync="reIdDialogVisible"
             custom-class="custom-dialog"
             :before-close="handleClose"
             center>
    <!------------------------设备选择表格 start--------------------------------->
    <div class="table-container">
      <el-table v-loading="loading"
                :data="machineList"
                @selection-change="handleSelectionChange"
                height="100%"
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
    <!------------------------设备选择表格 end--------------------------------->
    <span slot="footer"
          class="dialog-footer">
      <el-button @click="reIdDialogVisible = false;cleanAllData()"><i class="el-icon-close">取 消</i></el-button>
      <el-popconfirm ref="tipConfim"
                     :confirm-button-text="'语音查找'"
                     :cancel-button-text="'图像查找'"
                     :cancel-button-type="'primary'"
                     icon="el-icon-search"
                     icon-color="red"
                     title="请选择以下查找方式？"
                     @confirm="voiceMethod"
                     @cancel="imgMethod">
        <el-button type="warning"
                   slot="reference"><i class="el-icon-setting">选择查找方式</i></el-button>
      </el-popconfirm>

      <el-button type="primary"
                 @click="startFinding()"><i class="el-icon-search">开始查找</i></el-button>
    </span>
    <!---------------------------------------------------------图像上传dialog ------------------------------------------------------------------>
    <el-dialog append-to-body
               :close-on-click-modal="false"
               title="上传图像"
               :visible.sync="uploadImgDialogVisible"
               custom-class="img-dialog"
               center>
      <!---------------------图片选择 start--------------------------------->
      <div class="table-container">
        <el-upload class="upload-demo"
                   action="#"
                   :on-remove="handleRemove"
                   :file-list="imgList"
                   list-type="picture"
                   :before-upload="handleBeforeUpload"
                   :show-file-list="true"
                   multiple>
          <el-button type="primary"
                     style=" font-size:1.2rem">选择图片</el-button>
          <div slot="tip"
               style="color:#fff; font-size:1.2rem">只能上传jpg/png文件</div>
        </el-upload>
      </div>
      <!------------------------图片选择 end--------------------------------->
      <span slot="footer"
            class="dialog-footer">
        <el-button @click="uploadImgDialogVisible = false"><i class="el-icon-close">取 消</i></el-button>

        <el-button type="primary"
                   @click="handleUpload"><i class="el-icon-check">确定</i></el-button>
      </span>
    </el-dialog>
    <!---------------------------------------------------------图像上传dialog end------------------------------------------------------------------>

    <!---------------------------------------------------------语音上传dialog ------------------------------------------------------------------>
    <el-dialog append-to-body
               :close-on-click-modal="false"
               title="语音识别"
               :visible.sync="voiceDialogVisible"
               custom-class="voice-dialog"
               center>
      <!---------------------语音识别 start--------------------------------->
      <div class="table-container">
        <voice-recognition-component ref="voiceRecognitionComponent"></voice-recognition-component>
      </div>
      <!------------------------语音识别 end--------------------------------->
      <span slot="footer"
            class="dialog-footer">
        <el-button @click="voiceDialogVisible = false"><i class="el-icon-close">取 消</i></el-button>

        <el-button type="primary"
                   @click="handVoiceToText"><i class="el-icon-check">确定</i></el-button>
      </span>
    </el-dialog>
    <!---------------------------------------------------------语音识别dialog end------------------------------------------------------------------>

    <!---------------------------------------------------------结果返回dialog ------------------------------------------------------------------>
    <el-dialog append-to-body
               :close-on-click-modal="false"
               title="查找结果"
               :visible.sync="resultDialogVisible"
               custom-class="result-dialog"
               :fullscreen="true"
               center
               @close="closeResultDialog">
      <!---------------------视频查找结果 start--------------------------------->
      <div class="result-container">
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
      </div>
      <!------------------------视频查找结果 end--------------------------------->
    </el-dialog>
    <!---------------------------------------------------------结果返回dialog end------------------------------------------------------------------>
  </el-dialog>

</template>

<script>
import { listMachine } from "@/api/basedata/machine";
import VoiceRecognitionComponent from './voiceRecognitionComponent.vue';
import { reidSearch } from "@/api/screen/reid";
import VideoPlayer from './VideoPlayer.vue';
import VideoSection from './VideoSection.vue';
import "../js/webrtcstreamer.js" //此处两个js也可全局引用
import "../js/adapter.min.js"
export default {
  props: {
    funcCode: String,
  },
  components: {
    VideoPlayer,
    VoiceRecognitionComponent,
    VideoSection
  },
  data () {
    return {
      videoSrc: [],
      streamType: [],
      //选择查找方式
      findingMethod: {},
      //设备选择
      ids: [],
      //弹窗主标题
      dialogMainTitle: "",
      //弹窗子标题
      dialogSubTitle: "(当前未配置查找方式!)",
      //上传图像
      imgList: [],
      // 存储 base64 编码的图片数组
      urlList: [],
      voiceText: '',
      reIdDialogVisible: false,
      uploadImgDialogVisible: false,
      voiceDialogVisible: false,
      resultDialogVisible: false,
      statusMap: {
        1: '在线',
        0: '离线',
        2: '检修中...'
      },
      isvalidMap: {
        1: '是',
        0: '否'
      },
      loading: true,
      machineList: [],
      total: 0,
      queryParams: {
        pageNum: 1,
        pageSize: 10,
        machineName: null,
        status: null,
      }
    };
  }, created () {

  },
  methods: {
    /* ************* 图像上传************ */
    // 处理文件移除
    handleRemove (file, fileList) {
      this.imgList = fileList;
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
    // 处理文件上传
    handleUpload () {
      if (this.imgList.length > 0) {
        // 如果 imgList 不为空，关闭弹窗
        this.$nextTick(() => {
          this.setSubTitle(this.findingMethod)
          this.uploadImgDialogVisible = false;
        })

      } else {
        // 如果 imgList 为空，提示用户还未选择图片
        this.$confirm('您还未选择图片，是否继续选择?', '提示', {
          confirmButtonText: '继续选择',
          cancelButtonText: '取消',
          type: 'warning'
        }).then(() => {
          // 如果用户选择继续选择，不做任何操作，保持弹窗打开
        }).catch(() => {
          // 如果用户选择取消，关闭弹窗
          this.$nextTick(() => {
            if (this.imgList.length == 0) {
              this.dialogSubTitle = "(当前未配置查找方式!)"
            }
            this.uploadImgDialogVisible = false;
          })
        });
      }
    },

    //语音查找
    voiceMethod () {
      this.findingMethod = { code: 2, text: "语音查找" }
      this.voiceDialogVisible = true
    },
    //传递语音转文本信息
    handVoiceToText () {
      var text = this.$refs.voiceRecognitionComponent.transcript
      if (text != null || text != '') {
        // 如果 imgList 不为空，关闭弹窗
        this.$nextTick(() => {
          this.voiceText = text
          this.findingMethod = { code: 2, text: "语音查找" }
          this.setSubTitle(this.findingMethod)
          this.voiceDialogVisible = false;
        })

      } else {
        // 如果 imgList 为空，提示用户还未选择图片
        this.$confirm('您还未生成语音，是否继续选择?', '提示', {
          confirmButtonText: '继续选择',
          cancelButtonText: '取消',
          type: 'warning'
        }).then(() => {
          // 如果用户选择继续选择，不做任何操作，保持弹窗打开
        }).catch(() => {
          // 如果用户选择取消，关闭弹窗
          this.$nextTick(() => {
            if (text == null || text == '') {
              this.dialogSubTitle = "(当前未配置查找方式!)"
            }
            this.voiceDialogVisible = false;
          })
        });
      }

    },
    //图像查找
    imgMethod () {
      this.findingMethod = { code: 1, text: "图像查找" }
      this.uploadImgDialogVisible = true
    },
    //
    setSubTitle (val) {
      this.dialogSubTitle = "(当前已选择——" + val.text + ")"
    },
    //开始查找
    startFinding () {
      var length = this.ids.length
      if (length == 0) {
        this.$message({
          message: '请先选择要查找的设备!',
          type: 'warning'
        });
      } else if (length > 16) {
        this.$message({
          message: '最大只支持16分路，请重新选择!',
          type: 'warning'
        });
      } else {
        if (JSON.stringify(this.findingMethod) === '{}') {
          this.$message({
            message: '请先选择查找方式（图片或语音）!',
            type: 'warning'
          });
        } else {
          //ToDo:判断当前选择的查找方式，并将选择的设备ID集合以及选择的查找方式所对应的参数传递到后端
          let params = {
            machineIds: this.ids, // 设备ID集合
            method: this.findingMethod.code, // 查找方式的代码
            voiceText: this.findingMethod.code === 2 ? this.voiceText : null, // 如果是语音查找，则传递语音文本

            imgList: this.findingMethod.code === 1 ? this.imgList : null, // 如果是图像查找，则传递图像数组

            urlList: this.urlList
          };
          this.videoSrc = this.urlList
          this.videoSrc.forEach((videoUrl, index) => {
            // 根据 videoUrl 设置 streamType，这里只是一个示例
            const streamType = this.determineStreamType(videoUrl);
            this.streamType[index] = streamType
            const videoPlayerRef = this.$refs['videoPlayer_' + index]
            if (videoPlayerRef) {
              videoPlayerRef.forEach(player => {
                player.initXgPlayer(streamType);
              });
            }
          });
          this.resultDialogVisible = true
          console.log(this.videoSrc)
          // reidSearch(params).then(response => {
          //   this.videoSrc = this.urlList
          //   this.resultDialogVisible = true

          // }).catch(error => {
          //   // 处理错误情况
          //   console.error('Search failed:', error);
          // });
        }
      }
    },
    determineStreamType (videoUrl) {
      // 根据 videoUrl 确定 streamType
      const url = videoUrl.toLowerCase(); // 转换 URL 为小写
      if (url.includes('rtsp') || url.includes('rtmp') || url.includes('flv')|| url.includes('http') ) {
        return 'flv';
      } else if (url.includes('m3u8') || url.includes('hls') ) {
        return 'hls';   // HLS 类型
      } else if (url.includes('mp4')) {
        return 'mp4';   // MP4 类型
      }
      return 'unknown';  // 如果无法识别的格式，返回 'unknown'
    },
    //传递选择设备ids
    handleSelectionChange (selection) {
      this.ids = selection.map(item => item.machineId)
      this.urlList = selection.map(item => item.videoUrl)
    },
    getList () {
      this.loading = true;
      listMachine(this.queryParams).then(response => {
        this.machineList = response.rows;
        this.total = response.total;
        this.loading = false;
      });
    },
    async cleanAllData () {
      this.dialogSubTitle = "(当前未配置查找方式!)"
      this.findingMethod = {}
      this.cleanChooseImg()
      this.cleanVoiceText()
      this.cleanChooseMachine()
    },
    handleClose (done) {
      this.$confirm('确认关闭？')
        .then(_ => {
          this.$nextTick(() => {
            this.cleanAllData()
          })
          done();
        })
        .catch(_ => { });
    },
    cleanChooseImg () {
      this.imgList = []
    },
    cleanVoiceText () {
      this.voiceText = ''
      if (this.$refs.voiceRecognitionComponent != undefined) {
        this.$refs.voiceRecognitionComponent.transcript = ''
      }
    },
    cleanChooseMachine () {
      if (this.$refs.machineTable != undefined) {
        this.$refs.machineTable.clearSelection();
      }
      this.ids = []
      this.urlList = []
    },
    getGridClass (count) {
      // 计算列数和行数，使得布局为正方形
      let size = Math.ceil(Math.sqrt(count));
      return `grid-${size}-${size}`;
    },
    closeResultDialog () {
      // 遍历所有的视频播放器并断开连接
      this.resultDialogVisible = false;
      this.videoSrc.forEach((src, index) => {
        const videoPlayerRef = this.$refs['videoPlayer_' + index]
        if (videoPlayerRef) {
          videoPlayerRef.forEach(player => {
            player.destoryPlayer();
          });
        }
      });
    },
  }
};
</script>

<style lang="scss" scoped>
::v-deep .custom-dialog {
  background: linear-gradient(
    135deg,
    rgba(16, 42, 67, 0.95) 0%,
    rgba(37, 83, 159, 0.95) 100%
  );
  backdrop-filter: blur(10px);
  border: 1px solid rgba(87, 157, 255, 0.3);
  width: 80% !important;
  margin-top: 8vh !important;

  .el-dialog__body {
    height: calc(100vh - 250px);
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

        // 装饰性小图标
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

/* 按钮样式优化 */
.dialog-footer {
  .el-button {
    height: 40px;
    padding: 0 25px;
    font-weight: 500;
    letter-spacing: 1px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

    &:not(.el-button--primary):not(.el-button--warning) {
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

    &.el-button--warning {
      background: linear-gradient(135deg, #e6a23c, #f3d19e);
      border: none;
      color: white;

      &:hover {
        background: linear-gradient(135deg, #eaab4c, #f5d7ae);
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(230, 162, 60, 0.3);
      }
    }

    i {
      margin-right: 6px;
      font-size: 16px;
      vertical-align: middle;
    }
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

/* 上传组件样式 */
::v-deep .img-dialog,
::v-deep .voice-dialog {
  background: linear-gradient(
    135deg,
    rgba(16, 42, 67, 0.95) 0%,
    rgba(37, 83, 159, 0.95) 100%
  );
  backdrop-filter: blur(10px);
  width: 500px !important;
  margin-top: 15vh !important;

  .el-dialog__body {
    height: auto;
    min-height: 300px;
  }

  .el-upload {
    .el-button {
      background: linear-gradient(135deg, #409eff, #88c0ff);
      border: none;
      color: #fff;

      &:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(64, 158, 255, 0.3);
      }
    }
  }

  .el-upload-list {
    color: #fff;

    &__item {
      background-color: rgba(255, 255, 255, 0.1);
      border: 1px solid rgba(87, 157, 255, 0.2);

      &:hover {
        background-color: rgba(64, 158, 255, 0.1);
      }
    }
  }
}

/* 结果弹窗样式 */
::v-deep .result-dialog {
  background: linear-gradient(
    135deg,
    rgba(16, 42, 67, 0.95) 0%,
    rgba(37, 83, 159, 0.95) 100%
  );
  backdrop-filter: blur(10px);
  border: 1px solid rgba(87, 157, 255, 0.3);
  width: 100% !important; // 改为100%宽度
  height: 100vh !important; // 改为100vh高度
  margin: 0 !important; // 移除margin

  .el-dialog__header {
    padding: 20px 30px;

    .el-dialog__title {
      font-size: 24px; // 加大标题字号
      font-weight: 600; // 加粗
      background: linear-gradient(90deg, #fff, #88c0ff);
      -webkit-background-clip: text;
      color: transparent;
      text-shadow: 0 0 10px rgba(64, 158, 255, 0.3);
      letter-spacing: 2px;

      &::before {
        content: '';
        display: inline-block;
        width: 4px;
        height: 24px;
        background: #409eff;
        margin-right: 10px;
        vertical-align: middle;
        border-radius: 2px;
        box-shadow: 0 0 10px rgba(64, 158, 255, 0.5);
      }
    }
  }

  .el-dialog__body {
    height: calc(100vh - 120px); // 调整高度
    padding: 20px 30px;
  }

  .result-container {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: rgba(0, 0, 0, 0.2);
    border-radius: 12px;
    border: 1px solid rgba(87, 157, 255, 0.2);
  }

  .video-container {
    flex: 1;
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 20px;
    overflow: hidden;
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
  gap: 20px; // 增加间距
  padding: 20px;
  background: rgba(0, 0, 0, 0.1);
  border-radius: 8px;
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

/* 表格容器布局 */
::v-deep .el-table {
  flex: 1;
  overflow: hidden;

  .el-table__body-wrapper {
    overflow-y: auto;
    height: calc(100% - 40px);
  }
}

/* 分页布局调整 */
.pagination-container {
  margin-top: 20px;
  padding: 10px 0;
  border-top: 1px solid rgba(87, 157, 255, 0.1);
}

/* 视频播放器容器样式 */
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
</style>
