import request from '@/utils/request'

// 查询模型信息列表
export function listAlgmodel(query) {
  return request({
    url: '/basedata/algmodel/list',
    method: 'get',
    params: query
  })
}

// 查询模型信息详细
export function getAlgmodel(algmodelId) {
  return request({
    url: '/basedata/algmodel/' + algmodelId,
    method: 'get'
  })
}

// 新增模型信息
export function addAlgmodel(data) {
  return request({
    url: '/basedata/algmodel',
    method: 'post',
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    data: data
  })
}

// 修改模型信息
export function updateAlgmodel(data) {
  return request({
    url: '/basedata/algmodel',
    method: 'put',
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    data: data
  })
}

// 删除模型信息
export function delAlgmodel(algmodelId) {
  return request({
    url: '/basedata/algmodel/' + algmodelId,
    method: 'delete'
  })
}
