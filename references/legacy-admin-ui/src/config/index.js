export default {
  // 算法服务地址
  algorithmServiceUrl: process.env.VUE_APP_ALGORITHM_SERVICE_URL || 'http://localhost:8000',
  
  // 流媒体服务地址
  streamServiceUrl: process.env.ALG_OUTPUT_STREAM_URL || 'http://192.168.8.63:82',
  
  // 算法服务API路径
  algorithmApiPath: {
    startDeployment: '/start_deployment',
    stopDeployment: '/stop_deployment',
  },
  // API路径
  apiPath: {
    modelUpload: '/algPlatform/upload_model',
    modelProcess: '/algPlatform/test',
    modelList: '/api/v1/models/list',
    modelDelete: '/api/v1/models/delete',
    addFace: '/api/face_recognition/add_face',
    updateFace: '/api/face_recognition/update_face',
  }
} 