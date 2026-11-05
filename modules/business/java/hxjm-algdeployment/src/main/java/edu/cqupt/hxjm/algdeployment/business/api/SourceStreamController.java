package edu.cqupt.hxjm.algdeployment.business.api;

import java.util.List;
import java.util.Map;
import javax.servlet.http.HttpServletRequest;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessAuthentication;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import edu.cqupt.hxjm.algdeployment.business.service.SourceStreamService;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessValues;

@RestController
@RequestMapping("/api/v1/business")
@ConditionalOnProperty(prefix = "hxjm.business", name = "enabled", havingValue = "true")
public class SourceStreamController {
    private final BusinessAuthentication authentication;
    private final SourceStreamService service;

    public SourceStreamController(BusinessAuthentication authentication, SourceStreamService service) {
        this.authentication = authentication; this.service = service;
    }

    @GetMapping("/sources")
    public Map<String, Object> sources(HttpServletRequest request,
            @RequestParam(value="source_ids", required=false) List<String> sources,
            @RequestParam(value="cursor", required=false) String cursor,
            @RequestParam(value="page_size", defaultValue="50") int size) {
        return BusinessResponses.success(service.sources(authentication.authenticate(request,"sources.query"), sources, cursor, size), request, null);
    }

    @PostMapping("/sources")
    public Map<String, Object> register(HttpServletRequest request, @RequestBody String raw) {
        BusinessActor actor=authentication.requireService(request,"sources.register");
        Map<String, Object> body = BusinessValues.parse(raw);
        BusinessResponses.traceId(request, body.containsKey("trace_id") ? BusinessValues.text(body,"trace_id",128) : null);
        return BusinessResponses.success(service.register(actor, body), request, null);
    }

    @GetMapping("/streams")
    public Map<String, Object> streams(HttpServletRequest request,
            @RequestParam("source_id") String source,
            @RequestParam(value="cursor",required=false) String cursor,
            @RequestParam(value="page_size",defaultValue="50") int size) {
        return BusinessResponses.success(service.sessions(authentication.authenticate(request,"sources.query"), source, cursor, size),request,null);
    }

    @PostMapping("/streams/open")
    public Map<String, Object> open(HttpServletRequest request, @RequestBody String raw) {
        BusinessActor actor=authentication.requireService(request,"streams.open");
        Map<String, Object> body = BusinessValues.parse(raw);
        BusinessResponses.traceId(request, body.containsKey("trace_id") ? BusinessValues.text(body,"trace_id",128) : null);
        return BusinessResponses.success(service.open(actor,body),request,null);
    }

    @PostMapping("/streams/close")
    public Map<String, Object> close(HttpServletRequest request, @RequestBody String raw) {
        BusinessActor actor=authentication.requireService(request,"streams.close");
        Map<String, Object> body = BusinessValues.parse(raw);
        BusinessResponses.traceId(request,body.containsKey("trace_id") ? BusinessValues.text(body,"trace_id",128) : null);
        return BusinessResponses.success(service.close(actor,body),request,null);
    }
}
