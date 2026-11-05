package edu.cqupt.hxjm.algdeployment.capability.api;

import java.util.*;
import javax.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import edu.cqupt.hxjm.algdeployment.business.api.*;
import edu.cqupt.hxjm.algdeployment.business.security.*;
import edu.cqupt.hxjm.algdeployment.business.service.GarbageBusinessService;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessStore;
import edu.cqupt.hxjm.algdeployment.capability.service.*;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

@RestController
@RequestMapping("/api/v1/business/garbage")
@ConditionalOnProperty(prefix="hxjm.business",name="enabled",havingValue="true")
public class GarbageController {
    private final BusinessAuthentication auth;
    private final GarbageBusinessService business;
    private final CapabilityTaskService tasks;
    private final BusinessStore store;
    private final CleanupProperties config;
    private final CapabilityExecutionProperties execution;
    public GarbageController(BusinessAuthentication auth,GarbageBusinessService business,CapabilityTaskService tasks,BusinessStore store,CleanupProperties config,CapabilityExecutionProperties execution){this.auth=auth;this.business=business;this.tasks=tasks;this.store=store;this.config=config;this.execution=execution;}
    @GetMapping("/events")
    public Map<String,Object> events(HttpServletRequest r){
        BusinessActor actor=auth.authenticate(r,"events.query");
        Map<String,Object> result=business.query(actor);result.put("cleanup_enabled",config.isEnabled()&&execution.isEnabled());
        Map<String,String> routes=new LinkedHashMap<>();for(String source:actor.getSourceIds()){if(config.getRoutes().containsKey(source)){routes.put(source,config.getRoutes().get(source));}}result.put("routes",routes);
        return BusinessResponses.success(result,r,null);
    }
    @PostMapping("/cleanup")
    public Map<String,Object> submit(HttpServletRequest r,@RequestBody String raw){
        BusinessActor user=auth.authenticate(r,"cleanup.submit");Map<String,Object> body=parse(raw);fields(body,"request_id","event_id");
        String event=uuid(body,"event_id"),request=text(body,"request_id",128);
        if(!config.isEnabled()||!execution.isEnabled()){throw BusinessException.conflict("清理未启用，检测和事件查询仍可使用");}
        Map<String,Object> observed=business.event(user,event);String source=observed.get("source_id").toString(),route=config.getRoutes().get(source);
        if(route==null){throw BusinessException.conflict("该来源尚未配置经确认的机器狗路线；图片框不是导航坐标");}
        edu.cqupt.hxjm.devices.M20RouteAdapter.command(request,route);
        BusinessActor actor=auth.serviceActor(config.getServiceId(),"tasks.submit");actor.requireSource(source);
        Map<String,Object> result=store.transaction(jdbc->{
            jdbc.queryForObject("SELECT pg_advisory_xact_lock(hashtextextended(?,0)) IS NULL",Boolean.class,"cleanup:"+event);
            Map<String,Object> current=business.event(user,event);
            if(current.get("cleanup")!=null){return map(current.get("cleanup"));}
            if(!"open".equals(current.get("state"))){throw BusinessException.conflict("事件已关闭");}
            return tasks.submit(actor,values("request_id",request,"task_kind","garbage.cleanup","business_key",event,"capability_code","garbage.cleanup","task_mode","once",
                "input",values("kind","capability_call","payload",values("event_id",event,"source_ids",Arrays.asList(source),"route",route)),"requested_outputs",Arrays.asList("device.cleanup"),"parameters",values()));
        });
        business.refreshCleanup(result.get("task_id").toString());
        return BusinessResponses.success(result,r,null);
    }
}
