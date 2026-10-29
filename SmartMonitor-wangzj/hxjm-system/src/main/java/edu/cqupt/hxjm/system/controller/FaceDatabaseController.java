package edu.cqupt.hxjm.system.controller;

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
import edu.cqupt.hxjm.system.domain.FaceDatabase;
import edu.cqupt.hxjm.system.service.IFaceDatabaseService;
import edu.cqupt.hxjm.common.utils.poi.ExcelUtil;
import edu.cqupt.hxjm.common.core.page.TableDataInfo;
import edu.cqupt.hxjm.system.mapper.FaceDatabaseMapper;
import com.alibaba.fastjson2.JSON;
import java.util.ArrayList;

/**
 * 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等Controller
 * 
 * @author zyn
 * @date 2025-02-19
 */
@RestController
@RequestMapping("/system/face_database")
public class FaceDatabaseController extends BaseController
{
    @Autowired
    private IFaceDatabaseService faceDatabaseService;

    @Autowired
    private FaceDatabaseMapper faceDatabaseMapper;

    /**
     * 查询人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等列表
     */
    @PreAuthorize("@ss.hasPermi('system:face_database:list')")
    @GetMapping("/list")
    public TableDataInfo list(FaceDatabase faceDatabase)
    {
        startPage();
        List<FaceDatabase> list = faceDatabaseService.selectFaceDatabaseList(faceDatabase);
        return getDataTable(list);
    }

    /**
     * 导出人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等列表
     */
    @PreAuthorize("@ss.hasPermi('system:face_database:export')")
    @Log(title = "人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等", businessType = BusinessType.EXPORT)
    @PostMapping("/export")
    public void export(HttpServletResponse response, FaceDatabase faceDatabase)
    {
        List<FaceDatabase> list = faceDatabaseService.selectFaceDatabaseList(faceDatabase);
        ExcelUtil<FaceDatabase> util = new ExcelUtil<FaceDatabase>(FaceDatabase.class);
        util.exportExcel(response, list, "人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等数据");
    }

    /**
     * 获取人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等详细信息
     */
    @PreAuthorize("@ss.hasPermi('system:face_database:query')")
    @GetMapping(value = "/{id}")
    public AjaxResult getInfo(@PathVariable("id") Long id)
    {
        return success(faceDatabaseService.selectFaceDatabaseById(id));
    }

    /**
     * 新增人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     */
    @PreAuthorize("@ss.hasPermi('system:face_database:add')")
    @Log(title = "人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等", businessType = BusinessType.INSERT)
    @PostMapping
    public AjaxResult add(@RequestBody FaceDatabase faceDatabase)
    {
        return toAjax(faceDatabaseService.insertFaceDatabase(faceDatabase));
    }

    /**
     * 修改人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     */
    @PreAuthorize("@ss.hasPermi('system:face_database:edit')")
    @Log(title = "人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等", businessType = BusinessType.UPDATE)
    @PutMapping
    public AjaxResult edit(@RequestBody FaceDatabase faceDatabase)
    {
        return toAjax(faceDatabaseService.updateFaceDatabase(faceDatabase));
    }

    /**
     * 删除人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等
     */
    @PreAuthorize("@ss.hasPermi('system:face_database:remove')")
    @Log(title = "人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等", businessType = BusinessType.DELETE)
	@DeleteMapping("/{ids}")
    public AjaxResult remove(@PathVariable Long[] ids)
    {
        return toAjax(faceDatabaseService.deleteFaceDatabaseByIds(ids));
    }

    /**
     * 获取所有人脸信息
     */
    @GetMapping("/faces")
    public AjaxResult getAllFaces()
    {
        List<Map<String, Object>> faceList = faceDatabaseMapper.selectAllFaceInfo();
        return AjaxResult.success(faceList);
    }
}
