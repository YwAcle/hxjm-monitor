package edu.cqupt.hxjm.algdeployment.mapper;

import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Mapper;

import edu.cqupt.hxjm.algdeployment.domain.FaceRecognitionEvent;
import edu.cqupt.hxjm.algdeployment.domain.VO.TodayFaceEventVO;
import io.lettuce.core.dynamic.annotation.Param;

/**
 * 人脸识别事件Mapper接口
 * 
 * @author zyn
 * @date 2024-02-28
 */
@Mapper
public interface FaceRecognitionEventMapper 
{
    /**
     * 查询人脸识别事件
     * 
     * @param id 人脸识别事件主键
     * @return 人脸识别事件
     */
    public FaceRecognitionEvent selectFaceRecognitionEventById(Long id);

    /**
     * 查询人脸识别事件列表
     * 
     * @param faceRecognitionEvent 人脸识别事件
     * @return 人脸识别事件集合
     */
    public List<FaceRecognitionEvent> selectFaceRecognitionEventList(FaceRecognitionEvent faceRecognitionEvent);

    /**
     * 新增人脸识别事件
     * 
     * @param faceRecognitionEvent 人脸识别事件
     * @return 结果
     */
    public int insertFaceRecognitionEvent(FaceRecognitionEvent faceRecognitionEvent);

    /**
     * 修改人脸识别事件
     * 
     * @param faceRecognitionEvent 人脸识别事件
     * @return 结果
     */
    public int updateFaceRecognitionEvent(FaceRecognitionEvent faceRecognitionEvent);

    /**
     * 删除人脸识别事件
     * 
     * @param id 人脸识别事件主键
     * @return 结果
     */
    public int deleteFaceRecognitionEventById(Long id);

    /**
     * 批量删除人脸识别事件
     * 
     * @param ids 需要删除的数据主键集合
     * @return 结果
     */
    public int deleteFaceRecognitionEventByIds(Long[] ids);

    /**
     * 查询当天的人脸识别事件（关联设备和人脸信息）
     * 
     * @return 人脸识别事件集合
     */
    public List<Map<String, Object>> selectTodayEvents();

    /**
     * 统计当日各时段人流量
     * 
     * @return 各时段人流量列表
     */
    public List<Map<String, Object>> countTodayFlow();

    // ===== 新增：大屏用 v1 表 =====

    /**
     * face_recognition_events_v1 + face_person/face_stranger + ba_machine
     * 查询当日事件列表
     */
    List<TodayFaceEventVO> selectTodayEventsV1();

    /**
     * 根据事件ID查询事件 + 身份详情（JOIN 一次搞定）
     */
    Map<String, Object> selectEventIdentityDetail(@Param("id") Long id);


    // FaceRecognitionEventMapper.java

    /**
     * 将历史事件中指定陌生人ID对应的记录，批量改为正式人员
     *
     * @param strangerId 陌生人ID（face_stranger.id）
     * @param personId   新的正式人员ID（face_person.id）
     * @return 受影响行数
     */
    int updateEventsIdentityFromStrangerToPerson(@Param("strangerId") Long strangerId,
                                                 @Param("personId") Long personId);

}