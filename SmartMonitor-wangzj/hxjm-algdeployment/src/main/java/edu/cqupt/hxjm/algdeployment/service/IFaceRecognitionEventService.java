package edu.cqupt.hxjm.algdeployment.service;

import java.util.List;
import java.util.Map;
import edu.cqupt.hxjm.algdeployment.domain.FaceRecognitionEvent;
import edu.cqupt.hxjm.algdeployment.domain.VO.FaceEventIdentityDetailVO;
import edu.cqupt.hxjm.algdeployment.domain.VO.TodayFaceEventVO;

/**
 * 人脸识别事件Service接口
 * 
 * @author zyn
 * @date 2024-02-28
 */
public interface IFaceRecognitionEventService 
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
     * 批量删除人脸识别事件
     * 
     * @param ids 需要删除的人脸识别事件主键集合
     * @return 结果
     */
    public int deleteFaceRecognitionEventByIds(Long[] ids);

    /**
     * 删除人脸识别事件信息
     * 
     * @param id 人脸识别事件主键
     * @return 结果
     */
    public int deleteFaceRecognitionEventById(Long id);

    /**
     * 查询当天的人脸识别事件
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
     * 使用 face_recognition_events_v1 查询当天事件，返回封装好的 VO
     */
    List<TodayFaceEventVO> selectTodayEventsV1();

    /**
     * 根据事件ID，查询“事件 + 身份详情”
     */
    FaceEventIdentityDetailVO getIdentityDetail(Long eventId);
}