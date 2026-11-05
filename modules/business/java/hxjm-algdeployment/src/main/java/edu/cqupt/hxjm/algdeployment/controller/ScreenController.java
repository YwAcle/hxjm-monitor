package edu.cqupt.hxjm.algdeployment.controller;

import edu.cqupt.hxjm.algdeployment.service.IScreenService;
import edu.cqupt.hxjm.common.annotation.Anonymous;
import edu.cqupt.hxjm.common.core.controller.BaseController;
import edu.cqupt.hxjm.common.core.domain.AjaxResult;
import lombok.RequiredArgsConstructor;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.Map;

@RestController
@RequiredArgsConstructor
public class ScreenController extends BaseController {

    private final IScreenService screenService;

    @Anonymous
    @GetMapping("/api/device/stats")
    public AjaxResult getDeviceStats() {
        Long deviceCount = screenService.getDeviceCount();
        Map<String, Object> data = new HashMap<>();
        data.put("device_count", deviceCount == null ? 0L : deviceCount);
        return AjaxResult.success("success", data);
    }
}