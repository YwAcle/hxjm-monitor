package edu.cqupt.hxjm.system.domain;

import java.util.Date;
import com.fasterxml.jackson.annotation.JsonFormat;
import org.apache.commons.lang3.builder.ToStringBuilder;
import org.apache.commons.lang3.builder.ToStringStyle;
import edu.cqupt.hxjm.common.annotation.Excel;
import edu.cqupt.hxjm.common.core.domain.BaseEntity;

/**
 * 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等对象 face_database
 * 
 * @author zyn
 * @date 2025-02-19
 */
public class FaceDatabase extends BaseEntity
{
    private static final long serialVersionUID = 1L;

    /** 自增ID，唯一标识每条记录 */
    private Long id;

    /** 人脸ID，唯一标识每个特征（通常是UUID） */
    @Excel(name = "人脸ID", readConverterExp = "通=常是UUID")
    private String faceId;

    /** 人员姓名 */
    @Excel(name = "人员姓名")
    private String userName;

    /** 人脸特征向量，用于存储提取的人脸特征（例如128维、512维向量） */
    @Excel(name = "人脸特征向量", readConverterExp = "例=如128维、512维向量")
    private String faceEncoding;

    /** 人脸原始图像，用于存储采集到的图像数据或图像路径 */
    @Excel(name = "人脸原始图像")
    private String faceImage;

    /** 人脸缩略图，用于存储缩小版的人脸图像，用于展示 */
    @Excel(name = "人脸缩略图")
    private String faceImageThumbnail;

    /** 元数据（如：年龄、性别等信息），以JSON格式存储 */
    @Excel(name = "元数据", readConverterExp = "如=：年龄、性别等信息")
    private String metadata;

    /** 状态，表示人脸记录当前的状态 */
    @Excel(name = "状态")
    private Long status;

    /** 性别 */
    @Excel(name = "性别")
    private Integer gender;

    /** 年龄 */
    @Excel(name = "年龄")
    private Integer age;

    /** 质量分数 */
    @Excel(name = "质量分数")
    private Double quality;

    public void setId(Long id) 
    {
        this.id = id;
    }

    public Long getId() 
    {
        return id;
    }
    public void setFaceId(String faceId) 
    {
        this.faceId = faceId;
    }

    public String getFaceId() 
    {
        return faceId;
    }
    public void setUserName(String userName) 
    {
        this.userName = userName;
    }

    public String getUserName() 
    {
        return userName;
    }
    public void setFaceEncoding(String faceEncoding) 
    {
        this.faceEncoding = faceEncoding;
    }

    public String getFaceEncoding() 
    {
        return faceEncoding;
    }
    public void setFaceImage(String faceImage) 
    {
        this.faceImage = faceImage;
    }

    public String getFaceImage() 
    {
        return faceImage;
    }
    public void setFaceImageThumbnail(String faceImageThumbnail) 
    {
        this.faceImageThumbnail = faceImageThumbnail;
    }

    public String getFaceImageThumbnail() 
    {
        return faceImageThumbnail;
    }
    public void setMetadata(String metadata) 
    {
        this.metadata = metadata;
    }

    public String getMetadata() 
    {
        return metadata;
    }
    public void setStatus(Long status) 
    {
        this.status = status;
    }

    public Long getStatus() 
    {
        return status;
    }

    public void setGender(Integer gender) 
    {
        this.gender = gender;
    }

    public Integer getGender() 
    {
        return gender;
    }

    public void setAge(Integer age) 
    {
        this.age = age;
    }

    public Integer getAge() 
    {
        return age;
    }

    public void setQuality(Double quality) 
    {
        this.quality = quality;
    }

    public Double getQuality() 
    {
        return quality;
    }

    @Override
    public String toString() {
        return new ToStringBuilder(this,ToStringStyle.MULTI_LINE_STYLE)
            .append("id", getId())
            .append("faceId", getFaceId())
            .append("userName", getUserName())
            .append("faceEncoding", getFaceEncoding())
            .append("faceImage", getFaceImage())
            .append("faceImageThumbnail", getFaceImageThumbnail())
            .append("metadata", getMetadata())
            .append("status", getStatus())
            .append("gender", getGender())
            .append("age", getAge())
            .append("quality", getQuality())
            .append("createTime", getCreateTime())
            .append("updateTime", getUpdateTime())
            .toString();
    }
}
