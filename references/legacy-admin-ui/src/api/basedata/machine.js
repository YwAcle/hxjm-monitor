import request from '@/utils/request'

// 查询设备信息列表
export function listMachine(query) {
  return request({
    url: '/basedata/machine/list',
    method: 'get',
    params: query
  })
}

// 查询设备信息详细
export function getMachine(machineId) {
  return request({
    url: '/basedata/machine/' + machineId,
    method: 'get'
  })
}

// 新增设备信息
export function addMachine(data) {
  return request({
    url: '/basedata/machine',
    method: 'post',
    data: data
  })
}

// 修改设备信息
export function updateMachine(data) {
  return request({
    url: '/basedata/machine',
    method: 'put',
    data: data
  })
}

// 删除设备信息
export function delMachine(machineId) {
  return request({
    url: '/basedata/machine/' + machineId,
    method: 'delete'
  })
}
