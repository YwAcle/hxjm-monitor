<template>
  <div>
    <button @click="startRecognition">开始语音识别</button>
    <p>识别结果：{{ transcript }}</p>
  </div>
</template>
<script>
export default {
  data() {
    return {
      transcript: '', // 存储识别结果
    };
  },
  methods: {
    startRecognition() {
      if ('SpeechRecognition' in window) {
        const recognition = new SpeechRecognition();
        recognition.lang = 'zh-CN'; // 设置识别语言为中文

        // 识别开始事件
        recognition.onstart = () => {
          console.log('语音识别开始');
        };

        // 识别结果事件
        recognition.onresult = (event) => {
          const resultValue = event.results[0][0].transcript;
          this.transcript = resultValue; // 更新识别结果
        };

        // 识别结束事件
        recognition.onend = () => {
          console.log('语音识别结束');
        };

        // 错误处理
        recognition.onerror = (event) => {
          console.error('语音识别错误：', event.error);
        };

        recognition.start(); // 启动语音识别
      } else {
        alert('当前浏览器不支持语音识别');
      }
    },
  },
};
</script>
