package edu.cqupt.hxjm.algdeployment.business.api;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;
import javax.servlet.http.HttpServletRequest;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessAuthentication;
import edu.cqupt.hxjm.algdeployment.business.service.ImageAssetService;

@RestController
@RequestMapping("/api/v1/business")
@ConditionalOnProperty(prefix = "hxjm.business", name = "enabled", havingValue = "true")
public class ImageAssetController {
    private final BusinessAuthentication authentication;
    private final ImageAssetService images;
    public ImageAssetController(BusinessAuthentication authentication, ImageAssetService images) { this.authentication = authentication; this.images = images; }

    @PostMapping(value = "/assets/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, Object> upload(@RequestParam("file") MultipartFile file, @RequestParam Map<String, String> parameters, HttpServletRequest request) {
        edu.cqupt.hxjm.algdeployment.business.security.BusinessActor actor = authentication.authenticate(request, "assets.upload");
        if (file.getSize() > ImageAssetService.MAX_BYTES) { throw BusinessException.invalid("图片不得超过10MiB"); }
        Map<String, Object> body = new LinkedHashMap<>(parameters);
        try { return BusinessResponses.success(images.upload(actor, body, file.getBytes()), request, parameters.get("trace_id")); }
        catch (IOException failure) { throw BusinessException.invalid("上传图片无法读取"); }
    }
}
