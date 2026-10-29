package edu.cqupt.hxjm.algdeployment.controller;

import java.util.List;
import java.util.Map;
import javax.servlet.http.HttpServletResponse;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import edu.cqupt.hxjm.common.annotation.Log;
import edu.cqupt.hxjm.common.core.controller.BaseController;
import edu.cqupt.hxjm.common.core.domain.AjaxResult;
import edu.cqupt.hxjm.common.enums.BusinessType;
import edu.cqupt.hxjm.algdeployment.domain.AlgDeploymentManagement;
import edu.cqupt.hxjm.algdeployment.service.IAlgDeploymentManagementService;
import edu.cqupt.hxjm.common.utils.poi.ExcelUtil;
import edu.cqupt.hxjm.common.core.page.TableDataInfo;

/**
 * 算法部署管理Controller
 * 
 * @author zyn
 * @date 2024-02-28
 */
@RestController
@RequestMapping("/algdeployment/management")
public class AlgDeploymentManagementController extends BaseController
{
    @Autowired
    private IAlgDeploymentManagementService algDeploymentManagementService;

    /**
     * 查询算法部署管理列表
     */
    @PreAuthorize("@ss.hasPermi('algdeployment:management:list')")
    @GetMapping("/list")
    public TableDataInfo list(AlgDeploymentManagement algDeploymentManagement)
    {
        startPage();
        List<AlgDeploymentManagement> list = algDeploymentManagementService.selectAlgDeploymentManagementList(algDeploymentManagement);
        return getDataTable(list);
    }

    /**
     * 导出算法部署管理列表
     */
    @PreAuthorize("@ss.hasPermi('algdeployment:management:export')")
    @Log(title = "算法部署管理", businessType = BusinessType.EXPORT)
    @PostMapping("/export")
    public void export(HttpServletResponse response, AlgDeploymentManagement algDeploymentManagement)
    {
        List<AlgDeploymentManagement> list = algDeploymentManagementService.selectAlgDeploymentManagementList(algDeploymentManagement);
        ExcelUtil<AlgDeploymentManagement> util = new ExcelUtil<AlgDeploymentManagement>(AlgDeploymentManagement.class);
        util.exportExcel(response, list, "算法部署管理数据");
    }

    /**
     * 获取算法部署管理详细信息
     */
    @PreAuthorize("@ss.hasPermi('algdeployment:management:query')")
    @GetMapping(value = "/{id}")
    public AjaxResult getInfo(@PathVariable("id") Long id)
    {
        return success(algDeploymentManagementService.selectAlgDeploymentManagementById(id));
    }

    /**
     * 新增算法部署管理
     */
    @PreAuthorize("@ss.hasPermi('algdeployment:management:add')")
    @Log(title = "算法部署管理", businessType = BusinessType.INSERT)
    @PostMapping
    public AjaxResult add(@RequestBody AlgDeploymentManagement algDeploymentManagement)
    {
        return toAjax(algDeploymentManagementService.insertAlgDeploymentManagement(algDeploymentManagement));
    }

    /**
     * 修改算法部署管理
     */
    @PreAuthorize("@ss.hasPermi('algdeployment:management:edit')")
    @Log(title = "算法部署管理", businessType = BusinessType.UPDATE)
    @PutMapping
    public AjaxResult edit(@RequestBody AlgDeploymentManagement algDeploymentManagement)
    {
        return toAjax(algDeploymentManagementService.updateAlgDeploymentManagement(algDeploymentManagement));
    }

    /**
     * 删除算法部署管理
     */
    @PreAuthorize("@ss.hasPermi('algdeployment:management:remove')")
    @Log(title = "算法部署管理", businessType = BusinessType.DELETE)
	@DeleteMapping("/{ids}")
    public AjaxResult remove(@PathVariable Long[] ids)
    {
        return toAjax(algDeploymentManagementService.deleteAlgDeploymentManagementByIds(ids));
    }

    /**
     * 获取所有可用设备列表
     */
    @GetMapping("/getMachineList")
    public AjaxResult getMachineList()
    {
        List<Map<String, Object>> list = algDeploymentManagementService.getMachineList();
        return success(list);
    }
} 