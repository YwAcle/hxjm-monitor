<!-- VideoPlayer.vue -->
<template>

  <div class="video-player">
    <!-- xgplayer容器 -->
    <div :id="'xgPlayerContainer-' + index"
         class="xgplayer-container"></div>
  </div>

</template>

<script>

// 引入 Video.js 和 Flash 插件
import Player from 'xgplayer';
import FlvPlayer from 'xgplayer-flv';;
import HlsPlayer from 'xgplayer-hls';
import 'xgplayer/dist/index.min.css';
export default {
  props: {
    index: {
      type: Number,
      required: true
    },
    videoUrl: {
      type: String,
      required: true
    }, streamType: {
      type: String,
      required: true
    }
  },
  data () {
    return {
      xgPlayer: null,
      videoElement: null,
      streamer: null
    };
  },
  mounted () {
    this.initXgPlayer(this.streamType);
  },
  methods: {
    //初始化播放器实例
    initXgPlayer (streamType) {
      console.log("Initializing player with:", {
        streamType,
        videoUrl: this.videoUrl
      });

      let playerConfig = {}
      if (streamType === 'flv') {
        // 处理 RTMP 和 FLV 流
        const url = this.videoUrl;
        console.log('播放器收到URL:', url);
        
        // 如果是 RTMP 流，转换为对应的 HTTP-FLV 地址
        if (url.startsWith('rtmp://')) {
          // 先记录原始的RTMP地址
          console.log('原始RTMP地址:', url);
          
          let flvUrl = url;
          
          // 检查特定格式并转换
          if (url.includes('/live/')) {
            // 标准转换
            flvUrl = url.replace('rtmp://', 'http://')
              .replace('1935', '82')
              .replace('/live/', '/live.flv?app=live&stream=');
          } else if (url.includes('app=') && url.includes('stream=')) {
            // 已经包含app和stream参数的情况
            const urlParts = url.split('rtmp://')[1].split('/');
            const hostPart = urlParts[0];
            const queryPart = url.split('?')[1] || '';
            
            flvUrl = `http://${hostPart}/live.flv?${queryPart}`;
          } else {
            // 其他格式，尝试特殊处理
            // 提取域名部分
            const domain = url.split('rtmp://')[1].split('/')[0];
            // 提取最后的路径部分作为stream名称
            const streamName = url.split('/').pop();
            flvUrl = `http://${domain}/live.flv?app=live&stream=${streamName}`;
          }

          console.log('转换后的HTTP-FLV地址:', flvUrl);

          playerConfig = {
            id: 'xgPlayerContainer-' + this.index,
            url: flvUrl,
            volume: 0.6,
            autoplay: true,
            playsinline: true,
            isLive: true,
            cors: true,
            width: '100%',
            height: '100%',
            type: 'flv',
            plugins: [FlvPlayer],
            config: {
              hasAudio: false,
              hasVideo: true,
              cors: true,
              withCredentials: false,
              isLive: true,
              enableStashBuffer: false,
              stashInitialSize: 128,
              flv: {
                mediaDataSource: {
                  type: 'flv',
                  isLive: true,
                  cors: true,
                  withCredentials: false,
                  hasAudio: false,
                  hasVideo: true,
                  videoCodec: 'H264',
                  config: {
                    lazyLoadMaxDuration: 0,
                    enableWorker: true,
                    enableStashBuffer: false,
                    stashInitialSize: 128,
                    isLive: true
                  }
                }
              }
            }
          };
        } else {
          // 直接使用 FLV 流，同样禁用音频
          playerConfig = {
            id: 'xgPlayerContainer-' + this.index,
            url: this.videoUrl,
            volume: 0.6,
            autoplay: true,
            playsinline: true,
            isLive: true,
            cors: true,
            width: '100%',
            height: '100%',
            type: 'flv',
            plugins: [FlvPlayer],
            config: {
              hasAudio: false,
              hasVideo: true,
              cors: true,
              withCredentials: false,
              isLive: true,
              enableStashBuffer: false,
              stashInitialSize: 128
            }
          };
        }

        this.xgPlayer = new Player(playerConfig);

        // 添加更详细的错误处理
        this.xgPlayer.on('error', (err) => {
          console.error('Player error:', {
            error: err,
            message: err.message,
            errorType: err.errorType,
            errorDetails: err.errorDetails,
            mediaError: err.mediaError,
            url: this.videoUrl,
            config: playerConfig
          });

          // 检查具体错误类型并处理
          if (err.message && err.message.includes('addSourceBuffer')) {
            console.log('Codec not supported, trying without audio');
            // 可以在这里添加重试逻辑
          } else if (err.message && err.message.includes('cors')) {
            console.log('CORS error, attempting to reload');
            this.reloadPlayer();
          } else {
            // 其他类型错误，尝试直接使用原始URL
            console.log('尝试使用原始URL播放');
            this.tryOriginalUrl();
          }
        });

        // 添加更多调试信息
        this.xgPlayer.on('ready', () => {
          console.log('Player ready, capabilities:', {
            mediaSource: !!window.MediaSource,
            sourceBuffer: !!window.SourceBuffer,
            videoCodecs: MediaSource.isTypeSupported('video/mp4; codecs="avc1.42E01E"'),
            flvSupport: typeof FlvPlayer !== 'undefined'
          });
        });

        this.xgPlayer.on('loading', () => {
          console.log('Player loading stream');
        });

        this.xgPlayer.on('waiting', () => {
          console.log('Player waiting for data');
        });

        this.xgPlayer.on('canplay', () => {
          console.log('Player can play stream');
        });

      } else if (streamType === 'mp4') {
        playerConfig = {
          id: 'xgPlayerContainer-' + this.index,
          url: this.videoUrl,
          crossorigin: 'anonymous',
          autoplayMuted: true,
          autoplay: true,
          width: '100%',
          height: '100%'
        }
        this.xgPlayer = new Player(playerConfig);
      } else if (streamType === 'hls') {
        playerConfig = {
          id: 'xgPlayerContainer-' + this.index,
          url: this.videoUrl,
          width: '100%',
          height: '100%',
          type: 'hls',
          plugins: [HlsPlayer]
        };
        this.xgPlayer = new Player(playerConfig);
      }
    },
    destoryPlayer () {
      if (this.xgPlayer) {
        this.xgPlayer.destroy(); // 销毁xgplayer实例
      }
    },
    // 添加重新加载方法
    reloadPlayer () {
      if (this.xgPlayer) {
        this.xgPlayer.destroy();
      }
      this.$nextTick(() => {
        this.initXgPlayer(this.streamType);
      });
    },
    
    // 尝试使用原始URL直接播放
    tryOriginalUrl() {
      console.log('尝试直接使用原始URL播放:', this.videoUrl);
      if (this.xgPlayer) {
        this.xgPlayer.destroy();
      }
      
      // 尝试使用默认播放器直接播放原始URL
      this.$nextTick(() => {
        const playerConfig = {
          id: 'xgPlayerContainer-' + this.index,
          url: this.videoUrl,
          volume: 0.6,
          autoplay: true,
          playsinline: true,
          isLive: true,
          cors: true,
          width: '100%',
          height: '100%'
        };
        
        // 对于RTMP流，尝试不进行任何处理直接使用
        if (this.videoUrl.startsWith('rtmp://')) {
          playerConfig.type = 'normal';
        }
        
        this.xgPlayer = new Player(playerConfig);
        
        // 添加错误处理
        this.xgPlayer.on('error', () => {
          console.log('直接播放失败，尝试使用HLS');
          this.tryHlsPlayback();
        });
      });
    },
    
    // 尝试使用HLS播放
    tryHlsPlayback() {
      if (this.xgPlayer) {
        this.xgPlayer.destroy();
      }
      
      // 尝试将RTMP地址转换为HLS地址
      let hlsUrl = this.videoUrl;
      if (this.videoUrl.startsWith('rtmp://')) {
        const domain = this.videoUrl.split('rtmp://')[1].split('/')[0];
        const streamPath = this.videoUrl.split(domain)[1];
        hlsUrl = `http://${domain}/hls${streamPath}.m3u8`;
      }
      
      console.log('尝试使用HLS地址:', hlsUrl);
      
      this.$nextTick(() => {
        const playerConfig = {
          id: 'xgPlayerContainer-' + this.index,
          url: hlsUrl,
          volume: 0.6,
          autoplay: true,
          playsinline: true,
          isLive: true,
          cors: true,
          width: '100%',
          height: '100%',
          type: 'hls',
          plugins: [HlsPlayer]
        };
        
        this.xgPlayer = new Player(playerConfig);
      });
    }
  },

};
</script>

<style scoped>
.video-player {
  width: 100%;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  overflow: hidden;
}

.xgplayer-container {
  width: 100%;
  height: 100%;
}
</style>