package edu.cqupt.hxjm.algdeployment.controller;

import edu.cqupt.hxjm.algdeployment.service.IMediaAssetService;
import edu.cqupt.hxjm.common.annotation.Anonymous;
import edu.cqupt.hxjm.common.core.controller.BaseController;
import edu.cqupt.hxjm.common.core.domain.AjaxResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/media-assets")
public class MediaAssetController extends BaseController {
    private final IMediaAssetService mediaAssetService;

    public MediaAssetController(IMediaAssetService mediaAssetService) {
        this.mediaAssetService = mediaAssetService;
    }

    @Anonymous
    @PostMapping
    public AjaxResult create(@RequestBody Map<String, Object> body) {
        String streamId = getString(body.get("stream_id"));
        String segmentPath = getString(body.get("segment_path"));
        Double durationS = getDouble(body.get("duration_s"));
        Map<String, Object> data = mediaAssetService.createMediaAsset(streamId, segmentPath, durationS);
        return AjaxResult.success("success", data);
    }

    @Anonymous
    @GetMapping
    public AjaxResult list() {
        List<Map<String, Object>> out = mediaAssetService.listMediaAssets();
        return AjaxResult.success(out);
    }

    private String getString(Object obj) {
        if (obj == null) {
            return null;
        }
        if (obj instanceof String) {
            return ((String) obj).trim();
        }
        return String.valueOf(obj).trim();
    }

    private Double getDouble(Object obj) {
        if (obj == null) {
            return null;
        }
        if (obj instanceof Number) {
            return ((Number) obj).doubleValue();
        }
        try {
            return Double.valueOf(String.valueOf(obj));
        } catch (NumberFormatException e) {
            return null;
        }
    }
}
