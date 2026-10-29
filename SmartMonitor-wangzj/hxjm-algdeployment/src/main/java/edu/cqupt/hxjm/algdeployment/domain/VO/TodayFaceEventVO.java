package edu.cqupt.hxjm.algdeployment.domain.VO;

import java.util.Date;

public class TodayFaceEventVO {

    /** 事件ID */
    private Long eventId;

    /** 身份类型：PERSON/STRANGER */
    private String identityType;

    /** 人脸记录ID：PERSON -> face_person.id, STRANGER -> face_stranger.id */
    private Long faceId;

    /** 展示名称：正式人员=姓名，陌生人=陌生人_时间戳 */
    private String displayName;

    /** 设备ID */
    private Long machineId;

    /** 设备名称 */
    private String deviceName;

    /** 识别时间 */
    private Date recognitionTime;

    /** 离开时间 */
    private Date departureTime;

    /** 置信度 */
    private Float confidence;

    /** 抓拍图 URL/路径 */
    private String detectionImg;

    // ---------- getter / setter ----------

    public Long getEventId() {
        return eventId;
    }

    public void setEventId(Long eventId) {
        this.eventId = eventId;
    }

    public String getIdentityType() {
        return identityType;
    }

    public void setIdentityType(String identityType) {
        this.identityType = identityType;
    }

    public Long getFaceId() {
        return faceId;
    }

    public void setFaceId(Long faceId) {
        this.faceId = faceId;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public Long getMachineId() {
        return machineId;
    }

    public void setMachineId(Long machineId) {
        this.machineId = machineId;
    }

    public String getDeviceName() {
        return deviceName;
    }

    public void setDeviceName(String deviceName) {
        this.deviceName = deviceName;
    }

    public Date getRecognitionTime() {
        return recognitionTime;
    }

    public void setRecognitionTime(Date recognitionTime) {
        this.recognitionTime = recognitionTime;
    }

    public Date getDepartureTime() {
        return departureTime;
    }

    public void setDepartureTime(Date departureTime) {
        this.departureTime = departureTime;
    }

    public Float getConfidence() {
        return confidence;
    }

    public void setConfidence(Float confidence) {
        this.confidence = confidence;
    }

    public String getDetectionImg() {
        return detectionImg;
    }

    public void setDetectionImg(String detectionImg) {
        this.detectionImg = detectionImg;
    }
}
