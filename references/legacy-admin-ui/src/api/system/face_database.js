import request from '@/utils/request'
import config from '@/config'

// 查询人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等列表
export function listFace_database(query) {
  return request({
    url: '/system/face_database/list',
    method: 'get',
    params: query
  })
}

// 查询人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等详细
export function getFace_database(id) {
  return request({
    url: '/system/face_database/' + id,
    method: 'get'
  })
}

// 新增人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
export function addFace_database(data) {
  return request({
    url: '/system/face_database',
    method: 'post',
    data: data
  })
}

// 修改人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
export function updateFace_database(data) {
  return request({
    url: '/system/face_database',
    method: 'put',
    data: data
  })
}

// 删除人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
export function delFace_database(id) {
  return request({
    url: '/system/face_database/' + id,
    method: 'delete'
  })
}

// 获取人脸数据库所有人脸信息
export function getFace_database_all() {
  return request({
    url: '/system/face_database/faces',
    method: 'get'
  })  
}

// 调用算法服务添加人脸
export function addFace(data) {
  return request({
    url: config.algorithmServiceUrl + config.apiPath.addFace,
    method: 'post',
    data: data
  })
}

// 调用算法服务更新人脸
export function updateFace(data) {
  return request({
    url: config.algorithmServiceUrl + config.apiPath.updateFace,
    method: 'post',
    data: data
  })
}