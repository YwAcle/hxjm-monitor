package edu.cqupt.hxjm.algdeployment.domain;

import edu.cqupt.hxjm.common.annotation.Excel;
import edu.cqupt.hxjm.common.core.domain.BaseEntity;

/**
 * 算法部署管理对象 alg_deployment_management
 * 
 * @author zyn
 * @date 2024-02-28
 */
public class AlgDeploymentManagement extends BaseEntity
{
    private static final long serialVersionUID = 1L;

    /** 自增ID */
    private Long id;

    /** 算法名称 */
    @Excel(name = "算法名称")
    private String algBkName;

    /** 算法类型 */
    @Excel(name = "算法类型")
    private Integer algBkType;

    /** 算法请求头 */
    @Excel(name = "算法请求头")
    private String algBkApiHead;

    /** 启用标志 */
    @Excel(name = "启用标志")
    private Integer status;

    /** 设备状态表名 */
    @Excel(name = "设备状态表名")
    private String tableName;

    /** 备注 */
    @Excel(name = "备注")
    private String remark;

    public void setId(Long id) 
    {
        this.id = id;
    }

    public Long getId() 
    {
        return id;
    }

    public void setAlgBkName(String algBkName) 
    {
        this.algBkName = algBkName;
    }

    public String getAlgBkName() 
    {
        return algBkName;
    }

    public void setAlgBkType(Integer algBkType) 
    {
        this.algBkType = algBkType;
    }

    public Integer getAlgBkType() 
    {
        return algBkType;
    }

    public void setAlgBkApiHead(String algBkApiHead) 
    {
        this.algBkApiHead = algBkApiHead;
    }

    public String getAlgBkApiHead() 
    {
        return algBkApiHead;
    }

    public void setStatus(Integer status) 
    {
        this.status = status;
    }

    public Integer getStatus() 
    {
        return status;
    }

    public void setTableName(String tableName) 
    {
        this.tableName = tableName;
    }

    public String getTableName() 
    {
        return tableName;
    }

    public void setRemark(String remark)
    {
        this.remark = remark;
    }

    public String getRemark()
    {
        return remark;
    }
} 