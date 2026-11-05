package edu.cqupt.hxjm.basedata.controller;

import java.util.List;
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
import edu.cqupt.hxjm.basedata.domain.BaMachine;
import edu.cqupt.hxjm.basedata.service.IBaMachineService;
import edu.cqupt.hxjm.common.utils.poi.ExcelUtil;
import edu.cqupt.hxjm.common.core.page.TableDataInfo;

/**
 * 设备信息Controller
 * 
 * @author 钟先生不想写代码
 * @date 2024-11-04
 */
@RestController
@RequestMapping("/basedata/machine")
public class BaMachineController extends BaseController
{
    @Autowired
    private IBaMachineService baMachineService;

    /**
     * 查询设备信息列表
     */
    @PreAuthorize("@ss.hasPermi('basedata:machine:list')")
    @GetMapping("/list")
    public TableDataInfo list(BaMachine baMachine)
    {
        startPage();
        List<BaMachine> list = baMachineService.selectBaMachineList(baMachine);
        return getDataTable(list);
    }

    /**
     * 导出设备信息列表
     */
    @PreAuthorize("@ss.hasPermi('basedata:machine:export')")
    @Log(title = "设备信息", businessType = BusinessType.EXPORT)
    @PostMapping("/export")
    public void export(HttpServletResponse response, BaMachine baMachine)
    {
        List<BaMachine> list = baMachineService.selectBaMachineList(baMachine);
        ExcelUtil<BaMachine> util = new ExcelUtil<BaMachine>(BaMachine.class);
        util.exportExcel(response, list, "设备信息数据");
    }

    /**
     * 获取设备信息详细信息
     */
    @PreAuthorize("@ss.hasPermi('basedata:machine:query')")
    @GetMapping(value = "/{machineId}")
    public AjaxResult getInfo(@PathVariable("machineId") Long machineId)
    {
        return success(baMachineService.selectBaMachineByMachineId(machineId));
    }

    /**
     * 新增设备信息
     */
    @PreAuthorize("@ss.hasPermi('basedata:machine:add')")
    @Log(title = "设备信息", businessType = BusinessType.INSERT)
    @PostMapping
    public AjaxResult add(@RequestBody BaMachine baMachine)
    {
        return toAjax(baMachineService.insertBaMachine(baMachine));
    }

    /**
     * 修改设备信息
     */
    @PreAuthorize("@ss.hasPermi('basedata:machine:edit')")
    @Log(title = "设备信息", businessType = BusinessType.UPDATE)
    @PutMapping
    public AjaxResult edit(@RequestBody BaMachine baMachine)
    {
        return toAjax(baMachineService.updateBaMachine(baMachine));
    }

    /**
     * 删除设备信息
     */
    @PreAuthorize("@ss.hasPermi('basedata:machine:remove')")
    @Log(title = "设备信息", businessType = BusinessType.DELETE)
	@DeleteMapping("/{machineIds}")
    public AjaxResult remove(@PathVariable Long[] machineIds)
    {
        return toAjax(baMachineService.deleteBaMachineByMachineIds(machineIds));
    }
}
