package edu.cqupt.hxjm.algdeployment.business.api;

import java.nio.file.Path;
import java.util.Map;
import javax.servlet.http.HttpServletRequest;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessAuthentication;
import edu.cqupt.hxjm.algdeployment.business.security.PlaybackTickets;
import edu.cqupt.hxjm.algdeployment.business.service.RecordingService;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessValues;

@RestController
@RequestMapping("/api/v1/business")
@ConditionalOnProperty(prefix = "hxjm.business", name = "enabled", havingValue = "true")
public class RecordingController {
    private final BusinessAuthentication authentication;
    private final RecordingService recordings;
    private final PlaybackTickets tickets;
    public RecordingController(BusinessAuthentication authentication, RecordingService recordings, PlaybackTickets tickets) {
        this.authentication = authentication;
        this.recordings = recordings;
        this.tickets = tickets;
    }

    @PostMapping("/assets/{id}/playback-ticket")
    public Map<String, Object> ticket(@PathVariable String id, HttpServletRequest request) {
        BusinessActor actor = authentication.authenticate(request, "media.resolve");
        Map<String, Object> asset = recordings.asset(actor, id);
        recordings.content(actor, id);
        return BusinessResponses.success(tickets.issue(actor, asset.get("id").toString(),
                asset.get("expires_at") == null ? null : RecordingService.instant(asset.get("expires_at"))), request, null);
    }

    @PostMapping("/assets/register")
    public Map<String, Object> register(@RequestBody String raw, HttpServletRequest request) {
        BusinessActor actor = authentication.requireService(request, "assets.register");
        Map<String, Object> body = BusinessValues.parse(raw);
        return BusinessResponses.success(recordings.register(actor, body), request, (String) body.get("trace_id"));
    }

    @GetMapping("/assets/{id}/content")
    public ResponseEntity<Resource> content(@PathVariable String id, HttpServletRequest request) {
        String ticket = request.getParameter("ticket");
        BusinessActor actor = ticket == null ? authentication.authenticate(request, "media.resolve") : tickets.require(ticket, id);
        Path path = recordings.content(actor, id);
        Map<String, Object> asset = recordings.asset(actor, id);
        String contentType = String.valueOf(asset.get("content_type"));
        MediaType media;
        try { media = MediaType.parseMediaType(contentType); } catch (IllegalArgumentException invalid) { media = MediaType.APPLICATION_OCTET_STREAM; }
        ResponseEntity.BodyBuilder response = ResponseEntity.ok().contentType(media)
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .header("Referrer-Policy", "no-referrer")
                .header("X-Content-Type-Options", "nosniff");
        boolean safeImage = MediaType.IMAGE_JPEG.equals(media) || MediaType.IMAGE_PNG.equals(media);
        if ("algorithm_output".equals(asset.get("asset_type")) || (!"video".equalsIgnoreCase(media.getType()) && !safeImage)) {
            response.header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + asset.get("id") + ".bin\"");
        }
        return response.body(new FileSystemResource(path));
    }
}
