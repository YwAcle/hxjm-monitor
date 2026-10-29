package edu.cqupt.hxjm.algdeployment.controller;

import edu.cqupt.hxjm.algdeployment.service.IAiTaskRunService;
import edu.cqupt.hxjm.common.annotation.Log;
import edu.cqupt.hxjm.common.annotation.Anonymous;
import edu.cqupt.hxjm.common.core.controller.BaseController;
import edu.cqupt.hxjm.common.core.domain.AjaxResult;
import edu.cqupt.hxjm.common.enums.BusinessType;
import edu.cqupt.hxjm.common.constant.HttpStatus;
import edu.cqupt.hxjm.common.exception.ServiceException;
// import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.servlet.http.HttpServletRequest;
import java.util.HashMap;
import java.util.Map;

@RestController
@RequestMapping("/algdeployment/ai/tasks")
public class AiTaskRunController extends BaseController {
    private final IAiTaskRunService aiTaskRunService;

    public AiTaskRunController(IAiTaskRunService aiTaskRunService) {
        this.aiTaskRunService = aiTaskRunService;
    }

    // @PreAuthorize("@ss.hasPermi('algdeployment:aiTaskRun:add')")
    @Log(title = "启动算法任务", businessType = BusinessType.OTHER)
    @Anonymous
    @PostMapping("/{task}/runs")
    public AjaxResult createRun(@PathVariable("task") String task,
                                @RequestBody Map<String, Object> body,
                                HttpServletRequest request) {
        Object cam = body.get("camera_id");
        if (!(cam instanceof Number)) {
            throw new ServiceException("camera_id 必填且为数字", HttpStatus.BAD_REQUEST);
        }
        int cameraId = ((Number) cam).intValue();
        if (cameraId <= 0) {
            throw new ServiceException("camera_id 不合法", HttpStatus.BAD_REQUEST);
        }
        String url = aiTaskRunService.startAndGetUrl(task, cameraId, request);
        Map<String, Object> data = new HashMap<>();
        data.put("task", task);
        data.put("camera_id", cameraId);
        data.put("url", url);
        return AjaxResult.success("success", data);
    }
}
