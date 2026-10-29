package edu.cqupt.hxjm.system.service;

import java.util.List;
import edu.cqupt.hxjm.system.domain.FaceDatabase;

/**
 * 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等Service接口
 * 
 * @author zyn
 * @date 2025-02-19
 */
public interface IFaceDatabaseService 
{
    /**
     * 查询人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     * 
     * @param id 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等主键
     * @return 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     */
    public FaceDatabase selectFaceDatabaseById(Long id);

    /**
     * 查询人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等列表
     * 
     * @param faceDatabase 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     * @return 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等集合
     */
    public List<FaceDatabase> selectFaceDatabaseList(FaceDatabase faceDatabase);

    /**
     * 新增人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     * 
     * @param faceDatabase 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     * @return 结果
     */
    public int insertFaceDatabase(FaceDatabase faceDatabase);

    /**
     * 修改人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     * 
     * @param faceDatabase 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     * @return 结果
     */
    public int updateFaceDatabase(FaceDatabase faceDatabase);

    /**
     * 批量删除人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     * 
     * @param ids 需要删除的人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等主键集合
     * @return 结果
     */
    public int deleteFaceDatabaseByIds(Long[] ids);

    /**
     * 删除人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等信息
     * 
     * @param id 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等主键
     * @return 结果
     */
    public int deleteFaceDatabaseById(Long id);
}
