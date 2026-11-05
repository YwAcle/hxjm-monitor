import request from '@/utils/request'
import config from '@/config'
// 查询算法布控管理列表
export function listAlgdeploymentmanagement(query) {
  return request({
    url: '/algdeployment/management/list',
    method: 'get',
    params: query
  })
}

// 查询算法布控管理详细
export function getAlgdeploymentmanagement(id) {
  return request({
    url: '/algdeployment/management/' + id,
    method: 'get'
  })
}

// 新增算法布控管理
export function addAlgdeploymentmanagement(data) {
  return request({
    url: '/algdeployment/management',
    method: 'post',
    data: data
  })
}

// 修改算法布控管理
export function updateAlgdeploymentmanagement(data) {
  return request({
    url: '/algdeployment/management',
    method: 'put',
    data: data
  })
}

// 删除算法布控管理
export function delAlgdeploymentmanagement(id) {
  return request({
    url: '/algdeployment/management/' + id,
    method: 'delete'
  })
}

// 获取设备列表
export function getMachineList() {
  return request({
    url: '/algdeployment/management/getMachineList',
    method: 'get'
  })
}

// 布控算法
export function deployAlg(alg_bk_api_head, machineList) {
  return request({
    url: config.algorithmServiceUrl+alg_bk_api_head+config.algorithmApiPath.startDeployment,
    method: 'post',
    data: {"machineList": machineList }
  })
}

// 停止布控
export function stopDeploy(alg_bk_api_head, machineList) {
  return request({
    url: config.algorithmServiceUrl+alg_bk_api_head+config.algorithmApiPath.stopDeployment,
    method: 'post',
    data: {"machineList": machineList }
  })
}
