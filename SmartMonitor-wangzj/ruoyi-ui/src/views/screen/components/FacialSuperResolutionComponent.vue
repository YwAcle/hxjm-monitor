<template>
  <el-dialog :close-on-click-modal="false"
             append-to-body
             :title="dialogMainTitle + dialogSubTitle"
             :visible.sync="dialogVisible"
             custom-class="custom-dialog"
             :before-close="handleClose"
             center>
    <span slot="footer"
          class="dialog-footer">
      <el-button @click="dialogVisible = false;cleanAllData()"><i class="el-icon-close">取 消</i></el-button>
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
      dialogVisible: false,
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
      console.log(videoUrl)
      const url = videoUrl.toLowerCase(); // 转换 URL 为小写
      if (url.includes('rtsp') || url.includes('rtmp') || url.includes('flv')) {
        return 'flv';
      } else if (url.includes('m3u8') || url.includes('hls')) {
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
::v-deep .el-dialog.custom-dialog {
  background: rgba(30, 120, 238, 0.2) !important;
  border: rgb(70, 113, 229, 1) 0.5rem;
  backdrop-filter: blur(3px);
  width: 60%;
  height: 60%;
  display: flex;
  flex-direction: column;
  margin-top: 20vh !important;
}
::v-deep .el-dialog__header {
  color: #fff;
  background: rgba(0, 0, 0, 0.5);
  text-align: center;
  box-shadow: 0 0 1vw rgb(70, 113, 229, 1) inset;
  background: linear-gradient(#2807e4, hsl(249, 98%, 50%)) left top,
    linear-gradient(#2807e4, hsl(249, 98%, 50%)) left top,
    linear-gradient(#2807e4, hsl(249, 98%, 50%)) right top,
    linear-gradient(#2807e4, hsl(249, 98%, 50%)) right top;
  background-repeat: no-repeat;
  background-size: 2px 20px, 20px 2px;
  text-align: left;
}
::v-deep .el-dialog__title {
  line-height: 24px;
  font-size: 1.5rem;
  color: white;
}
::v-deep .el-dialog__headerbtn {
  font-size: 1.5rem;

  .el-dialog__close {
    color: white;
  }
}
::v-deep .el-dialog__body {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  overflow: auto; /* 如果内容过多，可以滚动 */
  padding: 20px;
  color: #fff;
  background: rgba(0, 0, 0, 0.5);
  text-align: left;
  // box-shadow: 0 0 1vw rgb(70, 113, 229, 1) inset;
  box-shadow: 1vw 0 1vw -1vw rgba(70, 113, 229, 1) inset,
    0 1vw 1vw -1vw rgba(70, 113, 229, 1) inset,
    -1vw 0 1vw -1vw rgba(70, 113, 229, 1) inset;
  background-repeat: no-repeat;
  background-size: 2px 20px, 20px 2px;
}

::v-deep .el-dialog__footer {
  box-shadow: -1vw 1vw 1vw -1vw rgba(70, 113, 229, 1) inset,
    1vw 1vw 1vw -1vw rgba(70, 113, 229, 1) inset,
    0 -1vw 1vw -1vw rgba(70, 113, 229, 1) inset;
  background: linear-gradient(#2807e4, hsl(249, 98%, 50%)) left bottom,
    linear-gradient(#2807e4, hsl(249, 98%, 50%)) left bottom,
    linear-gradient(#2807e4, hsl(249, 98%, 50%)) right bottom,
    linear-gradient(#2807e4, hsl(249, 98%, 50%)) right bottom;
  background-repeat: no-repeat;
  background-size: 2px 20px, 20px 2px;
}

/**更改el-table样式 */
.table-container {
  width: 100%;
  height: 80%;
}

.pagination-container {
  background: transparent;
}
::v-deep .el-pagination.is-background .el-pagination__total {
  color: #fff;
}

/* 最外层透明 */
::v-deep .el-table,
::v-deep .el-table__expanded-cell {
  background-color: transparent;
}
/* 表格内背景颜色 */
::v-deep .el-table th,
::v-deep .el-table tr,
::v-deep .el-table td {
  background-color: transparent;
  color: #fff;
}
/* 给表格侧边加边框 */
::v-deep .el-table {
  border-left: 1px solid #fff; /* 左侧边框 */
  border-right: 1px solid #fff; /* 右侧边框 */
}

/* 如果需要，也可以给表格顶部和底部添加边框 */
::v-deep .el-table__header-wrapper {
  border-top: 1px solid #fff; /* 顶部边框 */
}

::v-deep .el-table__body-wrapper::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
}
/* 去除每一行数据的边框 */
::v-deep .el-table th,
::v-deep .el-table td {
  border-bottom: none; /* 去除单元格底部边框 */
}

/* 去除行之间的边框 */
::v-deep .el-table tr {
  border: none; /* 去除行边框 */
}

/* 去除鼠标悬停时的高亮 */
::v-deep .el-table .el-table__body tr:hover > td {
  background-color: transparent; /* 去除悬停背景色 */
}

::v-deep .el-dialog.img-dialog {
  background: rgba(30, 120, 238, 0.2) !important;
  border: rgb(70, 113, 229, 1) 0.5rem;
  backdrop-filter: blur(3px);
  width: 30%;
  height: 40%;
  display: flex;
  flex-direction: column;
  margin-top: 30vh !important;
}
::v-deep .el-dialog.voice-dialog {
  background: rgba(30, 120, 238, 0.2) !important;
  border: rgb(70, 113, 229, 1) 0.5rem;
  backdrop-filter: blur(3px);
  width: 30%;
  height: 40%;
  display: flex;
  flex-direction: column;
  margin-top: 30vh !important;
}

::v-deep .el-dialog.result-dialog {
  background: rgba(30, 120, 238, 0.2) !important;
  border: rgb(70, 113, 229, 1) 0.5rem;
  backdrop-filter: blur(3px);
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.result-container {
  display: flex;
  flex-direction: row;
  width: 100%;
  height: 100%;
}
.video-container {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
}
.grid-1-1 {
  display: grid;
  grid-template-columns: repeat(1, 1fr); /* 创建4列 */
  grid-template-rows: repeat(1, 1fr); /* 创建4行 */
  grid-gap: 10px; /* 网格间距 */
  width: 80%; /* 容器宽度 */
  height: 80%; /* 容器高度 */
}

.grid-2-2 {
  display: grid;
  grid-template-columns: repeat(2, 1fr); /* 创建4列 */
  grid-template-rows: repeat(2, 1fr); /* 创建4行 */
  grid-gap: 10px; /* 网格间距 */
  width: 100%; /* 容器宽度 */
  height: 100%; /* 容器高度 */
}

.grid-3-3 {
  display: grid;
  grid-template-columns: repeat(3, 1fr); /* 创建4列 */
  grid-template-rows: repeat(3, 1fr); /* 创建4行 */
  grid-gap: 10px; /* 网格间距 */
  width: 100%; /* 容器宽度 */
  height: 100%; /* 容器高度 */
}

.grid-4-4 {
  display: grid;
  grid-template-columns: repeat(4, 1fr); /* 创建4列 */
  grid-template-rows: repeat(4, 1fr); /* 创建4行 */
  grid-gap: 10px; /* 网格间距 */
  width: 100%; /* 容器宽度 */
  height: 100%; /* 容器高度 */
}
</style>
