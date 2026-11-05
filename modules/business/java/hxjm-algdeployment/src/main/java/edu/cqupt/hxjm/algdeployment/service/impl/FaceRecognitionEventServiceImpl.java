package edu.cqupt.hxjm.algdeployment.service.impl;

import java.util.List;
import java.util.Map;

import edu.cqupt.hxjm.algdeployment.domain.VO.FaceEventIdentityDetailVO;
import edu.cqupt.hxjm.algdeployment.domain.VO.TodayFaceEventVO;
import edu.cqupt.hxjm.algdeployment.service.IFaceRecognitionEventService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import edu.cqupt.hxjm.algdeployment.mapper.FaceRecognitionEventMapper;
import edu.cqupt.hxjm.algdeployment.domain.FaceRecognitionEvent;

/**
 * 人脸识别事件Service业务层处理
 * 
 * @author zyn
 * @date 2024-02-28
 */
@Service
public class FaceRecognitionEventServiceImpl implements IFaceRecognitionEventService
{
    @Autowired
    private FaceRecognitionEventMapper faceRecognitionEventMapper;

    /**
     * 查询人脸识别事件
     * 
     * @param id 人脸识别事件主键
     * @return 人脸识别事件
     */
    @Override
    public FaceRecognitionEvent selectFaceRecognitionEventById(Long id)
    {
        return faceRecognitionEventMapper.selectFaceRecognitionEventById(id);
    }

    /**
     * 查询人脸识别事件列表
     * 
     * @param faceRecognitionEvent 人脸识别事件
     * @return 人脸识别事件
     */
    @Override
    public List<FaceRecognitionEvent> selectFaceRecognitionEventList(FaceRecognitionEvent faceRecognitionEvent)
    {
        return faceRecognitionEventMapper.selectFaceRecognitionEventList(faceRecognitionEvent);
    }

    /**
     * 新增人脸识别事件
     * 
     * @param faceRecognitionEvent 人脸识别事件
     * @return 结果
     */
    @Override
    public int insertFaceRecognitionEvent(FaceRecognitionEvent faceRecognitionEvent)
    {
        return faceRecognitionEventMapper.insertFaceRecognitionEvent(faceRecognitionEvent);
    }

    /**
     * 修改人脸识别事件
     * 
     * @param faceRecognitionEvent 人脸识别事件
     * @return 结果
     */
    @Override
    public int updateFaceRecognitionEvent(FaceRecognitionEvent faceRecognitionEvent)
    {
        return faceRecognitionEventMapper.updateFaceRecognitionEvent(faceRecognitionEvent);
    }

    /**
     * 批量删除人脸识别事件
     * 
     * @param ids 需要删除的人脸识别事件主键
     * @return 结果
     */
    @Override
    public int deleteFaceRecognitionEventByIds(Long[] ids)
    {
        return faceRecognitionEventMapper.deleteFaceRecognitionEventByIds(ids);
    }

    /**
     * 删除人脸识别事件信息
     * 
     * @param id 人脸识别事件主键
     * @return 结果
     */
    @Override
    public int deleteFaceRecognitionEventById(Long id)
    {
        return faceRecognitionEventMapper.deleteFaceRecognitionEventById(id);
    }

    /**
     * 查询当天的人脸识别事件
     * 
     * @return 人脸识别事件集合
     */
    @Override
    public List<Map<String, Object>> selectTodayEvents()
    {
        return faceRecognitionEventMapper.selectTodayEvents();
    }

    /**
     * 统计当日各时段人流量
     * 
     * @return 各时段人流量列表
     */
    @Override
    public List<Map<String, Object>> countTodayFlow()
    {
        return faceRecognitionEventMapper.countTodayFlow();
    }

    // ===== 新增：v1 大屏列表 =====

    @Override
    public List<TodayFaceEventVO> selectTodayEventsV1()
    {
        // 这里直接返回 mapper 的结果即可，VO 映射在 XML 中已经完成
        return faceRecognitionEventMapper.selectTodayEventsV1();
    }

    // ===== 新增：事件 + 身份详情 =====

    @Override
    public FaceEventIdentityDetailVO getIdentityDetail(Long eventId)
    {
        Map<String, Object> map = faceRecognitionEventMapper.selectEventIdentityDetail(eventId);
        if (map == null) {
            return null;
        }

        FaceEventIdentityDetailVO vo = new FaceEventIdentityDetailVO();

        // ------- 事件部分 -------
        FaceEventIdentityDetailVO.EventInfo eventInfo = new FaceEventIdentityDetailVO.EventInfo();
        eventInfo.setEventId(getLong(map.get("eventId")));
        eventInfo.setMachineId(getLong(map.get("machineId")));
        eventInfo.setDeviceName((String) map.get("deviceName"));
        eventInfo.setRecognitionTime(getDate(map.get("recognitionTime")));
        eventInfo.setDepartureTime(getDate(map.get("departureTime")));
        eventInfo.setConfidence(getFloat(map.get("confidence")));
        eventInfo.setDetectionImg((String) map.get("detectionImg"));
        vo.setEvent(eventInfo);

        // ------- 身份部分 -------
        FaceEventIdentityDetailVO.IdentityInfo identityInfo = new FaceEventIdentityDetailVO.IdentityInfo();
        String identityType = (String) map.get("identityType");
        identityInfo.setIdentityType(identityType);
        identityInfo.setId(getLong(map.get("faceId")));

        if ("PERSON".equalsIgnoreCase(identityType)) {
            String personName = (String) map.get("personName");
            identityInfo.setDisplayName(personName);
            identityInfo.setName(personName);
            identityInfo.setPersonType((String) map.get("personType"));
            identityInfo.setJobNo((String) map.get("jobNo"));
            identityInfo.setDeptName((String) map.get("deptName"));
            identityInfo.setPhone((String) map.get("phone"));
            identityInfo.setIdCard((String) map.get("idCard"));
            identityInfo.setFaceImg((String) map.get("personFaceImg"));
            identityInfo.setGender(getInteger(map.get("personGender")));
            identityInfo.setAge(getInteger(map.get("personAge")));
            // 这里暂时没有取 remark，可后续从 face_person 增加字段
        } else if ("STRANGER".equalsIgnoreCase(identityType)) {
            String strangerName = (String) map.get("strangerDisplayName");
            identityInfo.setDisplayName(strangerName);
            identityInfo.setName(strangerName);
            identityInfo.setFaceImg((String) map.get("strangerFaceImg"));
            identityInfo.setGender(getInteger(map.get("strangerGender")));
            identityInfo.setAge(getInteger(map.get("strangerAge")));
            identityInfo.setRemark((String) map.get("strangerRemark"));
        }

        vo.setIdentity(identityInfo);
        return vo;
    }

    // ===== 一些类型安全的小工具方法，避免强转出错 =====

    private Long getLong(Object obj) {
        if (obj == null) {
            return null;
        }
        if (obj instanceof Long) {
            return (Long) obj;
        }
        if (obj instanceof Number) {
            return ((Number) obj).longValue();
        }
        return Long.valueOf(obj.toString());
    }

    private Integer getInteger(Object obj) {
        if (obj == null) {
            return null;
        }
        if (obj instanceof Integer) {
            return (Integer) obj;
        }
        if (obj instanceof Number) {
            return ((Number) obj).intValue();
        }
        if (obj instanceof Boolean) {
            return ((Boolean) obj) ? 1 : 0;
        }
        String str = obj.toString();
        if ("true".equalsIgnoreCase(str)) {
            return 1;
        }
        if ("false".equalsIgnoreCase(str)) {
            return 0;
        }
        try {
            return Integer.valueOf(str);
        } catch (NumberFormatException e) {
            return null; // 或者 return 0; 根据业务需求，这里先返回 null 避免报错
        }
    }

    private Float getFloat(Object obj) {
        if (obj == null) {
            return null;
        }
        if (obj instanceof Float) {
            return (Float) obj;
        }
        if (obj instanceof Number) {
            return ((Number) obj).floatValue();
        }
        return Float.valueOf(obj.toString());
    }

    private java.util.Date getDate(Object obj) {
        if (obj == null) {
            return null;
        }
        if (obj instanceof java.util.Date) {
            return (java.util.Date) obj;
        }
        if (obj instanceof java.time.LocalDateTime) {
            return java.util.Date.from(((java.time.LocalDateTime) obj).atZone(java.time.ZoneId.systemDefault()).toInstant());
        }
        return null;
    }
}
