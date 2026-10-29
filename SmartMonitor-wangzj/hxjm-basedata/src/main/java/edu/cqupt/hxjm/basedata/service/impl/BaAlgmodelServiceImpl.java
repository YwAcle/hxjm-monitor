package edu.cqupt.hxjm.basedata.service.impl;

import java.io.IOException;
import java.util.List;

import edu.cqupt.hxjm.common.config.SmartMonitorConfig;
import edu.cqupt.hxjm.common.exception.file.InvalidExtensionException;
import edu.cqupt.hxjm.common.utils.file.FileUploadUtils;
import edu.cqupt.hxjm.common.utils.file.MimeTypeUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import edu.cqupt.hxjm.basedata.mapper.BaAlgmodelMapper;
import edu.cqupt.hxjm.basedata.domain.BaAlgmodel;
import edu.cqupt.hxjm.basedata.service.IBaAlgmodelService;
import org.springframework.web.multipart.MultipartFile;

/**
 * 模型信息Service业务层处理
 * 
 * @author 钟先生不想写代码
 * @date 2024-11-25
 */
@Service
public class BaAlgmodelServiceImpl implements IBaAlgmodelService 
{
    @Autowired
    private BaAlgmodelMapper baAlgmodelMapper;

    /**
     * 查询模型信息
     * 
     * @param algmodelId 模型信息主键
     * @return 模型信息
     */
    @Override
    public BaAlgmodel selectBaAlgmodelByAlgmodelId(Long algmodelId)
    {
        return baAlgmodelMapper.selectBaAlgmodelByAlgmodelId(algmodelId);
    }

    /**
     * 查询模型信息列表
     * 
     * @param baAlgmodel 模型信息
     * @return 模型信息
     */
    @Override
    public List<BaAlgmodel> selectBaAlgmodelList(BaAlgmodel baAlgmodel)
    {
        return baAlgmodelMapper.selectBaAlgmodelList(baAlgmodel);
    }

    /**
     * 新增模型信息
     * 
     * @param baAlgmodel 模型信息
     * @return 结果
     */
    @Override
    public int insertBaAlgmodel(BaAlgmodel baAlgmodel, MultipartFile file) throws IOException, InvalidExtensionException
    {
        if(file != null && !file.isEmpty()){
            String preview = FileUploadUtils.upload(SmartMonitorConfig.getAlgPreview(), file, MimeTypeUtils.IMAGE_EXTENSION);
            baAlgmodel.setPreview(preview);
        }
        return baAlgmodelMapper.insertBaAlgmodel(baAlgmodel);
    }

    /**
     * 修改模型信息
     * 
     * @param baAlgmodel 模型信息
     * @return 结果
     */
    @Override
    public int updateBaAlgmodel(BaAlgmodel baAlgmodel, MultipartFile file) throws IOException, InvalidExtensionException {
        if(file != null && !file.isEmpty()){
            String preview = FileUploadUtils.upload(SmartMonitorConfig.getAlgPreview(), file, MimeTypeUtils.IMAGE_EXTENSION);
            baAlgmodel.setPreview(preview);
        }
        return baAlgmodelMapper.updateBaAlgmodel(baAlgmodel);
    }

    /**
     * 批量删除模型信息
     * 
     * @param algmodelIds 需要删除的模型信息主键
     * @return 结果
     */
    @Override
    public int deleteBaAlgmodelByAlgmodelIds(Long[] algmodelIds)
    {
        return baAlgmodelMapper.deleteBaAlgmodelByAlgmodelIds(algmodelIds);
    }

    /**
     * 删除模型信息信息
     * 
     * @param algmodelId 模型信息主键
     * @return 结果
     */
    @Override
    public int deleteBaAlgmodelByAlgmodelId(Long algmodelId)
    {
        return baAlgmodelMapper.deleteBaAlgmodelByAlgmodelId(algmodelId);
    }
}
