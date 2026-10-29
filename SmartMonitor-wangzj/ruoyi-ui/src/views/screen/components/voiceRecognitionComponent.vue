<template>
  <div class="audio-capture">
    <div v-if="isRecording && !isPaused"
         class="recording-animation">
      正在 <br> 识别
    </div>
    <div>
      <button class="button start"
              @click="startRecording"
              v-if="!isRecording || isPaused">开始新录音识别</button>
      <button class="button pause"
              @click="pauseRecording"
              v-if="isRecording && !isPaused">暂停录音</button>
      <button class="button resume"
              @click="resumeRecording"
              v-if="isPaused">继续录音</button>
      <button class="button stop"
              @click="stopRecording"
              v-if="isRecording || isPaused">结束录音</button>
    </div>
    <div class="text-content">
      <el-input type="textarea"
                :rows="4"
                placeholder="语音识别结果将显示在这里"
                v-model="transcript"
                class="input-content">
      </el-input>
    </div>
    <audio :src="audioUrl"
           controls
           v-if="audioUrl"></audio>
    <p v-if="errorMessage"
       class="error">{{ errorMessage }}</p>
  </div>
</template>

<script>
export default {
  data () {
    return {
      // 组件的数据属性
      isRecognitionActive: false, // 添加一个标志位来跟踪语音识别是否已经启动
      mediaRecorder: null, // 媒体录制器
      audioChunks: [], // 音频片段
      audioUrl: '', // 音频URL
      recognition: null, // 语音识别器
      transcript: '', // 识别结果
      errorMessage: '', // 错误信息
      isRecording: false, // 是否正在录音
      isPaused: false, // 是否暂停
      audioContext: null, // 音频上下文
      analyser: null, // 分析器
      source: null, // 音频源
      animationId: null, // 动画ID
    };
  },
  methods: {
    /**
     * 启动录音和语音识别
     */
    async startRecording () {
      this.transcript = ''; // 清空之前的识别结果
      // 检查浏览器是否支持媒体设备和音频捕获功能
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert('该浏览器不支持音频捕获功能。');
        return;
      }
      // 检查浏览器是否支持语音识别功能
      if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        alert('该浏览器不支持语音识别功能。');
        return;
      }
      try {
        // 请求用户媒体权限，获取音频流
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        this.mediaRecorder = new MediaRecorder(stream); // 创建媒体录制器
        this.audioChunks = []; // 清空之前的音频片段

        // 当有音频数据可用时，将其添加到音频片段数组
        this.mediaRecorder.ondataavailable = (event) => {
          this.audioChunks.push(event.data);
        };

        // 当录制停止时，将音频片段合并为一个Blob对象，并创建一个URL
        this.mediaRecorder.onstop = () => {
          const audioBlob = new Blob(this.audioChunks, { type: 'audio/wav' });
          this.audioUrl = URL.createObjectURL(audioBlob);
        };

        this.mediaRecorder.start(); // 开始录制
        this.startRecognition(); // 启动语音识别

        // 创建音频上下文和分析器，用于音频可视化
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        this.analyser = this.audioContext.createAnalyser();
        this.source = this.audioContext.createMediaStreamSource(stream);
        this.source.connect(this.analyser);

        this.isRecording = true; // 设置录音状态为正在录音
        this.isPaused = false; // 设置暂停状态为非暂停
        this.monitorVolume(); // 监控音量

      } catch (error) {
        console.error('获取麦克风权限失败:', error);
        // 根据不同的错误类型设置错误信息
        if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
          this.errorMessage = '麦克风访问被拒绝，请检查浏览器设置并启用麦克风权限。';
        } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
          this.errorMessage = '未找到麦克风设备，请连接麦克风并重试。';
        } else {
          this.errorMessage = '发生未知错误，请重试。';
        }
      }
    },
    /**
     * 暂停录音
     */
    pauseRecording () {
      if (this.mediaRecorder && this.isRecording) {
        this.mediaRecorder.pause(); // 暂停媒体录制器
        if (this.recognition) {
          this.recognition.stop(); // 停止语音识别
        }
        this.isPaused = true; // 设置暂停状态为暂停
      }
    },
    /**
     * 继续录音
     */
    resumeRecording () {
      if (this.mediaRecorder && this.isPaused) {
        this.mediaRecorder.resume(); // 继续媒体录制器
        if (this.recognition) {
          this.recognition.start(); // 启动语音识别
        }
        this.isPaused = false; // 设置暂停状态为非暂停
      }
    },
    /**
     * 监控麦克风音量
     */
    monitorVolume () {
      const bufferLength = this.analyser.fftSize; // 获取FFT大小
      const dataArray = new Uint8Array(bufferLength); // 创建一个Uint8Array数组来存储音量数据

      // 定义一个函数来检查音量
      const checkVolume = () => {
        this.analyser.getByteTimeDomainData(dataArray); // 获取当前时间域数据
        let sum = 0; // 用于计算音量的总和
        for (let i = 0; i < bufferLength; i++) {
          sum += (dataArray[i] - 128) * (dataArray[i] - 128); // 计算音量
        }
        const volume = Math.sqrt(sum / bufferLength); // 计算音量的平方根

        if (volume > 1) {
          this.isRecording = true; // 如果音量大于1，设置录音状态为正在录音
          if (this.recognition && !this.isPaused) {
            this.recognition.start(); // 启动语音识别
          }
        } else {
          this.isRecording = false; // 如果音量不大于1，设置录音状态为非录音
        }

        this.animationId = requestAnimationFrame(checkVolume); // 递归调用checkVolume函数
      };

      checkVolume(); // 调用checkVolume函数
    },
    /**
     * 启动语音识别
     */
    startRecognition () {
      if ((window.SpeechRecognition == undefined && window.SpeechRecognition == null) || (window.webkitSpeechRecognition == undefined && window.webkitSpeechRecognition == null)) {
        this.recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)(); // 创建语音识别器

      }

      this.recognition.lang = 'zh-CN'; // 设置语言为中文
      this.recognition.continuous = true; // 设置为连续识别
      this.recognition.interimResults = true; // 设置为临时结果
      // 当有识别结果时，更新识别结果
      this.recognition.onresult = (event) => {
        let interimTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcriptPart = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            this.transcript += transcriptPart; // 如果是最终结果，添加到transcript
          } else {
            interimTranscript += transcriptPart; // 如果是临时结果，添加到interimTranscript
          }
        }
      };

      // 当发生错误时，打印错误信息
      this.recognition.onerror = (event) => {
        console.error('Recognition error:', event.error);
      };

      // 当识别结束时，如果正在录音且未暂停，则重新开始识别
      this.recognition.onend = () => {
        if (this.recognition && this.isRecording && !this.isPaused) {
          this.recognition.start();
        }
      };

      this.recognition.start(); // 开始语音识别
    },
    /**
     * 停止录音
     */
    stopRecording () {
      if (this.mediaRecorder) {
        this.mediaRecorder.stop(); // 停止媒体录制器
      }
      if (this.recognition) {
        this.recognition.stop(); // 停止语音识别
      }
      if (this.audioContext) {
        this.audioContext.close(); // 关闭音频上下文
      }
      cancelAnimationFrame(this.animationId); // 取消动画帧
      this.isRecording = false; // 设置录音状态为非录音
      this.isPaused = false; // 设置暂停状态为非暂停
    },
  },
  /**
   * 在组件销毁前，关闭音频上下文和取消动画帧
   */
  beforeDestroy () {
    if (this.audioContext) {
      this.audioContext.close();
    }
    cancelAnimationFrame(this.animationId);
  },
};
</script>

<style scoped lang="scss">
.audio-capture {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  background-color: transparent;
  audio {
    margin-top: 20px;
  }

  .error {
    color: red;
    margin-top: 20px;
  }

  .recording-animation {
    width: 60px;
    height: 60px;
    background-color: #f44336;
    border-radius: 50%;
    animation: pulse 1.2s infinite;
    margin: 20px auto;
    text-align: center;
    color: white;
    font-size: 14px;
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 10px;
    cursor: pointer;
  }

  @keyframes pulse {
    0% {
      transform: scale(0.95);
      box-shadow: 0 0 0 10px rgba(255, 0, 0, 0.5);
    }
    70% {
      transform: scale(1);
      box-shadow: 0 0 0 20px rgba(255, 0, 0, 0);
    }
    100% {
      transform: scale(0.95);
      box-shadow: 0 0 0 0 rgba(255, 0, 0, 0);
    }
  }
}
.button {
  padding: 10px 20px;
  font-size: 16px;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  margin: 15px;
}

.start {
  background-color: #4caf50;
  color: white;
}

.pause {
  background-color: #f44336;
  color: white;
}

.resume {
  background-color: #ffc107;
  color: white;
}

.stop {
  background-color: #607d8b;
  color: white;
}

/* 添加鼠标悬停效果 */
.button:hover {
  opacity: 0.8;
  box-shadow: 0 0 0 5px rgb(255, 255, 255);
}

.text-content {
  display: flex;
  justify-content: center;
  line-height: 30px;
  text-indent: 32px;
  width: 100%;
  background-color: transparent;
  margin-top: 10px;
  height: 100%;
  overflow-y: auto;
}
::v-deep .el-textarea__inner {
  color: #fff;
  width: 100% !important;
  height: 100% !important;
  background-color: transparent;
}
</style>

