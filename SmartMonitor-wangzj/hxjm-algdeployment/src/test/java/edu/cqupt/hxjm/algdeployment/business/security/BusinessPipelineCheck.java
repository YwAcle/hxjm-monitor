package edu.cqupt.hxjm.algdeployment.business.security;

import java.lang.reflect.Proxy;
import java.time.OffsetDateTime;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import javax.servlet.http.HttpServletRequest;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.service.CapabilityTaskService;
import edu.cqupt.hxjm.algdeployment.business.service.SourceStreamService;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessStore;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

/** Opt-in synthetic writes only to an explicitly named disposable stage-one database. */
public final class BusinessPipelineCheck {
    public static void main(String[] args) throws Exception {
        String url=System.getenv("HXJM_TEST_JDBC_URL");
        if(!"1".equals(System.getenv("HXJM_ISOLATED_TEST"))||url==null
                ||!url.matches("jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/hxjm_stage1_[a-z0-9_]+")) {
            throw new IllegalArgumentException("Explicit loopback hxjm_stage1_* test database and opt-in are required");
        }
        DriverManagerDataSource source=new DriverManagerDataSource(url,System.getenv("HXJM_TEST_DB_USER"),System.getenv("HXJM_TEST_DB_PASSWORD"));
        BusinessStore store=new BusinessStore(source);
        SourceStreamService streams=new SourceStreamService(store);
        CapabilityTaskService tasks=new CapabilityTaskService(store);
        String sourceId=UUID.randomUUID().toString();
        String session=UUID.randomUUID().toString();
        String suffix=UUID.randomUUID().toString();
        BusinessActor actor=actor(sourceId);
        Map<String,Object> registration=values("request_id","source-"+suffix,"source_id",sourceId,"camera_code","fixture-"+suffix,"display_name","synthetic source");
        streams.register(actor,registration);
        check(Boolean.TRUE.equals(streams.register(actor,registration).get("duplicate")),"source retry");
        Map<String,Object> changed=new java.util.LinkedHashMap<>(registration);changed.put("display_name","different");
        fails(409,()->streams.register(actor,changed));
        Map<String,Object> directory=streams.sources(actor,null,null,50);
        check(((List<?>)directory.get("items")).size()==1,"source scope");
        check(((Map<?,?>)((List<?>)directory.get("items")).get(0)).get("stream_id")==null,"do not invent stream mapping");
        OffsetDateTime now=OffsetDateTime.now().withNano(0);
        Map<String,Object> open=values("request_id","open-"+suffix,"source_id",sourceId,"stream_session_id",session,"session_key","ingest-"+suffix,
                "started_at",iso(now),"time_origin_at",iso(now),"time_basis","ingest_clock","source_timezone","Asia/Shanghai","source_width",1920,"source_height",1080);
        fails(400,()->streams.open(actor,open));
        store.jdbc().update("INSERT INTO public.camera_stream(id,camera_id,stream_name,task_type) VALUES (?::uuid,?::uuid,?,'track')",
                UUID.randomUUID().toString(),sourceId,"live/fixture-"+suffix);
        ExecutorService executor=Executors.newFixedThreadPool(2);
        try {
            Callable<Map<String,Object>> work=()->streams.open(actor,open);
            List<Future<Map<String,Object>>> responses=executor.invokeAll(Arrays.asList(work,work));
            boolean first=Boolean.TRUE.equals(responses.get(0).get().get("duplicate"));
            boolean second=Boolean.TRUE.equals(responses.get(1).get().get("duplicate"));
            check(first!=second,"one concurrent request executes, one replays");
        } finally {executor.shutdownNow();}
        check(store.jdbc().queryForObject("SELECT count(*) FROM public.stream_session WHERE id=?::uuid",Long.class,session)==1,"single persisted session");
        String capability="fixture_"+suffix.replace("-","");
        String output="fixture.result_"+suffix.replace("-","");
        tasks.resultType(actor,values("request_id","type-"+suffix,"type_code",output,"schema_version","1","json_schema",values("type","object")));
        tasks.capability(actor,values("request_id","cap-"+suffix,"capability_code",capability,"display_name","fixture capability","object_types",Collections.singletonList("person"),"input_kinds",Collections.singletonList("live_video"),
                "contract",values("input_schema",values("type","object"),"parameters_schema",values("type","object","additionalProperties",false),"output_types",Collections.singletonList(output))));
        String instance=UUID.randomUUID().toString();
        tasks.instance(actor,values("request_id","instance-"+suffix,"instance_id",instance,"capability_code",capability,"instance_key","one","implementation_code","fixture","implementation_version","1","source_ids",Collections.singletonList(sourceId),"service_ref","fixture-adapter"));
        Map<String,Object> submission=values("request_id","task-"+suffix,"task_kind","tracking","business_key","fixture-"+suffix,"capability_code",capability,"task_mode","continuous",
                "input",values("kind","live_video","source_id",sourceId,"stream_session_id",session),"requested_outputs",Collections.singletonList(output),"instance_id",instance);
        Map<String,Object> task=tasks.submit(actor,submission);
        String taskId=(String)task.get("task_id");
        check("pending".equals(task.get("state"))&&task.get("run_id")==null,"submit is not execution");
        Map<String,Object> start=values("request_id","start-"+suffix,"task_id",taskId,"expected_revision",1);
        Map<String,Object> running=tasks.start(actor,start);
        check("running".equals(running.get("state")),"execution started");
        check(Boolean.TRUE.equals(tasks.start(actor,start).get("duplicate")),"retry precedes revision check");
        Map<String,Object> execution=map(tasks.get(actor,taskId,(String)running.get("run_id")).get("execution"));
        check(instance.equals(execution.get("instance_id")),"fixed instance snapshot");
        check(actor.getActorKey().equals(store.jdbc().queryForObject("SELECT lease_owner FROM public.task_attempt WHERE run_id=?::uuid",String.class,running.get("run_id"))),"execution bound to actor");
        Map<String,Object> close=values("request_id","close-"+suffix,"stream_session_id",session,"expected_state","open","state","closed","occurred_at",iso(now.plusSeconds(10)),"ended_at",iso(now.plusSeconds(10)));
        streams.close(actor,close);
        check(Boolean.TRUE.equals(streams.close(actor,close).get("duplicate")),"close retry");
        check(Boolean.TRUE.equals(tasks.start(actor,start).get("duplicate")),"confirmed start remains replayable after stream closes");
        check(Boolean.TRUE.equals(streams.open(actor,open).get("duplicate")),"confirmed open remains replayable after close");
        String rollback="rollback-"+suffix;
        fails(409,()->store.write(actor,"sources.register",values("request_id",rollback),now.plusDays(1),jdbc->{
            store.event(jdbc,"fixture.rollback","stream_session",session,999,Collections.emptyMap(),now.plusDays(1));
            throw BusinessException.conflict("fixture rollback");
        }));
        check(store.jdbc().queryForObject("SELECT count(*) FROM public.request_deduplication WHERE request_id=?",Long.class,rollback)==0,"request and work rollback together");
        check(store.jdbc().queryForObject("SELECT count(*) FROM public.outbox_event WHERE aggregate_id=?::uuid AND aggregate_revision=999",Long.class,session)==0,"outbox rolled back");
        store.jdbc().update("UPDATE public.request_deduplication SET expires_at=now()-interval '1 second' WHERE actor_key=? AND operation='sources.register' AND request_id=?",actor.getActorKey(),registration.get("request_id"));
        fails(410,()->streams.register(actor,registration));
        System.out.println("BusinessPipelineCheck passed: source/session/task, concurrent dedup, transaction, snapshots, expiration");
    }

    private static BusinessActor actor(String source) {
        BusinessSecurityProperties properties=new BusinessSecurityProperties();
        BusinessSecurityProperties.ServiceIdentity identity=new BusinessSecurityProperties.ServiceIdentity();identity.setToken("fixture-only");
        identity.setOperations(new LinkedHashSet<>(Arrays.asList("sources.register","sources.query","streams.open","streams.close","capabilities.register","result_types.register","instances.configure","tasks.submit","tasks.start","tasks.get")));
        identity.setSourceIds(Collections.singleton(source));properties.getServices().put("fixture",identity);
        BusinessAuthentication authentication=new BusinessAuthentication(properties);authentication.afterPropertiesSet();
        HttpServletRequest request=(HttpServletRequest)Proxy.newProxyInstance(BusinessPipelineCheck.class.getClassLoader(),new Class<?>[]{HttpServletRequest.class},(proxy,method,args)->{
            if("getHeader".equals(method.getName())){return BusinessAuthentication.SERVICE_ID_HEADER.equals(args[0])?"fixture":"fixture-only";}throw new AssertionError(method.getName());});
        return authentication.requireService(request,"sources.register");
    }
    private static void fails(int status,Runnable work){try{work.run();throw new AssertionError("Expected "+status);}catch(BusinessException exception){check(exception.getStatus()==status,"unexpected status "+exception.getStatus());}}
    private static void check(boolean condition,String message){if(!condition){throw new AssertionError(message);}}
}
