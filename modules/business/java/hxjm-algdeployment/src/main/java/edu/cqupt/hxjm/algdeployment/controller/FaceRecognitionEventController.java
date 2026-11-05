package edu.cqupt.hxjm.algdeployment.controller;

import java.util.List;
import java.util.Map;
import javax.servlet.http.HttpServletResponse;

import edu.cqupt.hxjm.algdeployment.domain.VO.FaceEventIdentityDetailVO;
import edu.cqupt.hxjm.algdeployment.domain.VO.TodayFaceEventVO;
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
import edu.cqupt.hxjm.common.annotation.Anonymous;
import edu.cqupt.hxjm.common.core.controller.BaseController;
import edu.cqupt.hxjm.common.core.domain.AjaxResult;
import edu.cqupt.hxjm.common.enums.BusinessType;
import edu.cqupt.hxjm.algdeployment.domain.FaceRecognitionEvent;
import edu.cqupt.hxjm.common.utils.poi.ExcelUtil;
import edu.cqupt.hxjm.common.core.page.TableDataInfo;
import edu.cqupt.hxjm.algdeployment.service.IFaceRecognitionEventService;
/**
 * 人脸识别事件Controller
 * 
 * @author zyn
 * @date 2024-02-28
 */
@RestController
@RequestMapping("/algdeployment/face_recognition_events")
public class FaceRecognitionEventController extends BaseController
{
    @Autowired
    private IFaceRecognitionEventService faceRecognitionEventService;

    /**
     * 查询人脸识别事件列表
     */
    @PreAuthorize("@ss.hasPermi('algdeployment:face_recognition_events:list')")
    @GetMapping("/list")
    public TableDataInfo list(FaceRecognitionEvent faceRecognitionEvent)
    {
        startPage();
        List<FaceRecognitionEvent> list = faceRecognitionEventService.selectFaceRecognitionEventList(faceRecognitionEvent);
        return getDataTable(list);
    }

    /**
     * 导出人脸识别事件列表
     */
    @PreAuthorize("@ss.hasPermi('algdeployment:face_recognition_events:export')")
    @Log(title = "人脸识别事件", businessType = BusinessType.EXPORT)
    @PostMapping("/export")
    public void export(HttpServletResponse response, FaceRecognitionEvent faceRecognitionEvent)
    {
        List<FaceRecognitionEvent> list = faceRecognitionEventService.selectFaceRecognitionEventList(faceRecognitionEvent);
        ExcelUtil<FaceRecognitionEvent> util = new ExcelUtil<FaceRecognitionEvent>(FaceRecognitionEvent.class);
        util.exportExcel(response, list, "人脸识别事件数据");
    }

    /**
     * 获取人脸识别事件详细信息
     */
    @PreAuthorize("@ss.hasPermi('algdeployment:face_recognition_events:query')")
    @GetMapping(value = "/{id}")
    public AjaxResult getInfo(@PathVariable("id") Long id)
    {
        return success(faceRecognitionEventService.selectFaceRecognitionEventById(id));
    }

    /**
     * 新增人脸识别事件
     */
    @PreAuthorize("@ss.hasPermi('algdeployment:face_recognition_events:add')")
    @Log(title = "人脸识别事件", businessType = BusinessType.INSERT)
    @PostMapping
    public AjaxResult add(@RequestBody FaceRecognitionEvent faceRecognitionEvent)
    {
        return toAjax(faceRecognitionEventService.insertFaceRecognitionEvent(faceRecognitionEvent));
    }

    /**
     * 修改人脸识别事件
     */
    @PreAuthorize("@ss.hasPermi('algdeployment:face_recognition_events:edit')")
    @Log(title = "人脸识别事件", businessType = BusinessType.UPDATE)
    @PutMapping
    public AjaxResult edit(@RequestBody FaceRecognitionEvent faceRecognitionEvent)
    {
        return toAjax(faceRecognitionEventService.updateFaceRecognitionEvent(faceRecognitionEvent));
    }

    /**
     * 删除人脸识别事件
     */
    @PreAuthorize("@ss.hasPermi('algdeployment:face_recognition_events:remove')")
    @Log(title = "人脸识别事件", businessType = BusinessType.DELETE)
	@DeleteMapping("/{ids}")
    public AjaxResult remove(@PathVariable Long[] ids)
    {
        return toAjax(faceRecognitionEventService.deleteFaceRecognitionEventByIds(ids));
    }

    /**
     * 查询当天的人脸识别事件
     */
    @GetMapping("/getTodayEventsv")
    public AjaxResult getTodayEventsv()
    {
        List<Map<String, Object>> list = faceRecognitionEventService.selectTodayEvents();
        return success(list);
    }

    /**
     * 获取当日各时段人流量
     */
    @GetMapping("/todayFlow")
    public AjaxResult getTodayFlow()
    {
        List<Map<String, Object>> flowList = faceRecognitionEventService.countTodayFlow();
        return success(flowList);
    }


    // =================== 新增 / 修改的部分 ===================

    /**
     * 查询当天的人脸识别事件（大屏列表用）
     *
     * 返回统一封装好的 VO，包含 PERSON/STRANGER、displayName 等
     */
    @Anonymous
    @GetMapping("/getTodayEvents")
    public AjaxResult getTodayEvents()
    {
        List<TodayFaceEventVO> list = faceRecognitionEventService.selectTodayEventsV1();
        return success(list);
    }

    /**
     * 根据事件ID获取“事件 + 人员身份详情”（大屏弹窗用）
     *
     * 统一结构，前端不用关心是正式人员还是陌生人
     */
    @GetMapping("/{id}/identityDetail")
    public AjaxResult getIdentityDetail(@PathVariable("id") Long id)
    {
        FaceEventIdentityDetailVO detail = faceRecognitionEventService.getIdentityDetail(id);
        return success(detail);
    }

}