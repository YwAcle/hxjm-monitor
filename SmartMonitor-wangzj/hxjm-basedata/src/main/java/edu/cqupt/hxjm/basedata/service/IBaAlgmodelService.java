package edu.cqupt.hxjm.basedata.service;

import java.io.IOException;
import java.util.List;
import edu.cqupt.hxjm.basedata.domain.BaAlgmodel;
import edu.cqupt.hxjm.common.exception.file.InvalidExtensionException;
import org.springframework.web.multipart.MultipartFile;

/**
 * 模型信息Service接口
 * 
 * @author 钟先生不想写代码
 * @date 2024-11-25
 */
public interface IBaAlgmodelService 
{
    /**
     * 查询模型信息
     * 
     * @param algmodelId 模型信息主键
     * @return 模型信息
     */
    public BaAlgmodel selectBaAlgmodelByAlgmodelId(Long algmodelId);

    /**
     * 查询模型信息列表
     * 
     * @param baAlgmodel 模型信息
     * @return 模型信息集合
     */
    public List<BaAlgmodel> selectBaAlgmodelList(BaAlgmodel baAlgmodel);

    /**
     * 新增模型信息
     * 
     * @param baAlgmodel 模型信息
     * @return 结果
     */
    public int insertBaAlgmodel(BaAlgmodel baAlgmodel, MultipartFile file) throws IOException, InvalidExtensionException;

    /**
     * 修改模型信息
     * 
     * @param baAlgmodel 模型信息
     * @return 结果
     */
    public int updateBaAlgmodel(BaAlgmodel baAlgmodel, MultipartFile file) throws IOException, InvalidExtensionException;

    /**
     * 批量删除模型信息
     * 
     * @param algmodelIds 需要删除的模型信息主键集合
     * @return 结果
     */
    public int deleteBaAlgmodelByAlgmodelIds(Long[] algmodelIds);

    /**
     * 删除模型信息信息
     * 
     * @param algmodelId 模型信息主键
     * @return 结果
     */
    public int deleteBaAlgmodelByAlgmodelId(Long algmodelId);
}
