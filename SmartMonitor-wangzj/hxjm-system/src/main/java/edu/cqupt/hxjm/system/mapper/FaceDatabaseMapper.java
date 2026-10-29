package edu.cqupt.hxjm.system.mapper;

import java.util.List;
import java.util.Map;
import edu.cqupt.hxjm.system.domain.FaceDatabase;

/**
 * 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等Mapper接口
 * 
 * @author zyn
 * @date 2025-02-19
 */
public interface FaceDatabaseMapper 
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
     * 删除人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     * 
     * @param id 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等主键
     * @return 结果
     */
    public int deleteFaceDatabaseById(Long id);

    /**
     * 批量删除人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     * 
     * @param ids 需要删除的数据主键集合
     * @return 结果
     */
    public int deleteFaceDatabaseByIds(Long[] ids);

    /**
     * 获取所有人脸信息
     * 
     * @return 人脸信息列表
     */
    List<Map<String, Object>> selectAllFaceInfo();
}
