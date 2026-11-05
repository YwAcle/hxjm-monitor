package edu.cqupt.hxjm.algdeployment.capability.api;

import java.util.*;
import java.net.*;
import java.io.*;
import javax.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import edu.cqupt.hxjm.algdeployment.business.api.*;
import edu.cqupt.hxjm.algdeployment.business.security.*;
import edu.cqupt.hxjm.algdeployment.business.service.ActivityBusinessService;
import edu.cqupt.hxjm.algdeployment.capability.service.BehaviorRuntimeProperties;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

/** Public coordination boundary; browser never receives model addresses or producer credentials. */
@RestController
@RequestMapping("/api/v1/business/behavior")
@ConditionalOnProperty(prefix="hxjm.business",name="enabled",havingValue="true")
public class BehaviorController {
    private final BusinessAuthentication auth; private final ActivityBusinessService business; private final BehaviorRuntimeProperties config;
    public BehaviorController(BusinessAuthentication auth,ActivityBusinessService business,BehaviorRuntimeProperties config){this.auth=auth;this.business=business;this.config=config;}
    @GetMapping("/status")
    public Map<String,Object> status(HttpServletRequest request){
        BusinessActor actor=auth.authenticate(request,"events.query");
        Map<String,Object> response=call("/status",null);
        Map<String,Object> cameras=map(response.get("cameras"));
        cameras.entrySet().removeIf(e->!actor.getSourceIds().contains(map(e.getValue()).get("source_id")));
        List<Object> pending=new ArrayList<>();for(Object value:list(response.getOrDefault("pending_events",Collections.emptyList()))){if(actor.getSourceIds().contains(map(value).get("source_id"))){pending.add(value);}}
        response.put("pending_events",pending);response.put("pending_reviews",pending.stream().filter(v->!Arrays.asList("blocked","incomplete").contains(map(v).get("state"))).count());response.put("cameras",cameras);response.put("camera_contexts",cameras.size());response.remove("recent_work");response.remove("last_error");return BusinessResponses.success(response,request,null);
    }
    @PostMapping("/reviews")
    public Map<String,Object> review(HttpServletRequest request,@RequestBody String raw){
        BusinessActor actor=auth.authenticate(request,"behavior.review");Map<String,Object> body=parse(raw);fields(body,"report_id");String id=uuid(body,"report_id");
        Map<String,Object> report=business.getReport(actor,id);
        if(!String.valueOf(report.get("report_type")).startsWith("joyai_anomaly_review")){throw BusinessException.invalid("不是行为复核报告");}
        Map<String,Object> response=call("/reviews/restart",values("report_id",id));
        // Only acknowledgement leaves this write endpoint; progress uses the scoped public status API.
        return BusinessResponses.success(values("accepted",true,"pending_reviews",response.get("pending_reviews")),request,null);
    }
    private Map<String,Object> call(String path,Map<String,Object> body){
        if(config.getUrl()==null||config.getToken()==null){if(body!=null){throw BusinessException.conflict("行为检测服务未配置");}return values("status","unavailable","cameras",values(),"pending_events",Collections.emptyList());}
        HttpURLConnection connection=null;
        try{
            URI base=URI.create(config.getUrl());if(!Arrays.asList("http","https").contains(base.getScheme())||base.getHost()==null||base.getUserInfo()!=null||base.getQuery()!=null||base.getFragment()!=null){throw BusinessException.invalid("行为服务配置无效");}
            connection=(HttpURLConnection)new URL(config.getUrl()+path).openConnection();connection.setInstanceFollowRedirects(false);connection.setConnectTimeout(2000);connection.setReadTimeout(10000);connection.setRequestProperty("X-JoyAI-Token",config.getToken());
            if(body!=null){connection.setRequestMethod("POST");connection.setDoOutput(true);connection.setRequestProperty("Content-Type","application/json");try(OutputStream out=connection.getOutputStream()){out.write(json(body).getBytes(java.nio.charset.StandardCharsets.UTF_8));}}
            int status=connection.getResponseCode();if(status!=200){throw BusinessException.conflict("行为服务未接受请求，请核对服务状态和原始证据");}
            ByteArrayOutputStream out=new ByteArrayOutputStream();try(InputStream in=connection.getInputStream()){byte[] buffer=new byte[8192];int n;while((n=in.read(buffer))!=-1){if(out.size()+n>1048576){throw BusinessException.invalid("行为状态响应过大");}out.write(buffer,0,n);}}
            return parse(new String(out.toByteArray(),java.nio.charset.StandardCharsets.UTF_8));
        }catch(IOException e){throw BusinessException.conflict("行为检测服务未连接，历史事件与报告仍可查询");}finally{if(connection!=null){connection.disconnect();}}
    }
}
