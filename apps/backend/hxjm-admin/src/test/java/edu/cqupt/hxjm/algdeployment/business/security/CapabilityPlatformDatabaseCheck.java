package edu.cqupt.hxjm.algdeployment.business.security;

import edu.cqupt.hxjm.algdeployment.capability.service.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import com.sun.net.httpserver.HttpServer;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import edu.cqupt.hxjm.algdeployment.business.service.*;
import edu.cqupt.hxjm.algdeployment.business.store.*;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

/** Explicit disposable database only. Protocol fixtures are not real-business acceptance. */
public class CapabilityPlatformDatabaseCheck {
    static void check(boolean value,String label){if(!value){throw new AssertionError(label);}}
    static void conflict(Runnable call){try{call.run();throw new AssertionError("Expected conflict");}catch(BusinessException expected){check(expected.getStatus()==409,"conflict status");}}
    public static void main(String[] args)throws Exception{
        String url=System.getenv("HXJM_TEST_JDBC_URL");
        if(url==null||!url.matches("jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/hxjm_capv1_test")){throw new IllegalArgumentException("Disposable capability DB required");}
        BusinessStore store=new BusinessStore(new DriverManagerDataSource(url,System.getenv("HXJM_TEST_DB_USER"),System.getenv("HXJM_TEST_DB_PASSWORD")));
        BusinessSecurityProperties security=new BusinessSecurityProperties();BusinessSecurityProperties.ServiceIdentity identity=new BusinessSecurityProperties.ServiceIdentity();
        identity.setToken("test-token");identity.setOperations(new HashSet<>(Arrays.asList("capabilities.register","capabilities.describe","result_types.register","instances.configure","tasks.submit","tasks.start","tasks.get","events.query")));security.getServices().put("test",identity);
        BusinessAuthentication auth=new BusinessAuthentication(security,store);BusinessActor actor=auth.serviceActor("test","tasks.submit");
        CapabilityExecutionProperties props=new CapabilityExecutionProperties();props.setNamespace("test-one");
        HttpServer server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/query",exchange->{byte[] response="{\"items\":[{\"id\":\"protocol-fixture\"}]}".getBytes(StandardCharsets.UTF_8);exchange.sendResponseHeaders(200,response.length);exchange.getResponseBody().write(response);exchange.close();});
        server.createContext("/redirect",exchange->{exchange.getResponseHeaders().set("Location","/query");exchange.sendResponseHeaders(302,-1);exchange.close();});
        server.createContext("/error",exchange->{exchange.sendResponseHeaders(503,-1);exchange.close();});
        server.createContext("/invalid",exchange->{byte[] bytes="invalid".getBytes(StandardCharsets.UTF_8);exchange.sendResponseHeaders(200,bytes.length);exchange.getResponseBody().write(bytes);exchange.close();});
        server.createContext("/slow",exchange->{try{Thread.sleep(500);}catch(InterruptedException stopped){Thread.currentThread().interrupt();}exchange.sendResponseHeaders(200,0);exchange.close();});
        server.start();
        try{
            CapabilityExecutionProperties.Operation op=new CapabilityExecutionProperties.Operation();op.setUrl("http://127.0.0.1:"+server.getAddress().getPort()+"/query");op.setRequiredOperation("events.query");op.setCredentialRef("test");props.getServices().put("business",Collections.singletonMap("events",op));
            CapabilityPlatform platform=new CapabilityPlatform(store,props,auth,null);CapabilityTaskService tasks=new CapabilityTaskService(store,null,new edu.cqupt.hxjm.algdeployment.business.service.BusinessTaskInputs(null,null));
            java.lang.reflect.Field field=CapabilityTaskService.class.getDeclaredField("platform");field.setAccessible(true);field.set(tasks,platform);
            Map<String,Object> fixture=parse(new String(Files.readAllBytes(Paths.get(System.getenv("HXJM_CONTRACTS"),"events.json")),StandardCharsets.UTF_8));
            Map<String,Object> capability=map(fixture.get("capability")),result=map(fixture.get("result_type")),instance=map(fixture.get("instance"));
            String code="test."+UUID.randomUUID().toString().replace("-","");String type=code+".page";
            capability.put("capability_code",code);map(capability.get("contract")).put("output_types",Arrays.asList(type));
            result.put("type_code",type);result.put("request_id",UUID.randomUUID().toString());tasks.resultType(actor,result);
            capability.put("request_id",UUID.randomUUID().toString());tasks.capability(actor,capability);
            String instanceId=UUID.randomUUID().toString();instance.put("instance_id",instanceId);instance.put("capability_code",code);instance.put("instance_key","test-one");instance.put("request_id",UUID.randomUUID().toString());map(instance.get("execution")).put("result_type",type);tasks.instance(actor,instance);
            Map<String,Object> submit=values("request_id",UUID.randomUUID().toString(),"business_key",UUID.randomUUID().toString(),"task_kind","capability.call","capability_code",code,"task_mode","once","input",values("kind","capability_call","payload",values("mode","latest")),"parameters",values(),"instance_id",instanceId,"requested_outputs",Arrays.asList(type));
            Map<String,Object> submitted=tasks.submit(actor,submit);String task=submitted.get("task_id").toString();
            check(Boolean.TRUE.equals(tasks.submit(actor,submit).get("duplicate")),"duplicate submit");
            conflict(()->tasks.start(actor,values("request_id",UUID.randomUUID().toString(),"task_id",task,"expected_revision",1)));
            ExecutorService pool=Executors.newFixedThreadPool(2);List<Future<Map<String,Object>>> claimed=pool.invokeAll(Arrays.asList(()->platform.claim(),()->new CapabilityPlatform(store,props,auth,null).claim()));pool.shutdown();
            Map<String,Object> run=null;int count=0;for(Future<Map<String,Object>> future:claimed){if(future.get()!=null){run=future.get();count++;}}check(count==1,"two claimers one run");
            Map<String,Object> renew=values("task_id",task,"run_id",run.get("run_id"),"execution_token",run.get("execution_token"));
            check(Boolean.TRUE.equals(platform.heartbeat(actor,renew).get("renewed")),"heartbeat token");
            platform.execute(run);check("succeeded".equals(tasks.get(actor,task,null).get("state")),"HTTP execute success");
            check(list(platform.outputs(actor,task,1,null).get("items")).size()==1,"persisted output");
            Map<String,Object> completion=values("task_id",task,"run_id",run.get("run_id"),"execution_token",run.get("execution_token"),"expected_revision",run.get("revision"),"outputs",Arrays.asList(values("result_type",type,"schema_version","1","producer_result_key","response","payload",values("items",Arrays.asList(values("id","protocol-fixture"))))));
            check(Boolean.TRUE.equals(platform.terminal(actor,completion,true).get("duplicate")),"duplicate completion");
            map(list(completion.get("outputs")).get(0)).put("payload",values("items",Collections.emptyList()));conflict(()->platform.terminal(actor,completion,true));
            for(String phase:Arrays.asList("not_sent","sending")){
                submit.put("request_id",UUID.randomUUID().toString());submit.put("business_key",UUID.randomUUID().toString());String recoveryTask=tasks.submit(actor,submit).get("task_id").toString();
                Map<String,Object> old=platform.claim();store.jdbc().update("UPDATE public.task_attempt SET send_phase=?,lease_until=now()-interval '1 second' WHERE run_id=?::uuid",phase,old.get("run_id"));platform.recover();
                String expected="sending".equals(phase)?"REMOTE_OUTCOME_UNKNOWN":"EXECUTION_INTERRUPTED_BEFORE_SEND";
                check(expected.equals(store.jdbc().queryForObject("SELECT error_code FROM public.business_task WHERE task_id=?::uuid",String.class,recoveryTask)),"lease recovery "+phase);
                Map<String,Object> late=new LinkedHashMap<>(completion);late.put("task_id",recoveryTask);late.put("run_id",old.get("run_id"));late.put("execution_token",old.get("execution_token"));late.put("expected_revision",old.get("revision"));conflict(()->platform.terminal(actor,late,true));
            }
            submit.put("request_id",UUID.randomUUID().toString());submit.put("business_key",UUID.randomUUID().toString());String foreign=tasks.submit(actor,submit).get("task_id").toString();
            props.setNamespace("test-other");check(platform.claim()==null,"namespace claim isolation");props.setNamespace("test-one");
            store.jdbc().update("UPDATE public.business_task SET dispatch_mode='runtime_managed' WHERE task_id=?::uuid",foreign);check(platform.claim()==null,"runtime worker isolation");
            for(Object c:BusinessValues.list(com.alibaba.fastjson2.JSON.parse(new String(Files.readAllBytes(Paths.get(System.getenv("HXJM_CONTRACTS"),"schema-cases.json")),StandardCharsets.UTF_8)))){
                Map<String,Object> sample=map(c);for(Object valid:list(sample.get("valid"))){BusinessSchemas.validate(map(sample.get("schema")),valid);}for(Object invalid:list(sample.get("invalid"))){try{BusinessSchemas.validate(map(sample.get("schema")),invalid);throw new AssertionError("invalid schema accepted: "+json(invalid));}catch(BusinessException expected){}}
            }
            for(String[] scenario:new String[][]{{"redirect","REMOTE_HTTP_ERROR"},{"error","REMOTE_HTTP_ERROR"},{"invalid","REMOTE_INVALID_RESPONSE"},{"query","REMOTE_RESPONSE_TOO_LARGE"},{"slow","REMOTE_OUTCOME_UNKNOWN"}}){
                op.setUrl("http://127.0.0.1:"+server.getAddress().getPort()+"/"+scenario[0]);op.setResponseTimeoutMs(100);op.setMaxResponseBytes("query".equals(scenario[0])?2:1048576);
                try{new CapabilityHttpAdapter().execute(platform.operation("business",map(instance.get("execution"))),values("payload",values("mode","latest")),values(),auth);throw new AssertionError("Expected adapter failure");}
                catch(CapabilityHttpAdapter.Failure expected){check(scenario[1].equals(expected.code),"adapter "+scenario[0]+" "+expected.code);}
            }
            System.out.println("CapabilityPlatformDatabaseCheck passed: schema cases, global input, dedup, fenced completion, digest conflict, concurrent claim, lease recovery, late results, namespace and runtime isolation");
        }finally{server.stop(0);}
    }
}
