package edu.cqupt.hxjm.algdeployment.service.impl;

import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import edu.cqupt.hxjm.algdeployment.mapper.AlgDeploymentManagementMapper;
import edu.cqupt.hxjm.algdeployment.domain.AlgDeploymentManagement;
import edu.cqupt.hxjm.algdeployment.service.IAlgDeploymentManagementService;

/**
 * 算法部署管理Service业务层处理
 * 
 * @author zyn
 * @date 2024-02-28
 */
@Service
public class AlgDeploymentManagementServiceImpl implements IAlgDeploymentManagementService 
{
    @Autowired
    private AlgDeploymentManagementMapper algDeploymentManagementMapper;

    /**
     * 查询算法部署管理
     * 
     * @param id 算法部署管理主键
     * @return 算法部署管理
     */
    @Override
    public AlgDeploymentManagement selectAlgDeploymentManagementById(Long id)
    {
        return algDeploymentManagementMapper.selectAlgDeploymentManagementById(id);
    }

    /**
     * 查询算法部署管理列表
     * 
     * @param algDeploymentManagement 算法部署管理
     * @return 算法部署管理
     */
    @Override
    public List<AlgDeploymentManagement> selectAlgDeploymentManagementList(AlgDeploymentManagement algDeploymentManagement)
    {
        return algDeploymentManagementMapper.selectAlgDeploymentManagementList(algDeploymentManagement);
    }

    /**
     * 新增算法部署管理
     * 
     * @param algDeploymentManagement 算法部署管理
     * @return 结果
     */
    @Override
    public int insertAlgDeploymentManagement(AlgDeploymentManagement algDeploymentManagement)
    {
        return algDeploymentManagementMapper.insertAlgDeploymentManagement(algDeploymentManagement);
    }

    /**
     * 修改算法部署管理
     * 
     * @param algDeploymentManagement 算法部署管理
     * @return 结果
     */
    @Override
    public int updateAlgDeploymentManagement(AlgDeploymentManagement algDeploymentManagement)
    {
        return algDeploymentManagementMapper.updateAlgDeploymentManagement(algDeploymentManagement);
    }

    /**
     * 批量删除算法部署管理
     * 
     * @param ids 需要删除的算法部署管理主键
     * @return 结果
     */
    @Override
    public int deleteAlgDeploymentManagementByIds(Long[] ids)
    {
        return algDeploymentManagementMapper.deleteAlgDeploymentManagementByIds(ids);
    }

    /**
     * 删除算法部署管理信息
     * 
     * @param id 算法部署管理主键
     * @return 结果
     */
    @Override
    public int deleteAlgDeploymentManagementById(Long id)
    {
        return algDeploymentManagementMapper.deleteAlgDeploymentManagementById(id);
    }

    /**
     * 获取所有可用设备列表
     * 
     * @return 设备列表
     */
    @Override
    public List<Map<String, Object>> getMachineList()
    {
        return algDeploymentManagementMapper.getMachineList();
    }
} 