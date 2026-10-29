import request from '@/utils/request'
import config from '@/config'

const { algorithmServiceUrl, apiPath } = config

// 运行算法模型
export function runAlgorithmModel(data) {
  // 创建 FormData 对象
  const formData = new FormData()

  // 添加模型参数
  const modelParams = {
    modelCode: data.modelCode,
    modelPath: data.modelPath,
		modelName: data.modelName,
    modelInput: data.modelInput,
    modelOutput: data.modelOutput,
  }
  formData.append('model_params', JSON.stringify(modelParams))

  // 添加设备列表
  formData.append('machines', JSON.stringify(data.machines))

  // 处理图片文件
  if (data.files && data.files.length > 0) {
    const images = data.files.map(file => ({
      name: file.name,
      data: file.data  // 直接使用base64编码
    }))

    // 将图片数组添加到FormData
    formData.append('images', JSON.stringify(images))
  }

  return request({
    url: `${algorithmServiceUrl}${apiPath.modelProcess}`,
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data',
      'Accept': 'application/json',

    }
  })
}

// 运行ReID算法
export function runReIDAlgorithm(data) {
  return request({
    url: `${algorithmServiceUrl}/api/reid/start-reid`,
    method: 'post',
    data: data,
    timeout: 60000
  })
}

// 停止ReID算法
export function stopReIDAlgorithm(streamIds) {
  return request({
    url: `${algorithmServiceUrl}/api/reid/stop-reid`,
    method: 'post',
    data: { stream_ids: streamIds },
    timeout: 60000
  })
}

// 运行算法
export function runPoseEstimationAlgorithm(data) {
  return request({
    url: `${algorithmServiceUrl}/api/pose_estimation/start-estimation`,
    method: 'post',
    data: data,
    timeout: 60000
  })
}
// 停止姿态估计算法
export function stopPoseEstimationAlgorithm(streamIds) {
  return request({
    url: `${algorithmServiceUrl}/api/pose_estimation/stop-estimation`,
    method: 'post',
    data: { stream_ids: streamIds },
    timeout: 60000
  })
}
// 获取模型列表
export function listModels() {
  return request({
    url: `${algorithmServiceUrl}${apiPath.modelList}`,
    method: 'get'
  })
}

// 删除模型
export function deleteModel(modelId) {
  return request({
    url: `${algorithmServiceUrl}${apiPath.modelDelete}/${modelId}`,
    method: 'delete'
  })
}

// 上传模型文件
export function uploadModelFile(data, onProgress) {
  return request({
    url: `${algorithmServiceUrl}${apiPath.modelUpload}`,
    method: 'post',
    data,
    headers: {
      'Content-Type': 'multipart/form-data'
    },
    onUploadProgress: onProgress ?
      progressEvent => {
        const percentCompleted = Math.round(
          (progressEvent.loaded * 100) / progressEvent.total
        );
        onProgress(percentCompleted);
      } : undefined,
    timeout: 3600000  // 1小时超时
  })
}
