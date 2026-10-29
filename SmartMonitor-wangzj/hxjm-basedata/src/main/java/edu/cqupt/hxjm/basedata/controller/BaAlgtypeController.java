package edu.cqupt.hxjm.basedata.controller;

import java.util.List;
import java.util.Map;
import javax.servlet.http.HttpServletResponse;

import com.alibaba.fastjson2.JSONObject;
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
import edu.cqupt.hxjm.basedata.domain.BaAlgtype;
import edu.cqupt.hxjm.basedata.service.IBaAlgtypeService;
import edu.cqupt.hxjm.common.utils.poi.ExcelUtil;
import edu.cqupt.hxjm.common.core.page.TableDataInfo;

/**
 * 模型类型Controller
 * 
 * @author 钟先生不想写代码
 * @date 2024-11-25
 */
@RestController
@RequestMapping("/basedata/algtype")
public class BaAlgtypeController extends BaseController
{
    @Autowired
    private IBaAlgtypeService baAlgtypeService;

    /**
     * 查询模型类型列表
     */
    @PreAuthorize("@ss.hasPermi('basedata:algtype:list')")
    @GetMapping("/list")
    public TableDataInfo list(BaAlgtype baAlgtype)
    {
        startPage();
        List<BaAlgtype> list = baAlgtypeService.selectBaAlgtypeList(baAlgtype);
        return getDataTable(list);
    }

    /**
     * 导出模型类型列表
     */
    @PreAuthorize("@ss.hasPermi('basedata:algtype:export')")
    @Log(title = "模型类型", businessType = BusinessType.EXPORT)
    @PostMapping("/export")
    public void export(HttpServletResponse response, BaAlgtype baAlgtype)
    {
        List<BaAlgtype> list = baAlgtypeService.selectBaAlgtypeList(baAlgtype);
        ExcelUtil<BaAlgtype> util = new ExcelUtil<BaAlgtype>(BaAlgtype.class);
        util.exportExcel(response, list, "模型类型数据");
    }

    /**
     * 获取模型类型详细信息
     */
    @PreAuthorize("@ss.hasPermi('basedata:algtype:query')")
    @GetMapping(value = "/{algtypeId}")
    public AjaxResult getInfo(@PathVariable("algtypeId") Long algtypeId)
    {
        return success(baAlgtypeService.selectBaAlgtypeByAlgtypeId(algtypeId));
    }

    /**
     * 新增模型类型
     */
    @PreAuthorize("@ss.hasPermi('basedata:algtype:add')")
    @Log(title = "模型类型", businessType = BusinessType.INSERT)
    @PostMapping
    public AjaxResult add(@RequestBody BaAlgtype baAlgtype)
    {
        return toAjax(baAlgtypeService.insertBaAlgtype(baAlgtype));
    }

    /**
     * 修改模型类型
     */
    @PreAuthorize("@ss.hasPermi('basedata:algtype:edit')")
    @Log(title = "模型类型", businessType = BusinessType.UPDATE)
    @PutMapping
    public AjaxResult edit(@RequestBody BaAlgtype baAlgtype)
    {
        return toAjax(baAlgtypeService.updateBaAlgtype(baAlgtype));
    }

    /**
     * 删除模型类型
     */
    @PreAuthorize("@ss.hasPermi('basedata:algtype:remove')")
    @Log(title = "模型类型", businessType = BusinessType.DELETE)
	@DeleteMapping("/{algtypeIds}")
    public AjaxResult remove(@PathVariable Long[] algtypeIds)
    {
        return toAjax(baAlgtypeService.deleteBaAlgtypeByAlgtypeIds(algtypeIds));
    }

    /**
     * 查询大屏展示算法List
     */
    @GetMapping("/display")
    public AjaxResult getDisplayModelList()
    {
        ;
        return success(baAlgtypeService.getDisplayModelList());
    }
}
