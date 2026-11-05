package edu.cqupt.hxjm.algdeployment.business.api;

import java.util.Map;
import javax.servlet.http.HttpServletRequest;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessAuthentication;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import edu.cqupt.hxjm.algdeployment.business.service.TrackingLifecycleService;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessValues;

@RestController
@RequestMapping("/api/v1/business/tracking")
@ConditionalOnProperty(prefix="hxjm.business",name="enabled",havingValue="true")
public class TrackingLifecycleController {
    private final BusinessAuthentication authentication;
    private final TrackingLifecycleService service;
    public TrackingLifecycleController(BusinessAuthentication authentication,TrackingLifecycleService service){
        this.authentication=authentication;this.service=service;
    }
    @PostMapping("/close")
    public Map<String,Object> close(@RequestBody String raw,HttpServletRequest request){
        BusinessActor actor=authentication.requireService(request,"tracking.close");
        Map<String,Object> body=BusinessValues.parse(raw);
        String trace=BusinessResponses.traceId(request,body.get("trace_id")==null?null:BusinessValues.text(body,"trace_id"));
        return BusinessResponses.success(service.close(actor,body),request,trace);
    }
}
