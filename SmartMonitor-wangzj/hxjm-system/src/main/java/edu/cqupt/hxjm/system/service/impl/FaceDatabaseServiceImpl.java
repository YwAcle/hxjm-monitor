package edu.cqupt.hxjm.system.service.impl;

import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import edu.cqupt.hxjm.system.mapper.FaceDatabaseMapper;
import edu.cqupt.hxjm.system.domain.FaceDatabase;
import edu.cqupt.hxjm.system.service.IFaceDatabaseService;

/**
 * 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等Service业务层处理
 * 
 * @author zyn
 * @date 2025-02-19
 */
@Service
public class FaceDatabaseServiceImpl implements IFaceDatabaseService 
{
    @Autowired
    private FaceDatabaseMapper faceDatabaseMapper;

    /**
     * 查询人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     * 
     * @param id 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等主键
     * @return 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     */
    @Override
    public FaceDatabase selectFaceDatabaseById(Long id)
    {
        return faceDatabaseMapper.selectFaceDatabaseById(id);
    }

    /**
     * 查询人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等列表
     * 
     * @param faceDatabase 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     * @return 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     */
    @Override
    public List<FaceDatabase> selectFaceDatabaseList(FaceDatabase faceDatabase)
    {
        return faceDatabaseMapper.selectFaceDatabaseList(faceDatabase);
    }

    /**
     * 新增人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     * 
     * @param faceDatabase 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     * @return 结果
     */
    @Override
    public int insertFaceDatabase(FaceDatabase faceDatabase)
    {
        return faceDatabaseMapper.insertFaceDatabase(faceDatabase);
    }

    /**
     * 修改人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     * 
     * @param faceDatabase 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     * @return 结果
     */
    @Override
    public int updateFaceDatabase(FaceDatabase faceDatabase)
    {
        return faceDatabaseMapper.updateFaceDatabase(faceDatabase);
    }

    /**
     * 批量删除人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     * 
     * @param ids 需要删除的人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等主键
     * @return 结果
     */
    @Override
    public int deleteFaceDatabaseByIds(Long[] ids)
    {
        return faceDatabaseMapper.deleteFaceDatabaseByIds(ids);
    }

    /**
     * 删除人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等信息
     * 
     * @param id 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等主键
     * @return 结果
     */
    @Override
    public int deleteFaceDatabaseById(Long id)
    {
        return faceDatabaseMapper.deleteFaceDatabaseById(id);
    }
}
