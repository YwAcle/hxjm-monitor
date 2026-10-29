package edu.cqupt.hxjm.basedata.domain;

import org.apache.commons.lang3.builder.ToStringBuilder;
import org.apache.commons.lang3.builder.ToStringStyle;
import edu.cqupt.hxjm.common.annotation.Excel;
import edu.cqupt.hxjm.common.core.domain.BaseEntity;

/**
 * 模型类型对象 ba_algtype
 * 
 * @author 钟先生不想写代码
 * @date 2024-11-25
 */
public class BaAlgtype extends BaseEntity
{
    private static final long serialVersionUID = 1L;

    /** 主键 */
    private Long algtypeId;

    /** 算法类型编码 */
    @Excel(name = "算法类型编码")
    private String algtypeCode;

    /** 算法类型名称 */
    @Excel(name = "算法类型名称")
    private String algtypeName;

    /** 是否展示 */
    @Excel(name = "是否展示")
    private Long isvalid;

    public void setAlgtypeId(Long algtypeId) 
    {
        this.algtypeId = algtypeId;
    }

    public Long getAlgtypeId() 
    {
        return algtypeId;
    }
    public void setAlgtypeCode(String algtypeCode) 
    {
        this.algtypeCode = algtypeCode;
    }

    public String getAlgtypeCode() 
    {
        return algtypeCode;
    }
    public void setAlgtypeName(String algtypeName) 
    {
        this.algtypeName = algtypeName;
    }

    public String getAlgtypeName() 
    {
        return algtypeName;
    }
    public void setIsvalid(Long isvalid) 
    {
        this.isvalid = isvalid;
    }

    public Long getIsvalid() 
    {
        return isvalid;
    }

    @Override
    public String toString() {
        return new ToStringBuilder(this,ToStringStyle.MULTI_LINE_STYLE)
            .append("algtypeId", getAlgtypeId())
            .append("algtypeCode", getAlgtypeCode())
            .append("algtypeName", getAlgtypeName())
            .append("isvalid", getIsvalid())
            .append("remark", getRemark())
            .toString();
    }
}
