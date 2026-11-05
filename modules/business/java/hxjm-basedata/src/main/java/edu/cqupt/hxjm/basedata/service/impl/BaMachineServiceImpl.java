package edu.cqupt.hxjm.basedata.service.impl;

import java.util.List;

import edu.cqupt.hxjm.basedata.domain.BaMachine;
import edu.cqupt.hxjm.basedata.service.IBaMachineService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import edu.cqupt.hxjm.basedata.mapper.BaMachineMapper;

/**
 * 设备信息Service业务层处理
 * 
 * @author 钟先生不想写代码
 * @date 2024-11-04
 */
@Service
public class BaMachineServiceImpl implements IBaMachineService
{
    @Autowired
    private BaMachineMapper baMachineMapper;

    /**
     * 查询设备信息
     * 
     * @param machineId 设备信息主键
     * @return 设备信息
     */
    @Override
    public BaMachine selectBaMachineByMachineId(Long machineId)
    {
        return baMachineMapper.selectBaMachineByMachineId(machineId);
    }

    /**
     * 查询设备信息列表
     * 
     * @param baMachine 设备信息
     * @return 设备信息
     */
    @Override
    public List<BaMachine> selectBaMachineList(BaMachine baMachine)
    {
        return baMachineMapper.selectBaMachineList(baMachine);
    }

    /**
     * 新增设备信息
     * 
     * @param baMachine 设备信息
     * @return 结果
     */
    @Override
    public int insertBaMachine(BaMachine baMachine)
    {
        return baMachineMapper.insertBaMachine(baMachine);
    }

    /**
     * 修改设备信息
     * 
     * @param baMachine 设备信息
     * @return 结果
     */
    @Override
    public int updateBaMachine(BaMachine baMachine)
    {
        return baMachineMapper.updateBaMachine(baMachine);
    }

    /**
     * 批量删除设备信息
     * 
     * @param machineIds 需要删除的设备信息主键
     * @return 结果
     */
    @Override
    public int deleteBaMachineByMachineIds(Long[] machineIds)
    {
        return baMachineMapper.deleteBaMachineByMachineIds(machineIds);
    }

    /**
     * 删除设备信息信息
     * 
     * @param machineId 设备信息主键
     * @return 结果
     */
    @Override
    public int deleteBaMachineByMachineId(Long machineId)
    {
        return baMachineMapper.deleteBaMachineByMachineId(machineId);
    }
}
