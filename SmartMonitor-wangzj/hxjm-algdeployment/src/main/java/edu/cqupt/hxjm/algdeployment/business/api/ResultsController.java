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
import edu.cqupt.hxjm.algdeployment.business.service.ResultRegistrationService;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessValues;

@RestController
@RequestMapping("/api/v1/business/results")
@ConditionalOnProperty(prefix="hxjm.business",name="enabled",havingValue="true")
public class ResultsController {
    private final BusinessAuthentication authentication;
    private final ResultRegistrationService service;

    public ResultsController(BusinessAuthentication authentication, ResultRegistrationService service) {
        this.authentication=authentication; this.service=service;
    }

    @PostMapping("/register")
    public Map<String,Object> register(@RequestBody String raw, HttpServletRequest request) {
        BusinessActor actor=authentication.requireService(request,"results.register");
        Map<String,Object> body=BusinessValues.parse(raw);
        String trace=BusinessResponses.traceId(request,body.get("trace_id")==null?null:BusinessValues.text(body,"trace_id"));
        return BusinessResponses.success(service.register(actor,body),request,trace);
    }
}
