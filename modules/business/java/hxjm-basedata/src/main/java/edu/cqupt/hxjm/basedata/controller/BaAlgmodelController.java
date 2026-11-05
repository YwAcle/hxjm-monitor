package edu.cqupt.hxjm.basedata.controller;

import java.util.List;
import javax.servlet.http.HttpServletResponse;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;
import edu.cqupt.hxjm.common.annotation.Log;
import edu.cqupt.hxjm.common.core.controller.BaseController;
import edu.cqupt.hxjm.common.core.domain.AjaxResult;
import edu.cqupt.hxjm.common.enums.BusinessType;
import edu.cqupt.hxjm.basedata.domain.BaAlgmodel;
import edu.cqupt.hxjm.basedata.service.IBaAlgmodelService;
import edu.cqupt.hxjm.common.utils.poi.ExcelUtil;
import edu.cqupt.hxjm.common.core.page.TableDataInfo;
import org.springframework.web.multipart.MultipartFile;

/**
 * 模型信息Controller
 * 
 * @author 钟先生不想写代码
 * @date 2024-11-25
 */
@RestController
@RequestMapping("/basedata/algmodel")
public class BaAlgmodelController extends BaseController
{
    @Autowired
    private IBaAlgmodelService baAlgmodelService;

    /**
     * 查询模型信息列表
     */
    @PreAuthorize("@ss.hasPermi('basedata:algmodel:list')")
    @GetMapping("/list")
    public TableDataInfo list(BaAlgmodel baAlgmodel)
    {
        startPage();
        List<BaAlgmodel> list = baAlgmodelService.selectBaAlgmodelList(baAlgmodel);
        return getDataTable(list);
    }

    /**
     * 导出模型信息列表
     */
    @PreAuthorize("@ss.hasPermi('basedata:algmodel:export')")
    @Log(title = "模型信息", businessType = BusinessType.EXPORT)
    @PostMapping("/export")
    public void export(HttpServletResponse response, BaAlgmodel baAlgmodel)
    {
        List<BaAlgmodel> list = baAlgmodelService.selectBaAlgmodelList(baAlgmodel);
        ExcelUtil<BaAlgmodel> util = new ExcelUtil<BaAlgmodel>(BaAlgmodel.class);
        util.exportExcel(response, list, "模型信息数据");
    }

    /**
     * 获取模型信息详细信息
     */
    @PreAuthorize("@ss.hasPermi('basedata:algmodel:query')")
    @GetMapping(value = "/{algmodelId}")
    public AjaxResult getInfo(@PathVariable("algmodelId") Long algmodelId)
    {
        return success(baAlgmodelService.selectBaAlgmodelByAlgmodelId(algmodelId));
    }

    /**
     * 新增模型信息
     */
    @PreAuthorize("@ss.hasPermi('basedata:algmodel:add')")
    @Log(title = "模型信息", businessType = BusinessType.INSERT)
    @PostMapping
    public AjaxResult add(@RequestPart("baAlgmodel") BaAlgmodel baAlgmodel,
                          @RequestPart(value = "imgData", required = false) MultipartFile file) throws Exception
    {
        return toAjax(baAlgmodelService.insertBaAlgmodel(baAlgmodel,file));
    }

    /**
     * 修改模型信息
     */
    @PreAuthorize("@ss.hasPermi('basedata:algmodel:edit')")
    @Log(title = "模型信息", businessType = BusinessType.UPDATE)
    @PutMapping
    public AjaxResult edit(@RequestPart("baAlgmodel") BaAlgmodel baAlgmodel,
                           @RequestPart(value = "imgData", required = false) MultipartFile file) throws Exception
    {
        return toAjax(baAlgmodelService.updateBaAlgmodel(baAlgmodel,file));
    }

    /**
     * 删除模型信息
     */
    @PreAuthorize("@ss.hasPermi('basedata:algmodel:remove')")
    @Log(title = "模型信息", businessType = BusinessType.DELETE)
	@DeleteMapping("/{algmodelIds}")
    public AjaxResult remove(@PathVariable Long[] algmodelIds)
    {
        return toAjax(baAlgmodelService.deleteBaAlgmodelByAlgmodelIds(algmodelIds));
    }
}
