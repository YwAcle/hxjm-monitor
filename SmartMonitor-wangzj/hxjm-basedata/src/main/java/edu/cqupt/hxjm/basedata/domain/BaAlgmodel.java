package edu.cqupt.hxjm.basedata.domain;

import org.apache.commons.lang3.builder.ToStringBuilder;
import org.apache.commons.lang3.builder.ToStringStyle;
import edu.cqupt.hxjm.common.annotation.Excel;
import edu.cqupt.hxjm.common.core.domain.BaseEntity;
import org.springframework.web.multipart.MultipartFile;

/**
 * 模型信息对象 ba_algmodel
 *
 * @author 钟先生不想写代码
 * @date 2024-11-25
 */
public class BaAlgmodel extends BaseEntity
{
    private static final long serialVersionUID = 1L;

    /** 主键 */
    private Long algmodelId;

    /** 模型编码 */
    @Excel(name = "模型编码")
    private String algmodelCode;

    /** 模型名称 */
    @Excel(name = "模型名称")
    private String algmodelName;

    /** 模型引擎 */
    @Excel(name = "模型引擎")
    private String algmodelEngines;

    /** 模型输入 */
    @Excel(name = "模型输入")
    private String algmodelInput;

    /** 模型输出 */
    @Excel(name = "模型输出")
    private String algmodelOutput;

    /** 模型路径
 */
    @Excel(name = "模型路径 ")
    private String path;

    /** 算法类型id */
    @Excel(name = "算法类型id")
    private Long algtypeId;

    /** 模型名称 */
    @Excel(name = "算法类型名称")
    private String algtypeName;


    /** 启用 */
    @Excel(name = "启用")
    private Long isvalid;

    /** 封面图 */
    @Excel(name = "封面图")
    private String preview;

    /** 标签图 */
    @Excel(name = "标签图")
    private String icon;

    public String getAlgtypeName() {
        return algtypeName;
    }

    public void setAlgtypeName(String algtypeName) {
        this.algtypeName = algtypeName;
    }

    public void setAlgmodelId(Long algmodelId)
    {
        this.algmodelId = algmodelId;
    }

    public Long getAlgmodelId()
    {
        return algmodelId;
    }
    public void setAlgmodelCode(String algmodelCode)
    {
        this.algmodelCode = algmodelCode;
    }

    public String getAlgmodelCode()
    {
        return algmodelCode;
    }
    public void setAlgmodelName(String algmodelName)
    {
        this.algmodelName = algmodelName;
    }

    public String getAlgmodelName()
    {
        return algmodelName;
    }
    public void setAlgmodelEngines(String algmodelEngines)
    {
        this.algmodelEngines = algmodelEngines;
    }

    public String getAlgmodelEngines()
    {
        return algmodelEngines;
    }
    public void setPath(String path)
    {
        this.path = path;
    }

    public String getPath()
    {
        return path;
    }
    public void setAlgtypeId(Long algtypeId)
    {
        this.algtypeId = algtypeId;
    }

    public String getAlgmodelInput() {
        return algmodelInput;
    }

    public void setAlgmodelInput(String algmodelInput) {
        this.algmodelInput = algmodelInput;
    }

    public String getAlgmodelOutput() {
        return algmodelOutput;
    }

    public void setAlgmodelOutput(String algmodelOutput) {
        this.algmodelOutput = algmodelOutput;
    }

    public Long getAlgtypeId()
    {
        return algtypeId;
    }
    public void setIsvalid(Long isvalid)
    {
        this.isvalid = isvalid;
    }

    public Long getIsvalid()
    {
        return isvalid;
    }

    public void setPreview(String preview)
    {
        this.preview = preview;
    }

    public String getPreview()
    {
        return preview;
    }
    public void setIcon(String icon)
    {
        this.icon = icon;
    }

    public String getIcon()
    {
        return icon;
    }


    @Override
    public String toString() {
        return new ToStringBuilder(this,ToStringStyle.MULTI_LINE_STYLE)
            .append("algmodelId", getAlgmodelId())
            .append("algmodelCode", getAlgmodelCode())
            .append("algmodelName", getAlgmodelName())
            .append("algmodelEngines", getAlgmodelEngines())
            .append("path", getPath())
            .append("algmodelInput",getAlgmodelInput())
            .append("algmodelOutput",getAlgmodelOutput())
            .append("algtypeId", getAlgtypeId())
            .append("algtypeName", getAlgtypeName())
            .append("isvalid", getIsvalid())
            .append("remark", getRemark())
            .append("preview", getPreview())
            .append("icon", getIcon())
            .toString();
    }
}
