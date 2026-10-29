package edu.cqupt.hxjm.algdeployment.business.service;

import java.sql.Timestamp;
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
    private final BusinessDataAccess businessData;
    private final ActivityBusinessService activityService;

    public CapabilityTaskService(BusinessStore store) { this(store,null,null); }
    @Autowired
    public CapabilityTaskService(BusinessStore store,BusinessDataAccess businessData,ActivityBusinessService activityService) {
        this.store=store;this.businessData=businessData;this.activityService=activityService;
    }

    public Map<String, Object> capabilities(String code) {
        List<Map<String, Object>> items = store.jdbc().queryForList("SELECT capability_code,display_name,object_types,input_kinds,contract_json::text,enabled,revision "
                + "FROM public.capability_definition" + (code == null ? "" : " WHERE capability_code=?") + " ORDER BY capability_code", code == null ? new Object[]{} : new Object[]{code});
        for (Map<String, Object> item : items) {
            item.put("contract", parse(item.remove("contract_json").toString()));
            item.put("object_types", array(item.get("object_types")));
            item.put("input_kinds", array(item.get("input_kinds")));
        }
        return values("items", items);
    }

    public Map<String, Object> capability(BusinessActor actor, Map<String, Object> body) {
        fields(body,"request_id","trace_id","capability_code","display_name","object_types","input_kinds","contract");
        String code = text(body,"capability_code",64);
        String name = text(body,"display_name",128);
        List<String> objects = strings(required(body,"object_types"),128);
        List<String> kinds = strings(required(body,"input_kinds"),64);
        Map<String,Object> contract = map(required(body,"contract"));
        fields(contract,"input_schema","parameters_schema","output_types");
        BusinessSchemas.check(map(required(contract,"input_schema")));
        BusinessSchemas.check(map(required(contract,"parameters_schema")));
        strings(required(contract,"output_types"),64);
        return store.write(actor,"capabilities.register",body,OffsetDateTime.now().plusDays(7),jdbc -> {
            if (!jdbc.queryForList("SELECT capability_code FROM public.capability_definition WHERE capability_code=?",code).isEmpty()) {
                throw BusinessException.conflict("能力已存在，本接口不隐式修改已发布契约");
            }
            jdbc.update("INSERT INTO public.capability_definition(capability_code,display_name,object_types,input_kinds,contract_json) VALUES (?,?,?::text[],?::text[],?::jsonb)",
                    code,name,pgArray(objects),pgArray(kinds),json(contract));
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
        fields(body,"request_id","trace_id","instance_id","capability_code","instance_key","implementation_code","implementation_version","source_ids","service_ref","enabled","expected_revision");
        String id = uuid(body,"instance_id");
        String capability = text(body,"capability_code",64);
        String key = text(body,"instance_key",128);
        String implementation = text(body,"implementation_code",64);
        String version = text(body,"implementation_version",128);
        String service = text(body,"service_ref",256);
        List<String> sources = uuids(required(body,"source_ids"));
        if (sources.isEmpty()) { throw BusinessException.invalid("实例必须明确非空来源范围"); }
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
                jdbc.update("INSERT INTO public.capability_instance(id,capability_code,instance_key,implementation_code,implementation_version,source_ids,service_ref,enabled) VALUES (?::uuid,?,?,?,?,?::uuid[],?,?)",
                        id,capability,key,implementation,version,pgArray(sources),service,enabled);
            } else {
                for (String source : array(rows.get(0).get("source_ids"))) { actor.requireSource(source); }
                revision = ((Number) rows.get(0).get("revision")).longValue();
                if (expected == null || expected != revision) { throw BusinessException.conflict("实例修订号已改变"); }
                revision++;
                jdbc.update("UPDATE public.capability_instance SET capability_code=?,instance_key=?,implementation_code=?,implementation_version=?,source_ids=?::uuid[],service_ref=?,enabled=?,revision=?,updated_at=now() WHERE id=?::uuid",
                        capability,key,implementation,version,pgArray(sources),service,enabled,revision,id);
            }
            return values("instance_id",id,"revision",revision,"enabled",enabled);
        });
    }

    public Map<String, Object> instances(BusinessActor actor, String id, String capability) {
        if (id != null) { id = uuid(id,"instance_id"); }
        if (capability != null && (capability.trim().isEmpty() || capability.length() > 64)) {
            throw BusinessException.invalid("capability_code无效");
        }
        StringBuilder sql = new StringBuilder("SELECT id::text,capability_code,instance_key,implementation_code,implementation_version,source_ids,service_ref,enabled,revision,created_at,updated_at FROM public.capability_instance WHERE 1=1");
        List<Object> args = new ArrayList<>();
        if (id != null) { sql.append(" AND id=?::uuid"); args.add(id); }
        if (capability != null) { sql.append(" AND capability_code=?"); args.add(capability); }
        sql.append(" ORDER BY capability_code,instance_key,id");
        List<Map<String,Object>> items = store.jdbc().queryForList(sql.toString(), args.toArray());
        for (Map<String,Object> item : items) {
            List<String> sources = array(item.get("source_ids"));
            for (String source : sources) { actor.requireSource(source); }
            item.put("source_ids",sources);
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
        InputReference reference = resolveInput(store.jdbc(),actor,input,mode,false);
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
            selectInstance(jdbc,capability,instance,reference.sources);
            if (business != null) {
                jdbc.queryForObject("SELECT pg_advisory_xact_lock(hashtextextended(?,0)) IS NULL",Boolean.class,"task:" + kind + ":" + business);
                List<Map<String,Object>> old = jdbc.queryForList("SELECT task_id::text,actor_key,input_digest,expires_at>now() AS valid FROM public.business_task WHERE task_kind=? AND business_key=? FOR UPDATE",kind,business);
                if (!old.isEmpty()) {
                    Map<String,Object> row = old.get(0);
                    if (!actor.getActorKey().equals(row.get("actor_key"))) { throw BusinessException.forbidden(); }
                    if (!Boolean.TRUE.equals(row.get("valid"))) { throw BusinessException.expired("原业务任务已到期"); }
                    if (!digest.equals(row.get("input_digest"))) { throw BusinessException.conflict("业务键对应不同输入"); }
                    Map<String,Object> response = summary(jdbc,(String) row.get("task_id")); response.put("duplicate",true); return response;
                }
            }
            String task = UUID.randomUUID().toString();
            jdbc.update("INSERT INTO public.business_task(task_id,task_kind,business_key,task_mode,actor_key,owner_user_id,capability_code,input_json,input_digest,expires_at) VALUES (?::uuid,?,?,?,?,?,?,?::jsonb,?,?)",
                    task,kind,business,mode,actor.getActorKey(),actor.getUserId(),capability,json(snapshot),digest,expires);
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
            if (!expires.isAfter(OffsetDateTime.now())) { throw BusinessException.expired("任务已到期"); }
            if (((Number) row.get("revision")).longValue()!=expected || !"pending".equals(row.get("state"))) { throw BusinessException.conflict("任务状态或修订号已改变"); }
            Map<String,Object> snapshot = parse(row.get("input_json").toString());
            Map<String,Object> input = map(snapshot.get("input"));
            InputReference reference = resolveInput(jdbc,actor,input,row.get("task_mode").toString(),true);
            String bound = snapshot.get("instance_id") == null ? null : uuid(snapshot,"instance_id");
            if (bound != null && requestedInstance != null && !bound.equals(requestedInstance)) { throw BusinessException.conflict("不能更换任务已指定的实例"); }
            Map<String,Object> instance = selectInstance(jdbc,row.get("capability_code").toString(),requestedInstance==null?bound:requestedInstance,reference.sources);
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
        List<Map<String,Object>> rows=jdbc.queryForList("SELECT input_kinds,contract_json::text FROM public.capability_definition WHERE capability_code=? AND enabled",code);
        if(rows.isEmpty()){throw BusinessException.notFound("能力不存在或已停用");}return rows.get(0);
    }

    private static Map<String,Object> selectInstance(JdbcTemplate jdbc,String capability,String id,Set<String> sources){
        List<Map<String,Object>> rows=jdbc.queryForList("SELECT * FROM public.capability_instance WHERE capability_code=? AND enabled"+(id==null?"":" AND id=?::uuid")+" ORDER BY id",id==null?new Object[]{capability}:new Object[]{capability,id});
        List<Map<String,Object>> eligible=new ArrayList<>();
        for(Map<String,Object> row:rows){if(array(row.get("source_ids")).containsAll(sources)){eligible.add(row);}}
        if(eligible.isEmpty()){throw BusinessException.notFound("没有适用于输入来源的启用实例");}
        if(eligible.size()>1){throw BusinessException.conflict("存在多个适用实例，请明确instance_id");}return eligible.get(0);
    }

    private InputReference resolveInput(JdbcTemplate jdbc,BusinessActor actor,Map<String,Object> input,String mode,boolean processing){
        String kind=text(input,"kind",64);Set<String> sources=new LinkedHashSet<>();OffsetDateTime expires=null;
        if("live_video".equals(kind)){
            fields(input,"kind","source_id","stream_session_id");
            if(!"continuous".equals(mode)){throw BusinessException.invalid("直播任务须使用continuous");}
            String source=uuid(input,"source_id");actor.requireSource(source);sources.add(source);String session=uuid(input,"stream_session_id");
            List<Map<String,Object>> rows=jdbc.queryForList("SELECT expires_at,state FROM public.stream_session WHERE id=?::uuid AND source_id=?::uuid",session,source);
            if(rows.isEmpty()){throw BusinessException.notFound("输入会话不存在或来源不匹配");}
            if(processing&&!"open".equals(rows.get(0).get("state"))){throw BusinessException.conflict("连续输入会话已结束");}
            expires=timestamp(rows.get(0).get("expires_at"));
        }else if("recording".equals(kind)||"image".equals(kind)){
            fields(input,"kind","asset_ids","start_at","end_at");if(!"once".equals(mode)){throw BusinessException.invalid("文件任务须使用once");}
            List<String> assets=uuids(required(input,"asset_ids"));if(assets.isEmpty()){throw BusinessException.invalid("asset_ids不能为空");}
            OffsetDateTime start=null,end=null;if("recording".equals(kind)){start=time(input,"start_at");end=time(input,"end_at");if(!end.isAfter(start)){throw BusinessException.invalid("处理右端须晚于左端");}}
            for(String asset:assets){
                List<Map<String,Object>> rows=jdbc.queryForList("SELECT source_id::text,state,expires_at,start_ts,duration_ms FROM public.media_asset WHERE id=?::uuid",asset);
                if(rows.isEmpty()){throw BusinessException.notFound("输入资产不存在");}Map<String,Object> row=rows.get(0);
                if(row.get("source_id")==null){
                    if(!"image".equals(kind)||businessData==null){throw BusinessException.invalid("无来源输入须为已授权图片");}
                    businessData.recordings().asset(actor,asset);
                }else{String source=row.get("source_id").toString();actor.requireSource(source);sources.add(source);}
                if(processing&&!"available".equals(row.get("state"))){throw BusinessException.conflict("输入资产尚不可用");}
                OffsetDateTime expiry=row.get("expires_at")==null?OffsetDateTime.now().plusDays(7):timestamp(row.get("expires_at"));expires=expires==null||expiry.isBefore(expires)?expiry:expires;
                if(start!=null){OffsetDateTime from=timestamp(row.get("start_ts"));OffsetDateTime to=from.plusNanos(((Number)row.get("duration_ms")).longValue()*1000000);if(!from.isBefore(end)||!to.isAfter(start)){throw BusinessException.invalid("录像不与输入范围相交");}}
            }
        }else if(Arrays.asList("activity","event","query").contains(kind)){
            if(!"once".equals(mode)||activityService==null){throw BusinessException.invalid("业务主题须使用once任务");}
            String field=kind+"_id";fields(input,"kind",field);String id=uuid(input,field);
            Map<String,Object> subject=activityService.subject(jdbc,actor,kind,id);expires=BusinessDataAccess.expiry(subject);
            if("activity".equals(kind)){for(Object item:list(subject.get("tracks"))){sources.add(text(map(item),"source_id",36));}}
            else if("event".equals(kind)){
                if(subject.get("source_id")!=null){sources.add(subject.get("source_id").toString());}
                for(Map<String,Object> row:jdbc.queryForList("SELECT DISTINCT source_id::text FROM public.evidence_reference WHERE event_id=?::uuid AND source_id IS NOT NULL AND expires_at>now()",id)){sources.add(row.get("source_id").toString());}
            }else{
                Map<String,Object> scope=parse(subject.get("scope_json").toString());for(Object value:list(scope.get("source_ids"))){String source=uuid(value,"source_id");actor.requireSource(source);sources.add(source);}
            }
        }else{throw BusinessException.invalid("任务输入支持live_video、recording、image、activity、event或query");}
        if(expires==null||!expires.isAfter(OffsetDateTime.now())){throw BusinessException.expired("输入已到期");}return new InputReference(sources,expires);
    }

    private static List<String> strings(Object value,int maximum){
        List<String> result=new ArrayList<>();for(Object item:list(value)){String text=text(values("item",item),"item",maximum);if(!result.contains(text)){result.add(text);}}
        if(result.isEmpty()){throw BusinessException.invalid("字符串数组不能为空");}return result;
    }
    private static List<String> uuids(Object value){List<String> result=new ArrayList<>();for(Object item:list(value)){String id=uuid(item,"id");if(!result.contains(id)){result.add(id);}}return result;}
    private static String pgArray(List<String> values){List<String> escaped=new ArrayList<>();for(String value:values){escaped.add("\""+value.replace("\\","\\\\").replace("\"","\\\"")+"\"");}return "{"+String.join(",",escaped)+"}";}
    private static List<String> array(Object value){try{Object[] values=(Object[])((java.sql.Array)value).getArray();List<String> result=new ArrayList<>();for(Object item:values){result.add(item.toString());}return result;}catch(Exception exception){throw new IllegalStateException("Invalid database array",exception);}}
    private static OffsetDateTime timestamp(Object value){if(value instanceof OffsetDateTime){return (OffsetDateTime)value;}return ((Timestamp)value).toInstant().atOffset(ZoneOffset.UTC);}
    private static final class InputReference{final Set<String> sources;final OffsetDateTime expires;InputReference(Set<String> sources,OffsetDateTime expires){this.sources=sources;this.expires=expires;}}
}
