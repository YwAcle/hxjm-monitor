package edu.cqupt.hxjm.algdeployment.mapper;

import java.util.List;
import java.util.Map;
import edu.cqupt.hxjm.algdeployment.domain.AlgDeploymentManagement;

/**
 * 算法部署管理Mapper接口
 * 
 * @author zyn
 * @date 2024-02-28
 */
public interface AlgDeploymentManagementMapper 
{
    /**
     * 查询算法部署管理
     * 
     * @param id 算法部署管理主键
     * @return 算法部署管理
     */
    public AlgDeploymentManagement selectAlgDeploymentManagementById(Long id);

    /**
     * 查询算法部署管理列表
     * 
     * @param algDeploymentManagement 算法部署管理
     * @return 算法部署管理集合
     */
    public List<AlgDeploymentManagement> selectAlgDeploymentManagementList(AlgDeploymentManagement algDeploymentManagement);

    /**
     * 新增算法部署管理
     * 
     * @param algDeploymentManagement 算法部署管理
     * @return 结果
     */
    public int insertAlgDeploymentManagement(AlgDeploymentManagement algDeploymentManagement);

    /**
     * 修改算法部署管理
     * 
     * @param algDeploymentManagement 算法部署管理
     * @return 结果
     */
    public int updateAlgDeploymentManagement(AlgDeploymentManagement algDeploymentManagement);

    /**
     * 删除算法部署管理
     * 
     * @param id 算法部署管理主键
     * @return 结果
     */
    public int deleteAlgDeploymentManagementById(Long id);

    /**
     * 批量删除算法部署管理
     * 
     * @param ids 需要删除的数据主键集合
     * @return 结果
     */
    public int deleteAlgDeploymentManagementByIds(Long[] ids);

    /**
     * 获取所有可用设备列表
     * 
     * @return 设备列表
     */
    public List<Map<String, Object>> getMachineList();
} 