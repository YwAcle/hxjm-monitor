package edu.cqupt.hxjm.algdeployment.capability.service;

import java.sql.Timestamp;
import edu.cqupt.hxjm.algdeployment.business.service.*;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessCanonical;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessSchemas;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessStore;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

@Service
@ConditionalOnProperty(prefix = "hxjm.business", name = "enabled", havingValue = "true")
public class CapabilityTaskService {
    private final BusinessStore store;
    @Autowired(required=false) private CapabilityPlatform platform;
    private final BusinessDataAccess businessData;
    private final BusinessTaskInputs taskInputs;

    @Autowired
    public CapabilityTaskService(BusinessStore store,BusinessDataAccess businessData,BusinessTaskInputs taskInputs) {
        this.store=store;this.businessData=businessData;this.taskInputs=taskInputs;
    }

    public Map<String, Object> capabilities(String code) {
        List<Map<String, Object>> items = store.jdbc().queryForList("SELECT capability_code,display_name,object_types,input_kinds,contract_json::text,agent_json::text,enabled,revision "
                + "FROM public.capability_definition" + (code == null ? "" : " WHERE capability_code=?") + " ORDER BY capability_code", code == null ? new Object[]{} : new Object[]{code});
        for (Map<String, Object> item : items) {
            item.put("contract", parse(item.remove("contract_json").toString()));
            item.put("agent", parse(item.remove("agent_json").toString()));
            item.put("object_types", array(item.get("object_types")));
            item.put("input_kinds", array(item.get("input_kinds")));
        }
        return values("items", items);
    }

    public Map<String, Object> capability(BusinessActor actor, Map<String, Object> body) {
        fields(body,"request_id","trace_id","capability_code","display_name","object_types","input_kinds","contract","agent");
        String code = text(body,"capability_code",64);
        String name = text(body,"display_name",128);
        List<String> objects = strings(required(body,"object_types"),128);
        List<String> kinds = strings(required(body,"input_kinds"),64);
        Map<String,Object> contract = map(required(body,"contract"));
        fields(contract,"input_schema","parameters_schema","output_types");
        BusinessSchemas.check(map(required(contract,"input_schema")));
        BusinessSchemas.check(map(required(contract,"parameters_schema")));
        strings(required(contract,"output_types"),64);
        Map<String,Object> agent=body.containsKey("agent")?map(body.get("agent")):new LinkedHashMap<>();
        fields(agent,"enabled","read_only","tool_name","description","context_inputs");
        if(!agent.isEmpty()){
            if(!(agent.get("enabled") instanceof Boolean)||!Boolean.TRUE.equals(agent.get("read_only"))||!text(agent,"tool_name",64).matches("[a-zA-Z][a-zA-Z0-9_]{0,63}")){throw BusinessException.invalid("Agent仅允许只读工具，名称须为标识符");}
            text(agent,"description",2048);
            if(!kinds.equals(Collections.singletonList("capability_call"))){throw BusinessException.invalid("Agent能力须为capability_call");}
            Map<String,Object> inputSchema=map(contract.get("input_schema"));
            Map<String,Object> payloadSchema=map(required(map(required(inputSchema,"properties")),"payload"));
            BusinessSchemas.check(payloadSchema);
            if(agent.containsKey("context_inputs")){
                Map<String,Object> bindings=map(agent.get("context_inputs"));
                Map<String,Object> properties=map(required(payloadSchema,"properties"));
                for(Map.Entry<String,Object> binding:bindings.entrySet()){
                    if(!"image_base64".equals(binding.getValue())||!"string".equals(map(required(properties,binding.getKey())).get("type"))){
                        throw BusinessException.invalid("context_inputs须绑定字符串参数到image_base64");
                    }
                }
            }

        }
        return store.write(actor,"capabilities.register",body,OffsetDateTime.now().plusDays(7),jdbc -> {
            if (!jdbc.queryForList("SELECT capability_code FROM public.capability_definition WHERE capability_code=?",code).isEmpty()) {
                throw BusinessException.conflict("能力已存在，本接口不隐式修改已发布契约");
            }
            jdbc.update("INSERT INTO public.capability_definition(capability_code,display_name,object_types,input_kinds,contract_json,agent_json) VALUES (?,?,?::text[],?::text[],?::jsonb,?::jsonb)",
                    code,name,pgArray(objects),pgArray(kinds),json(contract),json(agent));
            return values("capability_code",code,"revision",1,"enabled",true);
        });
    }

    public Map<String, Object> resultType(BusinessActor actor, Map<String, Object> body) {
        fields(body,"request_id","trace_id","type_code","schema_version","json_schema","max_inline_bytes");
        String type = text(body,"type_code",64);
        String version = text(body,"schema_version",32);
        Map<String,Object> schema = map(required(body,"json_schema"));
        BusinessSchemas.check(schema);
        int maximum = body.containsKey("max_inline_bytes") ? (int) integer(body,"max_inline_bytes",1,Integer.MAX_VALUE) : 1048576;
        return store.write(actor,"result_types.register",body,OffsetDateTime.now().plusDays(7),jdbc -> {
            if (!jdbc.queryForList("SELECT type_code FROM public.result_type WHERE type_code=? AND schema_version=?",type,version).isEmpty()) {
                throw BusinessException.conflict("成果类型版本已存在");
            }
            jdbc.update("INSERT INTO public.result_type(type_code,schema_version,json_schema,max_inline_bytes) VALUES (?,?,?::jsonb,?)",type,version,json(schema),maximum);
            return values("type_code",type,"schema_version",version,"enabled",true);
        });
    }

    public Map<String, Object> resultTypes(String type, String version) {
        if (type != null && (type.trim().isEmpty() || type.length() > 64)) {
            throw BusinessException.invalid("type_code无效");
        }
        if (version != null && (version.trim().isEmpty() || version.length() > 32)) {
            throw BusinessException.invalid("schema_version无效");
        }
        StringBuilder sql = new StringBuilder("SELECT type_code,schema_version,json_schema::text,max_inline_bytes,enabled,created_at FROM public.result_type WHERE 1=1");
        List<Object> args = new ArrayList<>();
        if (type != null) { sql.append(" AND type_code=?"); args.add(type); }
        if (version != null) { sql.append(" AND schema_version=?"); args.add(version); }
        sql.append(" ORDER BY type_code,schema_version");
        List<Map<String,Object>> items = store.jdbc().queryForList(sql.toString(), args.toArray());
        for (Map<String,Object> item : items) {
            Object schema = item.remove("json_schema");
            item.put("json_schema", schema == null ? Collections.emptyMap() : parse(schema.toString()));
            item.put("created_at", iso(timestamp(item.get("created_at"))));
        }
        return values("items",items);
    }

    public Map<String, Object> instance(BusinessActor actor, Map<String, Object> body) {
        fields(body,"request_id","trace_id","instance_id","capability_code","instance_key","implementation_code","implementation_version","source_ids","service_ref","enabled","expected_revision","resource_scope","dispatch_mode","execution");
        String id = uuid(body,"instance_id");
        String capability = text(body,"capability_code",64);
        String key = text(body,"instance_key",128);
        String implementation = text(body,"implementation_code",64);
        String version = text(body,"implementation_version",128);
        String service = text(body,"service_ref",256);
        List<String> sources = body.containsKey("source_ids")?uuids(body.get("source_ids")):new ArrayList<>();
        Map<String,Object> scope=body.containsKey("resource_scope")?map(body.get("resource_scope")):values("scope_type","camera","resource_ids",sources);
        fields(scope,"scope_type","resource_ids");
        String scopeType=text(scope,"scope_type",16);List<String> resources=uuids(required(scope,"resource_ids"));
        if("global".equals(scopeType)){
            if(!sources.isEmpty()||!resources.isEmpty()){throw BusinessException.invalid("global范围不得声明来源");}
        }else if("camera".equals(scopeType)){
            if(resources.isEmpty()||!new LinkedHashSet<>(resources).equals(new LinkedHashSet<>(sources))){throw BusinessException.invalid("摄像头范围与source_ids须一致且非空");}
        }else{throw BusinessException.invalid("V1范围支持global或camera");}
        String dispatch=body.containsKey("dispatch_mode")?text(body,"dispatch_mode",32):"runtime_managed";
        if(!Arrays.asList("runtime_managed","platform_managed").contains(dispatch)){throw BusinessException.invalid("dispatch_mode无效");}
        Map<String,Object> execution=body.containsKey("execution")?map(body.get("execution")):new LinkedHashMap<>();
        if("platform_managed".equals(dispatch)){platform.operation(service,execution);if(!key.equals(platform.namespace())){throw BusinessException.invalid("平台实例instance_key须等于执行namespace");}}
        else if(!execution.isEmpty()){throw BusinessException.invalid("runtime实例不接受HTTP执行配置");}
        for (String source : sources) { actor.requireSource(source); }
        if (body.containsKey("enabled") && !(body.get("enabled") instanceof Boolean)) { throw BusinessException.invalid("enabled须为布尔值"); }
        boolean enabled = !body.containsKey("enabled") || Boolean.TRUE.equals(body.get("enabled"));
        Long expected = body.containsKey("expected_revision") ? integer(body,"expected_revision",1,Long.MAX_VALUE) : null;
        return store.write(actor,"instances.configure",body,OffsetDateTime.now().plusDays(7),jdbc -> {
            if (jdbc.queryForList("SELECT capability_code FROM public.capability_definition WHERE capability_code=? AND enabled",capability).isEmpty()) { throw BusinessException.notFound("能力不存在或已停用"); }
            for (String source : sources) {
                if (jdbc.queryForList("SELECT id FROM public.camera WHERE id=?::uuid",source).isEmpty()) { throw BusinessException.notFound("实例来源不存在"); }
            }
            List<Map<String,Object>> rows = jdbc.queryForList("SELECT revision,source_ids FROM public.capability_instance WHERE id=?::uuid FOR UPDATE",id);
            long revision = 1;
            if (rows.isEmpty()) {
                if (UUID.fromString(id).version()!=4) { throw BusinessException.invalid("新实例标识须为UUIDv4"); }
                if (expected != null) { throw BusinessException.conflict("新实例不接受expected_revision"); }
                jdbc.update("INSERT INTO public.capability_instance(id,capability_code,instance_key,implementation_code,implementation_version,source_ids,service_ref,enabled,resource_scope,dispatch_mode,execution_json) VALUES (?::uuid,?,?,?,?,?::uuid[],?,?,?::jsonb,?,?::jsonb)",
                        id,capability,key,implementation,version,pgArray(sources),service,enabled,json(scope),dispatch,json(execution));
            } else {
                for (String source : array(rows.get(0).get("source_ids"))) { actor.requireSource(source); }
                revision = ((Number) rows.get(0).get("revision")).longValue();
                if (expected == null || expected != revision) { throw BusinessException.conflict("实例修订号已改变"); }
                revision++;
                jdbc.update("UPDATE public.capability_instance SET capability_code=?,instance_key=?,implementation_code=?,implementation_version=?,source_ids=?::uuid[],service_ref=?,enabled=?,resource_scope=?::jsonb,dispatch_mode=?,execution_json=?::jsonb,revision=?,updated_at=now() WHERE id=?::uuid",
                        capability,key,implementation,version,pgArray(sources),service,enabled,json(scope),dispatch,json(execution),revision,id);
            }
            return values("instance_id",id,"revision",revision,"enabled",enabled);
        });
    }

    public Map<String, Object> instances(BusinessActor actor, String id, String capability) {
        if (id != null) { id = uuid(id,"instance_id"); }
        if (capability != null && (capability.trim().isEmpty() || capability.length() > 64)) {
            throw BusinessException.invalid("capability_code无效");
        }
        StringBuilder sql = new StringBuilder("SELECT id::text,capability_code,instance_key,implementation_code,implementation_version,source_ids,service_ref,resource_scope::text,dispatch_mode,execution_json::text,enabled,revision,created_at,updated_at FROM public.capability_instance WHERE 1=1");
        List<Object> args = new ArrayList<>();
        if (id != null) { sql.append(" AND id=?::uuid"); args.add(id); }
        if (capability != null) { sql.append(" AND capability_code=?"); args.add(capability); }
        sql.append(" ORDER BY capability_code,instance_key,id");
        List<Map<String,Object>> items = store.jdbc().queryForList(sql.toString(), args.toArray());
        for (Map<String,Object> item : items) {
            List<String> sources = array(item.get("source_ids"));
            for (String source : sources) { actor.requireSource(source); }
            item.put("source_ids",sources);
            item.put("resource_scope",parse(item.get("resource_scope").toString()));
            item.put("execution",parse(item.remove("execution_json").toString()));
            item.put("created_at",iso(timestamp(item.get("created_at"))));
            item.put("updated_at",iso(timestamp(item.get("updated_at"))));
            item.put("revision",((Number)item.get("revision")).longValue());
        }
        return values("items",items);
    }

    public Map<String, Object> submit(BusinessActor actor, Map<String, Object> body) {
        fields(body,"request_id","trace_id","task_kind","business_key","capability_code","task_mode","input","requested_outputs","parameters","instance_id","expires_at");
        String kind = text(body,"task_kind",64);
        String business = body.containsKey("business_key") ? text(body,"business_key",256) : null;
        String capability = text(body,"capability_code",64);
        String mode = text(body,"task_mode",16);
        if (!Arrays.asList("once","continuous").contains(mode)) { throw BusinessException.invalid("task_mode无效"); }
        Map<String,Object> input = map(required(body,"input"));
        List<String> outputs = strings(required(body,"requested_outputs"),64);
        Map<String,Object> parameters = body.containsKey("parameters") ? map(body.get("parameters")) : new LinkedHashMap<>();
        String instance = body.containsKey("instance_id") ? uuid(body,"instance_id") : null;
        BusinessTaskInputs.Scope reference = resolveInput(store.jdbc(),actor,input,mode,false);
        OffsetDateTime expiry = reference.expires;
        if (body.containsKey("expires_at")) {
            OffsetDateTime requested = time(body,"expires_at");
            if (requested.isAfter(expiry)) { throw BusinessException.invalid("任务期限不能延长输入期限"); }
            expiry = requested;
        }
        Map<String,Object> snapshot = values("input",input,"requested_outputs",outputs,"parameters",parameters,"instance_id",instance);
        Map<String,Object> identity = values("task_kind",kind,"capability_code",capability,"task_mode",mode,"snapshot",snapshot);
        String digest = BusinessCanonical.digest(identity);
        final OffsetDateTime expires = expiry;
        return store.write(actor,"tasks.submit",body,expires,jdbc -> {
            resolveInput(jdbc,actor,input,mode,true);
            Map<String,Object> definition = definition(jdbc,capability);
            Map<String,Object> contract = parse(definition.get("contract_json").toString());
            if (!array(definition.get("input_kinds")).contains(text(input,"kind",64))) { throw BusinessException.invalid("该能力不支持此输入类型"); }
            BusinessSchemas.validate(map(required(contract,"input_schema")),input);
            BusinessSchemas.validate(map(required(contract,"parameters_schema")),parameters);
            if (!strings(required(contract,"output_types"),64).containsAll(outputs)) { throw BusinessException.invalid("请求输出不属于该能力契约"); }
            for (String output : outputs) {
                if (jdbc.queryForList("SELECT type_code FROM public.result_type WHERE type_code=? AND enabled",output).isEmpty()) { throw BusinessException.notFound("成果类型尚未启用"); }
            }
            Map<String,Object> selected=selectInstance(jdbc,capability,instance,reference.sources);
            String dispatch=selected.get("dispatch_mode").toString();
            Map<String,Object> executionSnapshot=values("instance_id",selected.get("id").toString(),"instance_revision",selected.get("revision"),
                "capability_revision",definition.get("revision"),"implementation_code",selected.get("implementation_code"),"implementation_version",selected.get("implementation_version"),
                "service_ref",selected.get("service_ref"),"input",input,"parameters",parameters,"requested_outputs",outputs);
            Map<String,Object> outputContracts=new LinkedHashMap<>();
            for(String type:outputs){for(Map<String,Object> result:jdbc.queryForList("SELECT schema_version,json_schema::text,max_inline_bytes FROM public.result_type WHERE type_code=? AND enabled",type)){
                outputContracts.put(type+":"+result.get("schema_version"),values("json_schema",parse(result.get("json_schema").toString()),"max_inline_bytes",result.get("max_inline_bytes")));
            }}
            executionSnapshot.put("output_contracts",outputContracts);
            String namespace="runtime";
            if("platform_managed".equals(dispatch)){
                if(!"capability_call".equals(input.get("kind"))||!"once".equals(mode)){throw BusinessException.invalid("HTTP能力须使用once capability_call");}
                if(!array(selected.get("source_ids")).isEmpty()&&reference.sources.isEmpty()){throw BusinessException.invalid("摄像头范围HTTP实例须明确payload.source_ids");}
                Map<String,Object> execution=parse(selected.get("execution_json").toString());
                Map<String,Object> operation=platform.operation(selected.get("service_ref").toString(),execution);platform.authorize(actor,operation);
                executionSnapshot.put("execution",execution);executionSnapshot.put("operation",operation);namespace=platform.namespace();
                if(!outputContracts.containsKey(execution.get("result_type")+":"+execution.get("schema_version"))){throw BusinessException.invalid("HTTP输出类型或版本未登记");}
                executionSnapshot.put("output_contracts",outputContracts);
            }
            if (business != null) {
                jdbc.queryForObject("SELECT pg_advisory_xact_lock(hashtextextended(?,0)) IS NULL",Boolean.class,"task:" + namespace + ":" + kind + ":" + business);
                List<Map<String,Object>> old = jdbc.queryForList("SELECT task_id::text,actor_key,input_digest,expires_at>now() AS valid FROM public.business_task WHERE task_kind=? AND business_key=? AND execution_namespace=? FOR UPDATE",kind,business,namespace);
                if (!old.isEmpty()) {
                    Map<String,Object> row = old.get(0);
                    if (!actor.getActorKey().equals(row.get("actor_key"))) { throw BusinessException.forbidden(); }
                    if (!Boolean.TRUE.equals(row.get("valid"))) { throw BusinessException.expired("原业务任务已到期"); }
                    if (!digest.equals(row.get("input_digest"))) { throw BusinessException.conflict("业务键对应不同输入"); }
                    Map<String,Object> response = summary(jdbc,(String) row.get("task_id")); response.put("duplicate",true); return response;
                }
            }
            String task = UUID.randomUUID().toString();
            jdbc.update("INSERT INTO public.business_task(task_id,task_kind,business_key,task_mode,actor_key,owner_user_id,capability_code,input_json,input_digest,expires_at,execution_snapshot,dispatch_mode,execution_namespace) VALUES (?::uuid,?,?,?,?,?,?,?::jsonb,?,?,?::jsonb,?,?)",
                    task,kind,business,mode,actor.getActorKey(),actor.getUserId(),capability,json(snapshot),digest,expires,json(executionSnapshot),dispatch,namespace);
            Map<String,Object> response = summary(jdbc,task);
            store.event(jdbc,"tasks.submitted","business_task",task,1,response,expires);
            return response;
        });
    }

    public Map<String, Object> start(BusinessActor actor, Map<String, Object> body) {
        fields(body,"request_id","trace_id","task_id","expected_revision","instance_id");
        String task = uuid(body,"task_id");
        long expected = integer(body,"expected_revision",1,Long.MAX_VALUE);
        String requestedInstance = body.containsKey("instance_id") ? uuid(body,"instance_id") : null;
        Map<String,Object> prior = owned(actor,task);
        OffsetDateTime expires = timestamp(prior.get("expires_at"));
        return store.write(actor,"tasks.start",body,expires,jdbc -> {
            Map<String,Object> row = jdbc.queryForMap("SELECT * FROM public.business_task WHERE task_id=?::uuid FOR UPDATE",task);
            if (!actor.getActorKey().equals(row.get("actor_key"))) { throw BusinessException.forbidden(); }
            if ("platform_managed".equals(row.get("dispatch_mode"))) { throw BusinessException.conflict("平台任务不得由Worker启动"); }
            if (!expires.isAfter(OffsetDateTime.now())) { throw BusinessException.expired("任务已到期"); }
            if (((Number) row.get("revision")).longValue()!=expected || !"pending".equals(row.get("state"))) { throw BusinessException.conflict("任务状态或修订号已改变"); }
            Map<String,Object> snapshot = parse(row.get("input_json").toString());
            Map<String,Object> input = map(snapshot.get("input"));
            BusinessTaskInputs.Scope reference = resolveInput(jdbc,actor,input,row.get("task_mode").toString(),true);
            String bound = snapshot.get("instance_id") == null ? null : uuid(snapshot,"instance_id");
            if (bound != null && requestedInstance != null && !bound.equals(requestedInstance)) { throw BusinessException.conflict("不能更换任务已指定的实例"); }
            Map<String,Object> instance;
            if(row.get("execution_snapshot")!=null){
                Map<String,Object> fixed=parse(row.get("execution_snapshot").toString());
                if(requestedInstance!=null&&!requestedInstance.equals(fixed.get("instance_id"))){throw BusinessException.conflict("不能更换快照实例");}
                definition(jdbc,row.get("capability_code").toString());
                if(jdbc.queryForList("SELECT id FROM public.capability_instance WHERE id=?::uuid AND enabled",fixed.get("instance_id")).isEmpty()){throw BusinessException.conflict("实例已停用");}
                instance=values("id",fixed.get("instance_id"),"revision",fixed.get("instance_revision"),"service_ref",fixed.get("service_ref"),"implementation_code",fixed.get("implementation_code"),"implementation_version",fixed.get("implementation_version"));
            }else{instance=selectInstance(jdbc,row.get("capability_code").toString(),requestedInstance==null?bound:requestedInstance,reference.sources);}
            String run = UUID.randomUUID().toString();
            long generation = ((Number) row.get("generation")).longValue()+1;
            Map<String,Object> attempt = values("instance_id",instance.get("id").toString(),"instance_revision",instance.get("revision"),
                    "service_ref",instance.get("service_ref"),"implementation_code",instance.get("implementation_code"),
                    "implementation_version",instance.get("implementation_version"),"parameters",snapshot.get("parameters"),
                    "requested_outputs",snapshot.get("requested_outputs"),"input",input);
            jdbc.update("INSERT INTO public.task_attempt(run_id,task_id,generation,state,implementation_code,implementation_version,parameters_json,lease_owner,lease_until,started_at,expires_at) "
                            + "VALUES (?::uuid,?::uuid,?,'running',?,?,?::jsonb,?,now()+interval '1 minute',now(),?)",
                    run,task,generation,instance.get("implementation_code"),instance.get("implementation_version"),json(attempt),actor.getActorKey(),expires);
            jdbc.update("UPDATE public.business_task SET current_run_id=?::uuid,generation=?,state='running',revision=revision+1,updated_at=now() WHERE task_id=?::uuid",run,generation,task);
            Map<String,Object> response = summary(jdbc,task);
            store.event(jdbc,"tasks.started","business_task",task,expected+1,response,expires);
            return response;
        });
    }

    /** Runtime producers finish already registered results; platform tasks retain their execution-token API. */
    public Map<String,Object> endRuntime(BusinessActor actor,Map<String,Object> body) {
        fields(body,"request_id","trace_id","task_id","run_id","expected_revision","state","result_ids","outputs","error_code");
        if(!actor.isService()){throw BusinessException.forbidden();}
        String task=uuid(body,"task_id"),run=uuid(body,"run_id"),state=text(body,"state",16);
        if(!Arrays.asList("succeeded","failed","cancelled").contains(state)){throw BusinessException.invalid("运行时终态无效");}
        List<String> results=uuids(body.getOrDefault("result_ids",Collections.emptyList()));
        List<Object> inline=body.containsKey("outputs")?list(body.get("outputs")):Collections.emptyList();
        if(!"succeeded".equals(state)&&!inline.isEmpty()){throw BusinessException.invalid("失败或取消不能提交成功成果");}
        String error="failed".equals(state)?text(body,"error_code",64):null;
        long expected=integer(body,"expected_revision",1,Long.MAX_VALUE);
        Map<String,Object> prior=owned(actor,task);OffsetDateTime expires=timestamp(prior.get("expires_at"));
        return store.write(actor,"tasks.end",body,expires,jdbc->{
            Map<String,Object> row=jdbc.queryForMap("SELECT * FROM public.business_task WHERE task_id=?::uuid FOR UPDATE",task);
            if(!actor.getActorKey().equals(row.get("actor_key"))){throw BusinessException.forbidden();}
            if(!"runtime_managed".equals(row.get("dispatch_mode"))){throw BusinessException.conflict("此入口只支持Runtime托管任务");}
            if(((Number)row.get("revision")).longValue()!=expected||!"running".equals(row.get("state"))||!run.equals(String.valueOf(row.get("current_run_id")))){throw BusinessException.conflict("任务状态、当前执行或修订号已改变");}
            if(!expires.isAfter(OffsetDateTime.now())){throw BusinessException.expired("任务到期");}
            List<String> outputs=strings(required(parse(row.get("input_json").toString()),"requested_outputs"),64);
            if("succeeded".equals(state)&&"once".equals(row.get("task_mode"))&&results.isEmpty()&&inline.isEmpty()){throw BusinessException.invalid("一次性成功任务须引用或提交成果");}
            for(String id:results){
                List<Map<String,Object>> refs=jdbc.queryForList("SELECT r.result_type FROM public.algorithm_result r JOIN public.result_set s ON s.id=r.result_set_id WHERE r.id=?::uuid AND s.run_id=?::uuid AND r.expires_at>now()",id,run);
                if(refs.isEmpty()||!outputs.contains(refs.get(0).get("result_type"))){throw BusinessException.invalid("成果不属于本次执行或输出契约");}
            }
            Map<String,Object> snapshot=parse(row.get("execution_snapshot").toString());
            Set<String> keys=new LinkedHashSet<>();
            for(Object value:inline){
                Map<String,Object> output=map(value);fields(output,"result_type","schema_version","payload","producer_result_key");
                String type=text(output,"result_type",64),version=text(output,"schema_version",32),key=text(output,"producer_result_key",128);
                if(!outputs.contains(type)||!keys.add(key)){throw BusinessException.invalid("未请求的输出类型或重复成果键");}
                Map<String,Object> contracts=map(required(snapshot,"output_contracts"));
                Map<String,Object> contract=map(required(contracts,type+":"+version));
                Object payload=required(output,"payload");BusinessSchemas.validate(map(contract.get("json_schema")),payload);
                if(json(payload).getBytes(java.nio.charset.StandardCharsets.UTF_8).length>((Number)contract.get("max_inline_bytes")).intValue()){throw BusinessException.invalid("成果过大");}
                jdbc.update("INSERT INTO public.task_output(task_id,run_id,result_type,schema_version,payload_json,producer_result_key,payload_digest) VALUES(?::uuid,?::uuid,?,?,?::jsonb,?,?)",task,run,type,version,json(payload),key,BusinessCanonical.digest(output));
            }
            int changed=jdbc.update("UPDATE public.task_attempt SET state=?,error_code=?,finished_at=now(),lease_until=NULL,updated_at=now() WHERE run_id=?::uuid AND task_id=?::uuid AND lease_owner=? AND state='running'",state,error,run,task,actor.getActorKey());
            if(changed!=1){throw BusinessException.conflict("执行身份或状态无效");}
            jdbc.update("UPDATE public.business_task SET state=?,error_code=?,progress=CASE WHEN ?='succeeded' THEN 100 ELSE progress END,revision=revision+1,updated_at=now() WHERE task_id=?::uuid",state,error,state,task);
            Map<String,Object> response=summary(jdbc,task);store.event(jdbc,"tasks."+state,"business_task",task,expected+1,response,expires);return response;
        });
    }

    public Map<String,Object> finish(BusinessActor actor,Map<String,Object> body) {
        fields(body,"request_id","trace_id","task_id","run_id","expected_revision","feature_ids");
        if(!actor.isService()){throw BusinessException.forbidden();}
        String task=uuid(body,"task_id"),run=uuid(body,"run_id");
        long expected=integer(body,"expected_revision",1,Long.MAX_VALUE);
        List<String> featureIds=uuids(required(body,"feature_ids"));
        if(featureIds.isEmpty()||featureIds.size()!=list(body.get("feature_ids")).size()){throw BusinessException.invalid("feature_ids须为非空且不重复的特征标识数组");}
        Map<String,Object> prior=owned(actor,task);
        OffsetDateTime expires=timestamp(prior.get("expires_at"));
        return store.write(actor,"tasks.finish",body,expires,jdbc->{
            Map<String,Object> row=jdbc.queryForMap("SELECT * FROM public.business_task WHERE task_id=?::uuid FOR UPDATE",task);
            if(!actor.getActorKey().equals(row.get("actor_key"))){throw BusinessException.forbidden();}
            if(((Number)row.get("revision")).longValue()!=expected||!"running".equals(row.get("state"))||!run.equals(String.valueOf(row.get("current_run_id")))){throw BusinessException.conflict("任务状态、当前执行或修订号已改变");}
            if(!"once".equals(row.get("task_mode"))){throw BusinessException.invalid("仅一次性特征任务可使用此完成入口");}
            Map<String,Object> snapshot=parse(row.get("input_json").toString());
            if(!strings(required(snapshot,"requested_outputs"),64).contains("feature.embedding")){throw BusinessException.invalid("任务未请求特征输出");}
            Map<String,Object> attempt=jdbc.queryForMap("SELECT * FROM public.task_attempt WHERE run_id=?::uuid AND task_id=?::uuid FOR UPDATE",run,task);
            if(!actor.getActorKey().equals(attempt.get("lease_owner"))){throw BusinessException.forbidden();}
            if(!"running".equals(attempt.get("state"))){throw BusinessException.conflict("执行已经结束");}
            if(!timestamp(attempt.get("expires_at")).isAfter(OffsetDateTime.now())){throw BusinessException.expired("执行已到期");}
            if(businessData==null){throw new IllegalStateException("Feature data access required");}
            List<Map<String,Object>> refs=new ArrayList<>();
            for(String featureId:featureIds){
                Map<String,Object> feature=businessData.feature(jdbc,actor,featureId);
                if(!run.equals(String.valueOf(feature.get("run_id")))){throw BusinessException.conflict("特征不属于本次执行");}
                refs.add(values("kind","feature","id",featureId));
            }
            jdbc.update("UPDATE public.task_attempt SET state='succeeded',finished_at=now(),lease_until=NULL,updated_at=now() WHERE run_id=?::uuid",run);
            jdbc.update("UPDATE public.business_task SET state='succeeded',progress=100,revision=revision+1,updated_at=now() WHERE task_id=?::uuid",task);
            Map<String,Object> response=summary(jdbc,task);response.put("progress",100);response.put("output_refs",refs);
            store.event(jdbc,"tasks.succeeded","business_task",task,expected+1,response,expires);
            return response;
        });
    }

    public Map<String,Object> get(BusinessActor actor,String task,String run) {
        task=uuid(task,"task_id");
        Map<String,Object> row=owned(actor,task);
        Map<String,Object> response=summary(store.jdbc(),task);
        response.put("progress",row.get("progress"));
        response.put("failure",row.get("error_code")==null?null:values("code",row.get("error_code"),"message","任务处理失败","retryable",false));
        List<Map<String,Object>> sets=store.jdbc().queryForList("SELECT rs.id::text AS id FROM public.result_set rs WHERE rs.run_id=?::uuid AND rs.expires_at>now() ORDER BY rs.id",response.get("run_id"));
        List<Map<String,Object>> refs=new ArrayList<>();for(Map<String,Object> set:sets){refs.add(values("kind","result_set","id",set.get("id")));}response.put("output_refs",refs);
        if(businessData!=null&&response.get("run_id")!=null){
            for(Map<String,Object> feature:store.jdbc().queryForList("SELECT id::text FROM public.feature WHERE run_id=?::uuid AND state='ready' AND (expires_at IS NULL OR expires_at>now()) ORDER BY id",response.get("run_id"))){
                try{businessData.feature(store.jdbc(),actor,feature.get("id").toString());refs.add(values("kind","feature","id",feature.get("id")));}
                catch(BusinessException unavailable){if(unavailable.getStatus()!=404&&unavailable.getStatus()!=410){throw unavailable;}}
            }
        }
        response.put("outputs",platform==null?Collections.emptyList():platform.outputs(actor,task,20,null).get("items"));
        response.put("execution",null);
        if(run!=null){
            run=uuid(run,"run_id");
            List<Map<String,Object>> attempts=store.jdbc().queryForList("SELECT run_id::text,lease_owner,parameters_json::text,generation,implementation_code,implementation_version FROM public.task_attempt WHERE task_id=?::uuid AND run_id=?::uuid",task,run);
            if(attempts.isEmpty()){throw BusinessException.notFound("执行不存在");}
            Map<String,Object> attempt=attempts.get(0);
            if(!actor.isService()||!actor.getActorKey().equals(attempt.get("lease_owner"))){throw BusinessException.forbidden();}
            Map<String,Object> execution=parse(attempt.get("parameters_json").toString());
            execution.put("run_id",run);execution.put("generation",attempt.get("generation"));
            execution.remove("service_ref");response.put("execution",execution);
        }
        List<Map<String,Object>> ranges=store.jdbc().queryForList("SELECT c.source_id::text,c.stage,c.start_at,c.end_at,c.status,c.reason_code FROM public.processing_coverage c "
                + "JOIN public.task_attempt a ON a.run_id=c.run_id WHERE a.task_id=?::uuid AND c.expires_at>now() ORDER BY c.start_at,c.id",task);
        List<Map<String,Object>> completed=new ArrayList<>(),gaps=new ArrayList<>();
        for(Map<String,Object> range:ranges){
            Map<String,Object> item=values("source_id",range.get("source_id"),"stage",range.get("stage"),"start_at",iso(timestamp(range.get("start_at"))),"end_at",iso(timestamp(range.get("end_at"))));
            if("complete".equals(range.get("status"))){completed.add(item);}else{item.put("reason_code",range.get("reason_code")==null?"PROCESSING_INCOMPLETE":range.get("reason_code"));gaps.add(item);}
        }
        response.put("coverage",values("schema_version","1","completed",completed,"gaps",gaps));
        return response;
    }

    private Map<String,Object> owned(BusinessActor actor,String task) {
        List<Map<String,Object>> rows=store.jdbc().queryForList("SELECT *,input_json::text AS input_json FROM public.business_task WHERE task_id=?::uuid",task);
        if(rows.isEmpty()){throw BusinessException.notFound("任务不存在");}
        Map<String,Object> row=rows.get(0);
        if(!actor.getActorKey().equals(row.get("actor_key")) && (actor.getUserId()==null||!actor.getUserId().equals(row.get("owner_user_id")))){throw BusinessException.forbidden();}
        if(!timestamp(row.get("expires_at")).isAfter(OffsetDateTime.now())){throw BusinessException.expired("任务已到期");}
        Map<String,Object> snapshot=parse(row.get("input_json").toString());
        resolveInput(store.jdbc(),actor,map(snapshot.get("input")),row.get("task_mode").toString(),false);
        return row;
    }

    private static Map<String,Object> summary(JdbcTemplate jdbc,String task) {
        Map<String,Object> row=jdbc.queryForMap("SELECT task_id::text,current_run_id::text AS run_id,state,task_mode,generation,revision,expires_at FROM public.business_task WHERE task_id=?::uuid",task);
        row.put("expires_at",iso(timestamp(row.get("expires_at"))));return row;
    }

    private static Map<String,Object> definition(JdbcTemplate jdbc,String code){
        List<Map<String,Object>> rows=jdbc.queryForList("SELECT revision,input_kinds,contract_json::text FROM public.capability_definition WHERE capability_code=? AND enabled",code);
        if(rows.isEmpty()){throw BusinessException.notFound("能力不存在或已停用");}return rows.get(0);
    }

    private Map<String,Object> selectInstance(JdbcTemplate jdbc,String capability,String id,Set<String> sources){
        List<Map<String,Object>> rows=jdbc.queryForList("SELECT * FROM public.capability_instance WHERE capability_code=? AND enabled"+(id==null?"":" AND id=?::uuid")+" ORDER BY id",id==null?new Object[]{capability}:new Object[]{capability,id});
        List<Map<String,Object>> eligible=new ArrayList<>();
        for(Map<String,Object> row:rows){if("platform_managed".equals(row.get("dispatch_mode"))&&!row.get("instance_key").equals(platform.namespace())){continue;}if("global".equals(parse(row.get("resource_scope").toString()).get("scope_type"))||array(row.get("source_ids")).containsAll(sources)){eligible.add(row);}}
        if(eligible.isEmpty()){throw BusinessException.notFound("没有适用于输入来源的启用实例");}
        if(eligible.size()>1){throw BusinessException.conflict("存在多个适用实例，请明确instance_id");}return eligible.get(0);
    }

    private BusinessTaskInputs.Scope resolveInput(JdbcTemplate jdbc,BusinessActor actor,Map<String,Object> input,String mode,boolean processing){
        if(!"capability_call".equals(text(input,"kind",64))){return taskInputs.resolve(jdbc,actor,input,mode,processing);}
        fields(input,"kind","payload");if(!"once".equals(mode)){throw BusinessException.invalid("capability_call须为once");}
        Map<String,Object> payload=map(required(input,"payload"));Set<String> sources=new LinkedHashSet<>();
        if(payload.containsKey("source_ids")){for(String source:uuids(payload.get("source_ids"))){actor.requireSource(source);sources.add(source);}}
        return new BusinessTaskInputs.Scope(sources,OffsetDateTime.now().plusDays(7));
    }

    private static List<String> strings(Object value,int maximum){
        List<String> result=new ArrayList<>();for(Object item:list(value)){String text=text(values("item",item),"item",maximum);if(!result.contains(text)){result.add(text);}}
        if(result.isEmpty()){throw BusinessException.invalid("字符串数组不能为空");}return result;
    }
    private static List<String> uuids(Object value){List<String> result=new ArrayList<>();for(Object item:list(value)){String id=uuid(item,"id");if(!result.contains(id)){result.add(id);}}return result;}
    private static String pgArray(List<String> values){List<String> escaped=new ArrayList<>();for(String value:values){escaped.add("\""+value.replace("\\","\\\\").replace("\"","\\\"")+"\"");}return "{"+String.join(",",escaped)+"}";}
    private static List<String> array(Object value){try{Object[] values=(Object[])((java.sql.Array)value).getArray();List<String> result=new ArrayList<>();for(Object item:values){result.add(item.toString());}return result;}catch(Exception exception){throw new IllegalStateException("Invalid database array",exception);}}
    private static OffsetDateTime timestamp(Object value){if(value instanceof OffsetDateTime){return (OffsetDateTime)value;}return ((Timestamp)value).toInstant().atOffset(ZoneOffset.UTC);}

}
