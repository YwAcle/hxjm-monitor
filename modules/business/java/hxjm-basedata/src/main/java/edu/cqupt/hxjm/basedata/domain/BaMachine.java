package edu.cqupt.hxjm.basedata.domain;

import org.apache.commons.lang3.builder.ToStringBuilder;
import org.apache.commons.lang3.builder.ToStringStyle;
import edu.cqupt.hxjm.common.annotation.Excel;
import edu.cqupt.hxjm.common.core.domain.BaseEntity;

/**
 * 设备信息对象 ba_machine
 * 
 * @author 钟先生不想写代码
 * @date 2024-11-04
 */
public class BaMachine extends BaseEntity
{
    private static final long serialVersionUID = 1L;

    /** 主键 */
    private Long machineId;

    /** 设备编码 */
    @Excel(name = "设备编码")
    private String machineCode;

    /** 设备名称 */
    @Excel(name = "设备名称")
    private String machineName;

    /** 设备流 */
    @Excel(name = "设备流")
    private String videoUrl;

    /** 所属区域id */
    private Long locationId;

    /** 设备状态 */
    @Excel(name = "设备状态")
    private Long status;

    /** 启用标志 */
    @Excel(name = "启用标志")
    private Long isvalid;

    /** 分辨率 */
    @Excel(name = "分辨率")
    private String resolution;

    /** 解码器 */ 
    @Excel(name = "解码器")
    private String decoder;

    public void setMachineId(Long machineId) 
    {
        this.machineId = machineId;
    }

    public Long getMachineId() 
    {
        return machineId;
    }
    public void setMachineCode(String machineCode) 
    {
        this.machineCode = machineCode;
    }

    public String getMachineCode() 
    {
        return machineCode;
    }
    public void setMachineName(String machineName) 
    {
        this.machineName = machineName;
    }

    public String getMachineName() 
    {
        return machineName;
    }

    public String getVideoUrl() {
        return videoUrl;
    }

    public void setVideoUrl(String videoUrl) {
        this.videoUrl = videoUrl;
    }

    public void setLocationId(Long locationId)
    {
        this.locationId = locationId;
    }

    public Long getLocationId() 
    {
        return locationId;
    }
    public void setStatus(Long status) 
    {
        this.status = status;
    }

    public Long getStatus() 
    {
        return status;
    }
    public void setIsvalid(Long isvalid) 
    {
        this.isvalid = isvalid;
    }

    public Long getIsvalid() 
    {
        return isvalid;
    }

    public void setResolution(String resolution) 
    {
        this.resolution = resolution;
    }

    public String getResolution() 
    {
        return resolution;
    }

    public void setDecoder(String decoder) 
    {
        this.decoder = decoder;
    }

    public String getDecoder() 
    {
        return decoder;
    }

    @Override
    public String toString() {
        return new ToStringBuilder(this,ToStringStyle.MULTI_LINE_STYLE)
            .append("machineId", getMachineId())
            .append("machineCode", getMachineCode())
            .append("machineName", getMachineName())
            .append("videoUrl", getVideoUrl())
            .append("locationId", getLocationId())
            .append("status", getStatus())
            .append("isvalid", getIsvalid())
            .append("resolution", getResolution())
            .append("decoder", getDecoder())
            .append("createTime", getCreateTime())
            .append("updateTime", getUpdateTime())
            .toString();
    }
}
