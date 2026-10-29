package edu.cqupt.hxjm.algdeployment.business.api;

import java.util.Map;
import javax.servlet.http.HttpServletRequest;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.*;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessAuthentication;
import edu.cqupt.hxjm.algdeployment.business.service.HistoryService;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessValues;

@RestController
@RequestMapping("/api/v1/business")
@ConditionalOnProperty(prefix = "hxjm.business", name = "enabled", havingValue = "true")
public class HistoryController {
    private final BusinessAuthentication authentication;
    private final HistoryService history;
    public HistoryController(BusinessAuthentication authentication, HistoryService history) { this.authentication = authentication; this.history = history; }

    @PostMapping("/assets/query")
    public Map<String, Object> assets(@RequestBody String raw, HttpServletRequest request) {
        BusinessActor actor = authentication.authenticate(request, "assets.query");
        Map<String, Object> body = BusinessValues.parse(raw);
        return BusinessResponses.success(history.assets(actor, body), request, (String) body.get("trace_id"));
    }
    @PostMapping("/media/resolve")
    public Map<String, Object> resolve(@RequestBody String raw, HttpServletRequest request) {
        BusinessActor actor = authentication.authenticate(request, "media.resolve");
        Map<String, Object> body = BusinessValues.parse(raw);
        return BusinessResponses.success(history.resolve(actor, body), request, (String) body.get("trace_id"));
    }
    @PostMapping("/results/query")
    public Map<String, Object> results(@RequestBody String raw, HttpServletRequest request) {
        BusinessActor actor = authentication.authenticate(request, "results.query");
        Map<String, Object> body = BusinessValues.parse(raw);
        return BusinessResponses.success(history.results(actor, body), request, (String) body.get("trace_id"));
    }
}
