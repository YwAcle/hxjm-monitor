package edu.cqupt.hxjm.basedata.mapper;

import java.util.List;

import edu.cqupt.hxjm.basedata.domain.BaMachine;

/**
 * 设备信息Mapper接口
 * 
 * @author 钟先生不想写代码
 * @date 2024-11-04
 */
public interface BaMachineMapper 
{
    /**
     * 查询设备信息
     * 
     * @param machineId 设备信息主键
     * @return 设备信息
     */
    public BaMachine selectBaMachineByMachineId(Long machineId);

    /**
     * 查询设备信息列表
     * 
     * @param baMachine 设备信息
     * @return 设备信息集合
     */
    public List<BaMachine> selectBaMachineList(BaMachine baMachine);

    /**
     * 新增设备信息
     * 
     * @param baMachine 设备信息
     * @return 结果
     */
    public int insertBaMachine(BaMachine baMachine);

    /**
     * 修改设备信息
     * 
     * @param baMachine 设备信息
     * @return 结果
     */
    public int updateBaMachine(BaMachine baMachine);

    /**
     * 删除设备信息
     * 
     * @param machineId 设备信息主键
     * @return 结果
     */
    public int deleteBaMachineByMachineId(Long machineId);

    /**
     * 批量删除设备信息
     * 
     * @param machineIds 需要删除的数据主键集合
     * @return 结果
     */
    public int deleteBaMachineByMachineIds(Long[] machineIds);
}
