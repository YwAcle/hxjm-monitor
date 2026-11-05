import request from '@/utils/request'

// 查询reid
export function reidSearch(data) {
  return request({
    url: '/interface-service/reid',
    method: 'post',
    data: data
  })
}

// 查询设备信息列表
export function stramTransform(data) {
  return request({
    url: '/stream/proxy',
    method: 'post',
    data: data
  })
}