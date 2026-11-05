import request from '@/utils/request'

// 获取最近4小时的人脸识别事件
export function getTodayEvents() {
  return request({
    url: '/algdeployment/face_recognition_events/getTodayEvents',
    method: 'get'
  })
}

// 查询人脸识别事件列表
export function listFaceRecognitionEvents(query) {
  return request({
    url: '/algdeployment/face_recognition_events/list',
    method: 'get',
    params: query
  })
}

// 获取人脸识别事件详细信息
export function getFaceRecognitionEvent(id) {
  return request({
    url: '/algdeployment/face_recognition_events/' + id,
    method: 'get'
  })
} 


// 获取今日人脸识别流量
export function countTodayFlow() {
  return request({
    url: '/algdeployment/face_recognition_events/todayFlow',
    method: 'get'
  })
}
