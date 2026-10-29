import request from '@/utils/request'

// 查询模型类型列表
export function listAlgtype(query) {
  return request({
    url: '/basedata/algtype/list',
    method: 'get',
    params: query
  })
}

// 查询模型类型详细
export function getAlgtype(algtypeId) {
  return request({
    url: '/basedata/algtype/' + algtypeId,
    method: 'get'
  })
}

// 新增模型类型
export function addAlgtype(data) {
  return request({
    url: '/basedata/algtype',
    method: 'post',
    data: data
  })
}

// 修改模型类型
export function updateAlgtype(data) {
  return request({
    url: '/basedata/algtype',
    method: 'put',
    data: data
  })
}

// 删除模型类型
export function delAlgtype(algtypeId) {
  return request({
    url: '/basedata/algtype/' + algtypeId,
    method: 'delete'
  })
}

// 获取模型类型列表
export function getDisplayModel() {
  return request({
    url: '/basedata/algtype/display',
    method: 'get'
  })
}

