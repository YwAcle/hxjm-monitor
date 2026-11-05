package edu.cqupt.hxjm.architecture;

import java.util.*;
import java.nio.file.*;
import java.time.OffsetDateTime;
import java.lang.reflect.Proxy;
import javax.servlet.http.HttpServletRequest;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import edu.cqupt.hxjm.algdeployment.business.security.*;
import edu.cqupt.hxjm.algdeployment.business.store.*;
import edu.cqupt.hxjm.algdeployment.business.service.*;
import edu.cqupt.hxjm.algdeployment.capability.service.*;
import edu.cqupt.hxjm.algdeployment.capability.api.GarbageController;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

/** Real DB + real public services/Controller + explicit simulated device. Entire fixture rolls back. */
public class GarbageFlowCheck {
    static String id(){return UUID.randomUUID().toString();}
    static void expect(boolean v,String message){if(!v){throw new AssertionError(message);}}
    public static void main(String[] args) throws Exception {
        if(!"hxjm_refactor".equals(System.getenv("POSTGRES_DATABASE"))||!"127.0.0.1".equals(System.getenv("POSTGRES_HOST"))){throw new IllegalStateException("Use isolated stage3 DB only");}
        DriverManagerDataSource ds=new DriverManagerDataSource("jdbc:postgresql://127.0.0.1:5432/hxjm_refactor",System.getenv("POSTGRES_USER"),System.getenv("POSTGRES_PASSWORD"));
        BusinessStore store=new BusinessStore(ds);
        try{
            store.transaction(jdbc->{
                String source=jdbc.queryForObject("SELECT id::text FROM public.camera ORDER BY id LIMIT 1",String.class);
                BusinessSecurityProperties security=new BusinessSecurityProperties();
                BusinessSecurityProperties.ServiceIdentity grant=new BusinessSecurityProperties.ServiceIdentity();grant.setToken("local-fixture-only");grant.setSourceIds(new LinkedHashSet<>(Arrays.asList(source)));
                grant.setOperations(new LinkedHashSet<>(Arrays.asList("tasks.submit","tasks.start","capabilities.register","instances.configure","result_types.register","results.register","cleanup.execute")));
                security.getServices().put("hxjm-pipeline",grant);BusinessAuthentication auth=new BusinessAuthentication(security,store);auth.afterPropertiesSet();
                BusinessActor actor=auth.serviceActor("hxjm-pipeline","tasks.submit");
                BusinessDataAccess data=new BusinessDataAccess(store,null);
                CapabilityExecutionProperties execution=new CapabilityExecutionProperties();execution.setEnabled(true);execution.setNamespace("stage4-test");
                CapabilityExecutionProperties.Operation op=new CapabilityExecutionProperties.Operation();op.setAdapter("m20_mock");op.setUrl("mock://local");op.setRequiredOperation("cleanup.execute");op.setCredentialRef("hxjm-pipeline");execution.getServices().put("robot-dog",Collections.singletonMap("cleanup",op));
                CapabilityPlatform platform=new CapabilityPlatform(store,execution,auth,data);
                CapabilityTaskService tasks=new CapabilityTaskService(store,data,new BusinessTaskInputs(data,null));
                try{java.lang.reflect.Field f=CapabilityTaskService.class.getDeclaredField("platform");f.setAccessible(true);f.set(tasks,platform);}catch(Exception e){throw new IllegalStateException(e);}
                try{
                    Map<String,Object> contract=parse(new String(Files.readAllBytes(Paths.get("contracts/capability-v1/garbage-cleanup.json")),java.nio.charset.StandardCharsets.UTF_8));
                    Map<String,Object> cap=map(contract.get("capability"));cap.put("request_id",id());tasks.capability(actor,cap);
                    Map<String,Object> type=map(contract.get("result_type"));type.put("request_id",id());tasks.resultType(actor,type);
                    Map<String,Object> instance=map(contract.get("instance"));map(instance.get("execution")).put("adapter","m20_mock");instance.putAll(values("request_id",id(),"instance_id",id(),"capability_code","garbage.cleanup","instance_key","stage4-test"));tasks.instance(actor,instance);
                    // Register a continuous detector through the same Capability registry.
                    Map<String,Object> detector=values("input_schema",values("type","object"),"parameters_schema",values("type","object"),"output_types",Arrays.asList("garbage.detection"));
                    tasks.capability(actor,values("request_id",id(),"capability_code","garbage.detection","display_name","垃圾检测","object_types",Arrays.asList("garbage"),"input_kinds",Arrays.asList("live_video"),"contract",detector));
                    String detectorInstance=id();tasks.instance(actor,values("request_id",id(),"instance_id",detectorInstance,"capability_code","garbage.detection","instance_key","garbage-test","implementation_code","garbage","implementation_version","1","source_ids",Arrays.asList(source),"service_ref","local://video-analysis"));
                    String session=id(),stream=jdbc.queryForObject("SELECT id::text FROM public.camera_stream WHERE camera_id=?::uuid LIMIT 1",String.class,source);
                    OffsetDateTime now=OffsetDateTime.now().minusSeconds(1);
                    jdbc.update("INSERT INTO public.stream_session(id,source_id,camera_stream_id,session_key,started_at,time_origin_at,time_basis,source_timezone,source_width,source_height,expires_at) VALUES(?::uuid,?::uuid,?::uuid,?,?,?,'ingest_clock','Asia/Shanghai',1920,1080,now()+interval '7 days')",session,source,stream,id(),now,now);
                    Map<String,Object> submitted=tasks.submit(actor,values("request_id",id(),"task_kind","garbage.detection","task_mode","continuous","capability_code","garbage.detection","instance_id",detectorInstance,"input",values("kind","live_video","source_id",source,"stream_session_id",session),"requested_outputs",Arrays.asList("garbage.detection")));
                    Map<String,Object> started=tasks.start(actor,values("request_id",id(),"task_id",submitted.get("task_id"),"expected_revision",submitted.get("revision")));
                    String result=id();Map<String,Object> target=values("category","瓶罐类","bbox",Arrays.asList(.1,.1,.2,.2),"confidence",.9);
                    Map<String,Object> body=values("request_id",id(),"task_id",started.get("task_id"),"run_id",started.get("run_id"),"result_set_id",id(),"set_key","garbage-test","capability_code","garbage.detection","result_type","garbage.detection","schema_version","1","source_id",source,"stream_session_id",session,"processed_at",iso(now.plusSeconds(1)),"results",Arrays.asList(values("result_id",result,"producer_result_key","frame-1","start_at",iso(now),"payload",values("has_target",true,"targets",Arrays.asList(target)))),"analysis_coverage",values("start_at",iso(now),"end_at",iso(now.plusSeconds(1)),"closed",true,"analyzed_frame_count",0,"frame_ids",Collections.emptyList(),"result_ids",Arrays.asList(result),"gaps",Collections.emptyList()));
                    body.put("tracking_context_id",id());body.put("tracking_context",values("context_key","garbage-runtime","started_at",iso(now),"reset_reason",null));
                    ResultRegistrationService results=new ResultRegistrationService(store);Map<String,Object> accepted=results.register(actor,body);expect(list(accepted.get("accepted_result_ids")).size()==1,"result must be accepted");
                    body.put("request_id",id());expect(list(results.register(actor,body).get("duplicate_result_ids")).size()==1,"retry must not duplicate event");
                    String nextResult=id();body.put("request_id",id());
                    body.put("results",Arrays.asList(values("result_id",nextResult,"producer_result_key","frame-2","start_at",iso(now),"payload",values("has_target",true,"targets",Arrays.asList(target)))));
                    map(body.get("analysis_coverage")).put("result_ids",Arrays.asList(result,nextResult));
                    expect(list(results.register(actor,body).get("accepted_result_ids")).size()==1,"next observation must persist");
                    String event=jdbc.queryForObject("SELECT id::text FROM public.business_event WHERE event_type='garbage.detected'",String.class);
                    expect(jdbc.queryForObject("SELECT count(*) FROM public.business_event WHERE event_type='garbage.detected'",Integer.class)==1,"dedup event");
                    GarbageBusinessService garbage=new GarbageBusinessService(store);CleanupProperties config=new CleanupProperties();config.setEnabled(true);config.getRoutes().put(source,"route1");
                    GarbageController controller=new GarbageController(auth,garbage,tasks,store,config,execution);
                    Map<String,Object> attributes=new HashMap<>();HttpServletRequest request=(HttpServletRequest)Proxy.newProxyInstance(GarbageFlowCheck.class.getClassLoader(),new Class[]{HttpServletRequest.class},(proxy,method,a)->{
                        if(method.getName().equals("getHeader")){return null;}if(method.getName().equals("getAttribute")){return attributes.get(a[0]);}if(method.getName().equals("setAttribute")){attributes.put(a[0].toString(),a[1]);return null;}return null;});
                    Map<String,Object> cleanup=controller.submit(request,json(values("request_id",id(),"event_id",event)));
                    expect(cleanup.get("task_id").equals(controller.submit(request,json(values("request_id",id(),"event_id",event))).get("task_id")),"double click must use same task");
                    platform.tick();platform.tick();
                    Map<String,Object> state=garbage.event(actor,event);Map<String,Object> task=map(state.get("cleanup"));
                    expect("succeeded".equals(task.get("state")),"simulated cleanup must complete through Capability");
                    expect(Boolean.TRUE.equals(map(task.get("device")).get("simulated")),"must identify simulation");
                    expect("open".equals(state.get("state")),"simulation must never mark event physically cleaned");
                    expect(jdbc.queryForObject("SELECT count(*) FROM public.task_output WHERE task_id=?::uuid",Integer.class,cleanup.get("task_id"))==1,"must persist task output");
                    expect(list(controller.events(request).get("items")).size()==1,"public page API must show event");
                    // A previous uncertain device run must block a different new run even after in-memory sessions disappear.
                    String endpoint="ws://robot.invalid:8765/control";
                    jdbc.update("UPDATE public.business_task SET execution_snapshot=jsonb_set(execution_snapshot,'{operation,url}',to_jsonb(?::text)) WHERE task_id=?::uuid",endpoint,cleanup.get("task_id"));
                    jdbc.update("UPDATE public.task_attempt SET state='failed',error_code='REMOTE_OUTCOME_UNKNOWN' WHERE task_id=?::uuid",cleanup.get("task_id"));
                    op.setAdapter("m20_route");op.setUrl(endpoint);
                    execution.setNamespace("uncertain-test");
                    String blockedInstance=id();
                    Map<String,Object> realInstance=map(contract.get("instance"));map(realInstance.get("execution")).put("adapter","m20_route");
                    realInstance.putAll(values("request_id",id(),"instance_id",blockedInstance,"capability_code","garbage.cleanup","instance_key","uncertain-test"));tasks.instance(actor,realInstance);
                    Map<String,Object> blocked=tasks.submit(actor,values("request_id",id(),"task_kind","garbage.cleanup","capability_code","garbage.cleanup","instance_id",blockedInstance,"task_mode","once","input",values("kind","capability_call","payload",values("event_id",event,"source_ids",Arrays.asList(source),"route","route1")),"requested_outputs",Arrays.asList("device.cleanup")));
                    platform.tick();platform.tick();
                    expect("DEVICE_RECONCILIATION_REQUIRED".equals(jdbc.queryForObject("SELECT error_code FROM public.business_task WHERE task_id=?::uuid",String.class,blocked.get("task_id"))),"persisted uncertain run must block dispatch without opening a socket");
                    config.getRoutes().clear();try{controller.submit(request,json(values("request_id",id(),"event_id",event)));throw new AssertionError("missing route should fail");}catch(edu.cqupt.hxjm.algdeployment.business.api.BusinessException expected){ }
                    System.out.println("GarbageFlowCheck passed: standard result -> deduplicated event -> manual Capability task -> simulated device -> persisted output -> page API; uncertain run blocks later dispatch; no hardware calls");
                }catch(java.io.IOException e){throw new IllegalStateException(e);}finally{platform.closeDevices();}
                throw new Rollback();
            });
        }catch(Rollback expected){System.out.println("Integration fixtures rolled back");}
    }
    private static class Rollback extends RuntimeException { }
}
