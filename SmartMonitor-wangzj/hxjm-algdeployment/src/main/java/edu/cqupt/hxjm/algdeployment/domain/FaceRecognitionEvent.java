package edu.cqupt.hxjm.algdeployment.domain;

import java.util.Date;
import com.fasterxml.jackson.annotation.JsonFormat;
import edu.cqupt.hxjm.common.annotation.Excel;
import edu.cqupt.hxjm.common.core.domain.BaseEntity;

/**
 * 人脸识别事件对象 face_recognition_events
 * 
 * @author zyn
 * @date 2024-02-28
 */
public class FaceRecognitionEvent extends BaseEntity
{
    private static final long serialVersionUID = 1L;

    /** 自增ID */
    private Long id;

    /** 轨迹ID */
    @Excel(name = "轨迹ID")
    private String trackId;

    /** 关联设备 */
    @Excel(name = "关联设备")
    private Long machineId;

    /** 人脸ID */
    @Excel(name = "人脸ID")
    private String faceId;

    /** 识别置信度 */
    @Excel(name = "识别置信度")
    private Float confidence;

    /** 识别时间 */
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    @Excel(name = "识别时间", width = 30, dateFormat = "yyyy-MM-dd HH:mm:ss")
    private Date recognitionTime;

    /** 离开时间 */
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    @Excel(name = "离开时间", width = 30, dateFormat = "yyyy-MM-dd HH:mm:ss")
    private Date departureTime;

    /** 检测图片 */
    @Excel(name = "检测图片")
    private byte[] detectionImg;

    /** 身份类型 */
    @Excel(name = "身份类型")
    private String identityType;

    public String getIdentityType() {
        return identityType;
    }

    public void setIdentityType(String identityType) {
        this.identityType = identityType;
    }

    public void setId(Long id) 
    {
        this.id = id;
    }

    public Long getId() 
    {
        return id;
    }

    public void setTrackId(String trackId) 
    {
        this.trackId = trackId;
    }

    public String getTrackId() 
    {
        return trackId;
    }

    public void setMachineId(Long machineId) 
    {
        this.machineId = machineId;
    }

    public Long getMachineId() 
    {
        return machineId;
    }

    public void setFaceId(String faceId) 
    {
        this.faceId = faceId;
    }

    public String getFaceId() 
    {
        return faceId;
    }

    public void setConfidence(Float confidence) 
    {
        this.confidence = confidence;
    }

    public Float getConfidence() 
    {
        return confidence;
    }

    public void setRecognitionTime(Date recognitionTime) 
    {
        this.recognitionTime = recognitionTime;
    }

    public Date getRecognitionTime() 
    {
        return recognitionTime;
    }

    public void setDepartureTime(Date departureTime) 
    {
        this.departureTime = departureTime;
    }

    public Date getDepartureTime() 
    {
        return departureTime;
    }

    public void setDetectionImg(byte[] detectionImg) 
    {
        this.detectionImg = detectionImg;
    }

    public byte[] getDetectionImg() 
    {
        return detectionImg;
    }
}