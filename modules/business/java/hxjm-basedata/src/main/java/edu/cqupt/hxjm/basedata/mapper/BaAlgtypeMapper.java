package edu.cqupt.hxjm.basedata.mapper;

import java.util.List;

import com.alibaba.fastjson2.JSONObject;
import edu.cqupt.hxjm.basedata.domain.BaAlgtype;

/**
 * 模型类型Mapper接口
 * 
 * @author 钟先生不想写代码
 * @date 2024-11-25
 */
public interface BaAlgtypeMapper 
{
    /**
     * 查询模型类型
     * 
     * @param algtypeId 模型类型主键
     * @return 模型类型
     */
    public BaAlgtype selectBaAlgtypeByAlgtypeId(Long algtypeId);

    /**
     * 查询模型类型列表
     * 
     * @param baAlgtype 模型类型
     * @return 模型类型集合
     */
    public List<BaAlgtype> selectBaAlgtypeList(BaAlgtype baAlgtype);

    /**
     * 新增模型类型
     * 
     * @param baAlgtype 模型类型
     * @return 结果
     */
    public int insertBaAlgtype(BaAlgtype baAlgtype);

    /**
     * 修改模型类型
     * 
     * @param baAlgtype 模型类型
     * @return 结果
     */
    public int updateBaAlgtype(BaAlgtype baAlgtype);

    /**
     * 删除模型类型
     * 
     * @param algtypeId 模型类型主键
     * @return 结果
     */
    public int deleteBaAlgtypeByAlgtypeId(Long algtypeId);

    /**
     * 批量删除模型类型
     * 
     * @param algtypeIds 需要删除的数据主键集合
     * @return 结果
     */
    public int deleteBaAlgtypeByAlgtypeIds(Long[] algtypeIds);

    /**
     * 查询大屏展示算法List
     *
     * @return 模型List
     */
    public List<JSONObject> getDisplayModelList();
}
