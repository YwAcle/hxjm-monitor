package edu.cqupt.hxjm.algdeployment.domain.VO;

import java.util.Date;

public class FaceEventIdentityDetailVO {

    /** 事件信息 */
    private EventInfo event;

    /** 身份信息（正式人员或陌生人统一结构） */
    private IdentityInfo identity;

    // ---------- inner classes ----------

    public static class EventInfo {
        private Long eventId;
        private Long machineId;
        private String deviceName;
        private Date recognitionTime;
        private Date departureTime;
        private Float confidence;
        private String detectionImg;

        public Long getEventId() {
            return eventId;
        }

        public void setEventId(Long eventId) {
            this.eventId = eventId;
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

    public static class IdentityInfo {
        /** PERSON / STRANGER */
        private String identityType;
        /** PERSON: face_person.id; STRANGER: face_stranger.id */
        private Long id;
        /** 统一展示名称 */
        private String displayName;

        // PERSON 时常用字段
        private String name;
        private String personType;
        private String jobNo;
        private String deptName;
        private String phone;
        private String idCard;
        private String faceImg;

        // 公共字段
        private Integer age;
        private Integer gender; // 0/1/2
        private String remark;

        // ---------- getter / setter ----------

        public String getIdentityType() {
            return identityType;
        }

        public void setIdentityType(String identityType) {
            this.identityType = identityType;
        }

        public Long getId() {
            return id;
        }

        public void setId(Long id) {
            this.id = id;
        }

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public String getPersonType() {
            return personType;
        }

        public void setPersonType(String personType) {
            this.personType = personType;
        }

        public String getJobNo() {
            return jobNo;
        }

        public void setJobNo(String jobNo) {
            this.jobNo = jobNo;
        }

        public String getDeptName() {
            return deptName;
        }

        public void setDeptName(String deptName) {
            this.deptName = deptName;
        }

        public String getPhone() {
            return phone;
        }

        public void setPhone(String phone) {
            this.phone = phone;
        }

        public String getIdCard() {
            return idCard;
        }

        public void setIdCard(String idCard) {
            this.idCard = idCard;
        }

        public String getFaceImg() {
            return faceImg;
        }

        public void setFaceImg(String faceImg) {
            this.faceImg = faceImg;
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }

        public Integer getGender() {
            return gender;
        }

        public void setGender(Integer gender) {
            this.gender = gender;
        }

        public String getRemark() {
            return remark;
        }

        public void setRemark(String remark) {
            this.remark = remark;
        }
    }

    // ---------- getter / setter ----------

    public EventInfo getEvent() {
        return event;
    }

    public void setEvent(EventInfo event) {
        this.event = event;
    }

    public IdentityInfo getIdentity() {
        return identity;
    }

    public void setIdentity(IdentityInfo identity) {
        this.identity = identity;
    }
}
