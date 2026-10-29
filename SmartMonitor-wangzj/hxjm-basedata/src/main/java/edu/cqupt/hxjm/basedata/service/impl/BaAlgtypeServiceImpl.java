package edu.cqupt.hxjm.basedata.service.impl;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.alibaba.fastjson2.JSONObject;
import edu.cqupt.hxjm.basedata.mapper.BaAlgmodelMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import edu.cqupt.hxjm.basedata.mapper.BaAlgtypeMapper;
import edu.cqupt.hxjm.basedata.domain.BaAlgtype;
import edu.cqupt.hxjm.basedata.service.IBaAlgtypeService;

/**
 * 模型类型Service业务层处理
 * 
 * @author 钟先生不想写代码
 * @date 2024-11-25
 */
@Service
public class BaAlgtypeServiceImpl implements IBaAlgtypeService 
{
    @Autowired
    private BaAlgtypeMapper baAlgtypeMapper;

    /**
     * 查询模型类型
     * 
     * @param algtypeId 模型类型主键
     * @return 模型类型
     */
    @Override
    public BaAlgtype selectBaAlgtypeByAlgtypeId(Long algtypeId)
    {
        return baAlgtypeMapper.selectBaAlgtypeByAlgtypeId(algtypeId);
    }

    /**
     * 查询模型类型列表
     * 
     * @param baAlgtype 模型类型
     * @return 模型类型
     */
    @Override
    public List<BaAlgtype> selectBaAlgtypeList(BaAlgtype baAlgtype)
    {
        return baAlgtypeMapper.selectBaAlgtypeList(baAlgtype);
    }

    /**
     * 新增模型类型
     * 
     * @param baAlgtype 模型类型
     * @return 结果
     */
    @Override
    public int insertBaAlgtype(BaAlgtype baAlgtype)
    {
        return baAlgtypeMapper.insertBaAlgtype(baAlgtype);
    }

    /**
     * 修改模型类型
     * 
     * @param baAlgtype 模型类型
     * @return 结果
     */
    @Override
    public int updateBaAlgtype(BaAlgtype baAlgtype)
    {
        return baAlgtypeMapper.updateBaAlgtype(baAlgtype);
    }

    /**
     * 批量删除模型类型
     * 
     * @param algtypeIds 需要删除的模型类型主键
     * @return 结果
     */
    @Override
    public int deleteBaAlgtypeByAlgtypeIds(Long[] algtypeIds)
    {
        return baAlgtypeMapper.deleteBaAlgtypeByAlgtypeIds(algtypeIds);
    }

    /**
     * 删除模型类型信息
     * 
     * @param algtypeId 模型类型主键
     * @return 结果
     */
    @Override
    public int deleteBaAlgtypeByAlgtypeId(Long algtypeId)
    {
        return baAlgtypeMapper.deleteBaAlgtypeByAlgtypeId(algtypeId);
    }

    @Override
    public Map<Integer, Map<String, Object>> getDisplayModelList() {
        List<JSONObject> modelList = baAlgtypeMapper.getDisplayModelList();
        // 创建一个 Map 来存储结果
        Map<Integer, Map<String, Object>> resultMap = new HashMap<>();
        // 遍历 modelList
        for (JSONObject model : modelList) {
            Integer algTypeId = model.getInteger("algtypeId");
            String algTypeName = model.getString("algtypeName");

            // 如果 map 中还没有这个 algTypeId 的列表，创建一个新的
            resultMap.computeIfAbsent(algTypeId, k -> {
                Map<String, Object> map = new HashMap<>();
                map.put("algTypeName", algTypeName);
                map.put("modelList", new ArrayList<JSONObject>());
                return map;
            });
            // 将当前对象添加到对应的列表中
            ((List<JSONObject>) resultMap.get(algTypeId).get("modelList")).add(model);
        }

        return resultMap;
    }
}
