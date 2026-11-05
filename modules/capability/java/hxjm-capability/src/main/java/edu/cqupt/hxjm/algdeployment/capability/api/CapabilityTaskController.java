package edu.cqupt.hxjm.algdeployment.capability.api;

import java.util.Map;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessResponses;
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
import edu.cqupt.hxjm.algdeployment.capability.service.CapabilityTaskService;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessValues;

@RestController
@RequestMapping("/api/v1/business")
@ConditionalOnProperty(prefix = "hxjm.business", name = "enabled", havingValue = "true")
public class CapabilityTaskController {
    @org.springframework.beans.factory.annotation.Autowired
    private edu.cqupt.hxjm.algdeployment.capability.service.CapabilityPlatform platform;
    private final BusinessAuthentication authentication;
    private final CapabilityTaskService service;
    @org.springframework.beans.factory.annotation.Autowired
    private edu.cqupt.hxjm.algdeployment.capability.service.CapabilityExecutionProperties executionProperties;

    public CapabilityTaskController(BusinessAuthentication authentication, CapabilityTaskService service) {
        this.authentication = authentication;
        this.service = service;
    }

    @GetMapping("/execution/status")
    public Map<String,Object> executionStatus(HttpServletRequest request) {
        authentication.authenticate(request,"capabilities.describe");
        return BusinessResponses.success(BusinessValues.values("enabled",executionProperties.isEnabled()),request,null);
    }

    @GetMapping("/capabilities")
    public Map<String, Object> capabilities(HttpServletRequest request,
            @RequestParam(value="capability_code",required=false) String code) {
        authentication.authenticate(request,"capabilities.describe");
        return BusinessResponses.success(service.capabilities(code),request,null);
    }

    @PostMapping("/capabilities")
    public Map<String,Object> capability(HttpServletRequest request,@RequestBody String raw) {
        BusinessActor actor=authentication.requireService(request,"capabilities.register");
        Map<String,Object> body=body(request,raw);
        return BusinessResponses.success(service.capability(actor,body),request,null);
    }

    @PostMapping("/result-types")
    public Map<String,Object> resultType(HttpServletRequest request,@RequestBody String raw) {
        BusinessActor actor=authentication.requireService(request,"result_types.register");
        Map<String,Object> body=body(request,raw);
        return BusinessResponses.success(service.resultType(actor,body),request,null);
    }

    /**
     * Read a registered result contract.  Algorithm workers use this before
     * submitting a task so that a retry can distinguish an existing contract
     * from a conflicting registration.
     */
    @GetMapping("/result-types")
    public Map<String,Object> resultTypes(HttpServletRequest request,
            @RequestParam(value="type_code",required=false) String type,
            @RequestParam(value="schema_version",required=false) String version) {
        authentication.authenticate(request,"result_types.query");
        return BusinessResponses.success(service.resultTypes(type,version),request,null);
    }

    @PostMapping("/instances")
    public Map<String,Object> instance(HttpServletRequest request,@RequestBody String raw) {
        BusinessActor actor=authentication.requireService(request,"instances.configure");
        Map<String,Object> body=body(request,raw);
        return BusinessResponses.success(service.instance(actor,body),request,null);
    }

    /** Read the current configuration and revision of an algorithm instance. */
    @GetMapping("/instances")
    public Map<String,Object> instances(HttpServletRequest request,
            @RequestParam(value="instance_id",required=false) String id,
            @RequestParam(value="capability_code",required=false) String capability) {
        BusinessActor actor=authentication.authenticate(request,"instances.query");
        return BusinessResponses.success(service.instances(actor,id,capability),request,null);
    }

    @PostMapping("/tasks")
    public Map<String,Object> submit(HttpServletRequest request,@RequestBody String raw) {
        BusinessActor actor=authentication.authenticate(request,"tasks.submit");
        Map<String,Object> body=body(request,raw);
        return BusinessResponses.success(service.submit(actor,body),request,null);
    }

    @PostMapping("/tasks/start")
    public Map<String,Object> start(HttpServletRequest request,@RequestBody String raw) {
        BusinessActor actor=authentication.requireService(request,"tasks.start");
        Map<String,Object> body=body(request,raw);
        return BusinessResponses.success(service.start(actor,body),request,null);
    }

    @GetMapping("/tasks")
    public Map<String,Object> get(HttpServletRequest request,@RequestParam("task_id") String task,
            @RequestParam(value="run_id",required=false) String run) {
        return BusinessResponses.success(service.get(authentication.authenticate(request,"tasks.get"),task,run),request,null);
    }

    @PostMapping("/tasks/end")
    public Map<String,Object> endRuntime(HttpServletRequest request,@RequestBody String raw) {
        return BusinessResponses.success(service.endRuntime(authentication.requireService(request,"tasks.end"),body(request,raw)),request,null);
    }

    @PostMapping("/tasks/finish")
    public Map<String,Object> finish(HttpServletRequest request,@RequestBody String raw) {
        BusinessActor actor=authentication.requireService(request,"tasks.finish");
        return BusinessResponses.success(service.finish(actor,body(request,raw)),request,null);
    }

    @GetMapping("/capabilities/tools")
    public Map<String,Object> tools(HttpServletRequest request){
        return BusinessResponses.success(platform.catalog(authentication.authenticate(request,"capabilities.describe")),request,null);
    }
    @GetMapping("/tasks/outputs")
    public Map<String,Object> outputs(HttpServletRequest request,@RequestParam("task_id") String task,
            @RequestParam(value="limit",defaultValue="20") int limit,@RequestParam(value="after",required=false) String after){
        return BusinessResponses.success(platform.outputs(authentication.authenticate(request,"tasks.get"),task,limit,after),request,null);
    }
    @PostMapping("/tasks/heartbeat")
    public Map<String,Object> heartbeat(HttpServletRequest request,@RequestBody String raw){
        return BusinessResponses.success(platform.heartbeat(authentication.requireService(request,"tasks.heartbeat"),body(request,raw)),request,null);
    }
    @PostMapping("/tasks/complete")
    public Map<String,Object> complete(HttpServletRequest request,@RequestBody String raw){
        return BusinessResponses.success(platform.terminal(authentication.requireService(request,"tasks.complete"),body(request,raw),true),request,null);
    }
    @PostMapping("/tasks/fail")
    public Map<String,Object> fail(HttpServletRequest request,@RequestBody String raw){
        return BusinessResponses.success(platform.terminal(authentication.requireService(request,"tasks.fail"),body(request,raw),false),request,null);
    }

    private static Map<String,Object> body(HttpServletRequest request,String raw) {
        Map<String,Object> body=BusinessValues.parse(raw);
        BusinessResponses.traceId(request,body.containsKey("trace_id")?BusinessValues.text(body,"trace_id",128):null);
        return body;
    }
}
