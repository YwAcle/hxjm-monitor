package edu.cqupt.hxjm.algdeployment.business.service;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.jdbc.core.JdbcTemplate;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.security.*;
import edu.cqupt.hxjm.algdeployment.business.store.*;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

/** Registry projection, fenced platform execution and generic task outputs. */
@Service
@EnableScheduling
@ConditionalOnProperty(prefix="hxjm.business",name="enabled",havingValue="true")
public class CapabilityPlatform {
    private static final Logger LOG=LoggerFactory.getLogger(CapabilityPlatform.class);
    private final String executorId=UUID.randomUUID().toString();
    private final BusinessStore store;
    private final CapabilityExecutionProperties config;
    private final BusinessAuthentication auth;
    private final BusinessDataAccess data;
    public CapabilityPlatform(BusinessStore store,CapabilityExecutionProperties config,BusinessAuthentication auth,BusinessDataAccess data){
        this.store=store;this.config=config;this.auth=auth;this.data=data;
    }
    public String namespace(){
        String value=config.getNamespace();
        if(value==null||!value.matches("[a-zA-Z0-9_.-]{1,100}")){throw BusinessException.invalid("配置 execution.namespace 后才能提交平台任务");}
        return value;
    }
    public Map<String,Object> operation(String service,Map<String,Object> execution){
        fields(execution,"adapter","operation","result_type","schema_version");
        if(!"http".equals(text(execution,"adapter",16))){throw BusinessException.invalid("仅支持http适配器");}
        Map<String,CapabilityExecutionProperties.Operation> operations=config.getServices().get(service);
        CapabilityExecutionProperties.Operation op=operations==null?null:operations.get(text(execution,"operation",64));
        if(op==null){throw BusinessException.invalid("服务或操作未在可信配置登记");}
        URI uri;
        try{uri=URI.create(op.getUrl());}catch(RuntimeException invalid){throw BusinessException.invalid("服务URL无效");}
        if(!Arrays.asList("http","https").contains(uri.getScheme())||uri.getHost()==null||uri.getUserInfo()!=null||uri.getFragment()!=null
            ||!"POST".equals(op.getMethod())||!Arrays.asList("payload","envelope").contains(op.getRequestMode())
            ||!Arrays.asList("business","json").contains(op.getResponseMode())||op.getRequiredOperation()==null
            ||op.getConnectTimeoutMs()<1||op.getResponseTimeoutMs()<1||op.getResponseTimeoutMs()>30000||op.getMaxResponseBytes()<1||op.getMaxResponseBytes()>10485760){
            throw BusinessException.invalid("可信HTTP操作配置无效");
        }
        return values("url",op.getUrl(),"method",op.getMethod(),"version",op.getVersion(),"credential_ref",op.getCredentialRef(),
            "required_operation",op.getRequiredOperation(),"request_mode",op.getRequestMode(),"response_mode",op.getResponseMode(),
            "connect_timeout_ms",op.getConnectTimeoutMs(),"response_timeout_ms",op.getResponseTimeoutMs(),"max_response_bytes",op.getMaxResponseBytes());
    }
    public void authorize(BusinessActor actor,Map<String,Object> operation){
        actor.requireOperation(text(operation,"required_operation",64));
        // V1 background execution supports the existing service identities; no user delegation is introduced.
        if(!actor.isService()){throw BusinessException.forbidden();}
        Object credential=operation.get("credential_ref");
        if(credential!=null&&!actor.getServiceId().equals(credential)){throw BusinessException.forbidden();}
    }
    public Map<String,Object> catalog(BusinessActor actor){
        List<Map<String,Object>> items=new ArrayList<>();
        for(Map<String,Object> row:store.jdbc().queryForList("SELECT d.capability_code,d.display_name,d.agent_json::text,d.contract_json::text,i.id::text,i.service_ref,i.execution_json::text,i.resource_scope::text FROM public.capability_definition d JOIN public.capability_instance i USING(capability_code) WHERE d.enabled AND i.enabled AND i.dispatch_mode='platform_managed' AND i.instance_key=? ORDER BY d.capability_code,i.id",namespace())){
            Map<String,Object> agent=parse(row.get("agent_json").toString());
            if(!Boolean.TRUE.equals(agent.get("enabled"))||!Boolean.TRUE.equals(agent.get("read_only"))){continue;}
            Map<String,Object> execution=parse(row.get("execution_json").toString());
            try{authorize(actor,operation(row.get("service_ref").toString(),execution));
                Map<String,Object> scope=parse(row.get("resource_scope").toString());
                for(Object source:list(scope.get("resource_ids"))){actor.requireSource(source.toString());}
            }catch(BusinessException denied){if(denied.getStatus()==403){continue;}throw denied;}
            Map<String,Object> contract=parse(row.get("contract_json").toString());
            Map<String,Object> input=map(contract.get("input_schema"));
            Map<String,Object> payload=map(map(input.get("properties")).get("payload"));
            items.add(values("capability_code",row.get("capability_code"),"instance_id",row.get("id"),"tool_name",required(agent,"tool_name"),
                "description",required(agent,"description"),"input_schema",payload,"output_types",contract.get("output_types"),"read_only",true));
        }
        return values("items",items);
    }
    public Map<String,Object> outputs(BusinessActor actor,String task,int limit,String after){
        task=uuid(task,"task_id");if(limit<1||limit>100){throw BusinessException.invalid("limit须为1..100");}
        Map<String,Object> row=store.jdbc().queryForMap("SELECT actor_key,expires_at>now() AS valid FROM public.business_task WHERE task_id=?::uuid",task);
        if(!actor.getActorKey().equals(row.get("actor_key"))){throw BusinessException.forbidden();}
        if(!Boolean.TRUE.equals(row.get("valid"))){throw BusinessException.expired("任务已到期");}
        List<Map<String,Object>> items=store.jdbc().queryForList("SELECT id::text,run_id::text,result_type,schema_version,payload_json::text,asset_id::text,producer_result_key FROM public.task_output WHERE task_id=?::uuid AND (?::uuid IS NULL OR id>?::uuid) ORDER BY id LIMIT ?",task,after==null?null:uuid(after,"after"),after,limit+1);
        boolean more=items.size()>limit;if(more){items.remove(items.size()-1);}
        for(Map<String,Object> item:items){item.put("payload",parseValue(item.remove("payload_json").toString()));}
        return values("items",items,"next_cursor",more?items.get(items.size()-1).get("id"):null);
    }
    public Map<String,Object> terminal(BusinessActor actor,Map<String,Object> body,boolean success){
        fields(body,"request_id","trace_id","task_id","run_id","expected_revision","execution_token","outputs","error_code");
        String task=uuid(body,"task_id"),run=uuid(body,"run_id"),token=uuid(body,"execution_token");
        long revision=integer(body,"expected_revision",1,Long.MAX_VALUE);
        return store.transaction(jdbc->{
            Map<String,Object> t=jdbc.queryForMap("SELECT *,expires_at>now() AS valid FROM public.business_task WHERE task_id=?::uuid FOR UPDATE",task);
            Map<String,Object> a=jdbc.queryForMap("SELECT *,lease_until>now() AS live FROM public.task_attempt WHERE task_id=?::uuid AND run_id=?::uuid FOR UPDATE",task,run);
            if(!actor.isService()||!actor.getActorKey().equals(a.get("lease_owner"))||!token.equals(String.valueOf(a.get("execution_token")))){throw BusinessException.forbidden();}
            if(!"platform_managed".equals(t.get("dispatch_mode"))||!namespace().equals(t.get("execution_namespace"))||!run.equals(String.valueOf(t.get("current_run_id")))){throw BusinessException.conflict("不是当前平台执行");}
            List<Object> incoming=success?list(required(body,"outputs")):Collections.emptyList();
            if(success&&incoming.isEmpty()){throw BusinessException.invalid("outputs不能为空");}
            if("succeeded".equals(t.get("state"))&&success){
                List<Map<String,Object>> old=jdbc.queryForList("SELECT producer_result_key,payload_digest FROM public.task_output WHERE run_id=?::uuid",run);
                if(old.size()!=incoming.size()){throw BusinessException.conflict("终态成果不能更改");}
                for(Object value:incoming){Map<String,Object> output=map(value);String digest=BusinessCanonical.digest(output);
                    if(old.stream().noneMatch(o->o.get("producer_result_key").equals(output.get("producer_result_key"))&&o.get("payload_digest").toString().trim().equals(digest))){throw BusinessException.conflict("成果摘要冲突");}}
                return values("task_id",task,"run_id",run,"state","succeeded","duplicate",true);
            }
            if("failed".equals(t.get("state"))&&!success&&Objects.equals(t.get("error_code"),body.get("error_code"))){return values("task_id",task,"state","failed","duplicate",true);}
            if(!"running".equals(t.get("state"))||!"running".equals(a.get("state"))||!Boolean.TRUE.equals(a.get("live"))||!Boolean.TRUE.equals(t.get("valid"))||((Number)t.get("revision")).longValue()!=revision){throw BusinessException.conflict("执行状态、revision或lease失效");}
            Map<String,Object> snapshot=parse(t.get("execution_snapshot").toString());
            Set<String> keys=new HashSet<>();
            for(Object value:incoming){
                Map<String,Object> output=map(value);fields(output,"result_type","schema_version","payload","asset_id","producer_result_key");
                String type=text(output,"result_type",64),version=text(output,"schema_version",32),key=text(output,"producer_result_key",128);
                if(!keys.add(key)){throw BusinessException.invalid("成果键重复");}
                if(!list(snapshot.get("requested_outputs")).contains(type)){throw BusinessException.invalid("未请求此成果类型");}
                Map<String,Object> contract=map(map(snapshot.get("output_contracts")).get(type+":"+version));
                Object payload=required(output,"payload");BusinessSchemas.validate(map(contract.get("json_schema")),payload);
                if(json(payload).getBytes(StandardCharsets.UTF_8).length>((Number)contract.get("max_inline_bytes")).intValue()){throw BusinessException.invalid("成果过大");}
                String asset=output.containsKey("asset_id")?uuid(output,"asset_id"):null;
                if(asset!=null){data.recordings().asset(auth.serviceActor(t.get("actor_key").toString().substring(8),"tasks.submit"),asset);}
                jdbc.update("INSERT INTO public.task_output(task_id,run_id,result_type,schema_version,payload_json,asset_id,producer_result_key,payload_digest) VALUES(?::uuid,?::uuid,?,?,?::jsonb,?::uuid,?,?)",task,run,type,version,json(payload),asset,key,BusinessCanonical.digest(output));
            }
            String state=success?"succeeded":"failed",code=success?null:text(body,"error_code",64);
            jdbc.update("UPDATE public.task_attempt SET state=?,error_code=?,finished_at=now(),lease_until=NULL,updated_at=now() WHERE run_id=?::uuid",state,code,run);
            jdbc.update("UPDATE public.business_task SET state=?,error_code=?,progress=?,revision=revision+1,updated_at=now() WHERE task_id=?::uuid",state,code,success?100:0,task);
            return values("task_id",task,"run_id",run,"state",state,"revision",revision+1,"duplicate",false);
        });
    }
    public Map<String,Object> heartbeat(BusinessActor actor,Map<String,Object> body){
        fields(body,"task_id","run_id","execution_token");
        int changed=store.jdbc().update("UPDATE public.task_attempt a SET lease_until=now()+interval '60 seconds',updated_at=now() FROM public.business_task t WHERE a.task_id=t.task_id AND a.run_id=t.current_run_id AND t.task_id=?::uuid AND a.run_id=?::uuid AND a.execution_token=?::uuid AND a.lease_owner=? AND a.state='running' AND t.state='running' AND t.execution_namespace=? AND t.dispatch_mode='platform_managed' AND a.lease_until>now() AND t.expires_at>now()",uuid(body,"task_id"),uuid(body,"run_id"),uuid(body,"execution_token"),actor.getActorKey(),namespace());
        if(changed!=1){throw BusinessException.conflict("当前执行令牌或lease失效");}
        return values("renewed",true);
    }
    @Scheduled(fixedDelayString="${hxjm.business.execution.poll-ms:500}")
    public void tick(){
        if(!config.isEnabled()){return;}
        try{recover();Map<String,Object> task=claim();if(task!=null){execute(task);}}
        catch(RuntimeException failed){LOG.error("Capability executor poll failed ({})",failed.getClass().getSimpleName());}
    }
    public Map<String,Object> claim(){
        return store.transaction(jdbc->{
            List<Map<String,Object>> pending=jdbc.queryForList("SELECT * FROM public.business_task WHERE dispatch_mode='platform_managed' AND execution_namespace=? AND state='pending' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1",namespace());
            if(pending.isEmpty()){return null;}Map<String,Object> task=pending.get(0);
            Map<String,Object> snapshot=parse(task.get("execution_snapshot").toString());
            try{
                BusinessActor owner=auth.serviceActor(task.get("actor_key").toString().substring(8),"tasks.submit");
                authorize(owner,map(snapshot.get("operation")));
                Map<String,Object> input=map(snapshot.get("input"));
                for(Object source:list(map(input.get("payload")).getOrDefault("source_ids",Collections.emptyList()))){owner.requireSource(source.toString());}
                if(jdbc.queryForList("SELECT 1 FROM public.capability_definition d JOIN public.capability_instance i USING(capability_code) WHERE d.capability_code=? AND d.enabled AND i.id=?::uuid AND i.enabled",task.get("capability_code"),snapshot.get("instance_id")).isEmpty()){throw BusinessException.forbidden();}
                if(!jdbc.queryForObject("SELECT expires_at>now() FROM public.business_task WHERE task_id=?",Boolean.class,task.get("task_id"))){throw BusinessException.expired("任务到期");}
            }catch(BusinessException denied){jdbc.update("UPDATE public.business_task SET state='failed',error_code='EXECUTION_NOT_AUTHORIZED',revision=revision+1,updated_at=now() WHERE task_id=?",task.get("task_id"));return null;}
            String run=UUID.randomUUID().toString(),token=UUID.randomUUID().toString();long generation=((Number)task.get("generation")).longValue()+1;
            jdbc.update("INSERT INTO public.task_attempt(run_id,task_id,generation,state,implementation_code,implementation_version,parameters_json,lease_owner,lease_until,started_at,expires_at,execution_token,executor_id) VALUES(?::uuid,?,?,'running',?,?,?::jsonb,?,now()+interval '60 seconds',now(),?,?::uuid,?)",run,task.get("task_id"),generation,snapshot.get("implementation_code"),snapshot.get("implementation_version"),json(snapshot),task.get("actor_key"),task.get("expires_at"),token,executorId);
            jdbc.update("UPDATE public.business_task SET current_run_id=?::uuid,generation=?,state='running',revision=revision+1,updated_at=now() WHERE task_id=?",run,generation,task.get("task_id"));
            task.put("run_id",run);task.put("execution_token",token);task.put("revision",((Number)task.get("revision")).longValue()+1);task.put("snapshot",snapshot);return task;
        });
    }
    public void execute(Map<String,Object> task){
        Map<String,Object> snapshot=map(task.get("snapshot"));
        BusinessActor actor=auth.serviceActor(task.get("actor_key").toString().substring(8),"tasks.submit");
        Map<String,Object> completion=values("task_id",task.get("task_id").toString(),"run_id",task.get("run_id"),"execution_token",task.get("execution_token"),"expected_revision",task.get("revision"));
        try{
            int marked=store.jdbc().update("UPDATE public.task_attempt SET send_phase='sending' WHERE run_id=?::uuid AND execution_token=?::uuid AND state='running' AND lease_until>now()",task.get("run_id"),task.get("execution_token"));
            if(marked!=1){return;}
            Object result=new CapabilityHttpAdapter().execute(map(snapshot.get("operation")),map(snapshot.get("input")),map(snapshot.get("parameters")),auth);
            Map<String,Object> execution=map(snapshot.get("execution"));
            completion.put("outputs",Arrays.asList(values("result_type",execution.get("result_type"),"schema_version",execution.get("schema_version"),"producer_result_key","response","payload",result)));
            terminal(actor,completion,true);
        }catch(RuntimeException failed){
            completion.remove("outputs");completion.put("error_code",failed instanceof CapabilityHttpAdapter.Failure?((CapabilityHttpAdapter.Failure)failed).code:"RESULT_VALIDATION_FAILED");
            terminal(actor,completion,false);
        }
    }
    public void recover(){
        store.transaction(jdbc->{
            for(Map<String,Object> row:jdbc.queryForList("SELECT t.task_id,a.run_id,a.send_phase FROM public.business_task t JOIN public.task_attempt a ON a.run_id=t.current_run_id WHERE t.dispatch_mode='platform_managed' AND t.execution_namespace=? AND t.state='running' AND (a.lease_until<=now() OR t.expires_at<=now()) FOR UPDATE OF t,a SKIP LOCKED",namespace())){
                String code="sending".equals(row.get("send_phase"))?"REMOTE_OUTCOME_UNKNOWN":"EXECUTION_INTERRUPTED_BEFORE_SEND";
                jdbc.update("UPDATE public.task_attempt SET state='failed',error_code=?,finished_at=now(),lease_until=NULL WHERE run_id=?",code,row.get("run_id"));
                jdbc.update("UPDATE public.business_task SET state='failed',error_code=?,revision=revision+1,updated_at=now() WHERE task_id=?",code,row.get("task_id"));
            }return null;
        });
    }
}
