package edu.cqupt.hxjm.algdeployment.business.service;

import java.time.OffsetDateTime;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessStore;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

/** Garbage is a projection of accepted algorithm results into the existing event model. */
@Service
@ConditionalOnProperty(prefix="hxjm.business",name="enabled",havingValue="true")
public class GarbageBusinessService {
    private final BusinessStore store;
    public GarbageBusinessService(BusinessStore store){this.store=store;}

    public static String region(Map<String,Object> target){
        List<Object> b=list(required(target,"bbox"));
        if(b.size()!=4){throw BusinessException.invalid("垃圾框必须为归一化xyxy");}
        for(Object v:b){if(!(v instanceof Number)||!Double.isFinite(((Number)v).doubleValue())||((Number)v).doubleValue()<0||((Number)v).doubleValue()>1){throw BusinessException.invalid("垃圾框坐标无效");}}
        if(((Number)b.get(0)).doubleValue()>=((Number)b.get(2)).doubleValue()||((Number)b.get(1)).doubleValue()>=((Number)b.get(3)).doubleValue()){throw BusinessException.invalid("垃圾框须有正面积");}
        double x=(((Number)b.get(0)).doubleValue()+((Number)b.get(2)).doubleValue())/2;
        double y=(((Number)b.get(1)).doubleValue()+((Number)b.get(3)).doubleValue())/2;
        return "r"+(Math.min(2,(int)(y*3))+1)+"c"+(Math.min(2,(int)(x*3))+1);
    }
    public static void record(JdbcTemplate jdbc,Map<String,Object> body,Map<String,Object> result){
        Map<String,Object> payload=map(required(result,"payload"));
        String source=uuid(body,"source_id"),resultId=uuid(result,"result_id");
        OffsetDateTime at=time(result,"start_at"),expires=at.plusDays(7);
        List<Object> targets=list(required(payload,"targets"));
        if(!Boolean.valueOf(!targets.isEmpty()).equals(payload.get("has_target"))){throw BusinessException.invalid("垃圾目标标志与列表矛盾");}
        for(Object value:targets){
            Map<String,Object> target=map(value);String category=text(target,"category",64),region=region(target);
            // shortcut: one source/category/3x3 cell aggregates five minutes; use tracking only when calibrated identities exist.
            String key=source+":"+category+":"+region+":"+(at.toEpochSecond()/300);
            jdbc.queryForObject("SELECT pg_advisory_xact_lock(hashtextextended(?,0)) IS NULL",Boolean.class,"garbage:"+key);
            List<Map<String,Object>> prior=jdbc.queryForList("SELECT id,conclusion_json::text,state FROM public.business_event WHERE event_type='garbage.detected' AND event_key=? FOR UPDATE",key);
            String id=prior.isEmpty()?UUID.randomUUID().toString():prior.get(0).get("id").toString();
            Map<String,Object> conclusion=values("category",category,"region",region,"bbox",target.get("bbox"),"confidence",target.get("confidence"),"result_id",resultId,"last_detected_at",iso(at));
            if(prior.isEmpty()){
                jdbc.update("INSERT INTO public.business_event(id,event_type,event_key,source_id,start_at,state,conclusion_json,run_id,expires_at) VALUES(?::uuid,'garbage.detected',?,?::uuid,?,'open',?::jsonb,?::uuid,?)",id,key,source,at,json(conclusion),uuid(body,"run_id"),expires);
            }else{
                jdbc.update("UPDATE public.business_event SET conclusion_json=conclusion_json||?::jsonb,expires_at=GREATEST(expires_at,?),revision=revision+1,updated_at=now() WHERE id=?::uuid",json(conclusion),expires,id);
            }
            jdbc.update("INSERT INTO public.evidence_reference(event_id,source_id,original_result_id,start_at,end_at,fact_snapshot,provenance_json,expires_at) SELECT ?::uuid,?::uuid,?::uuid,?,?,?::jsonb,?::jsonb,? WHERE NOT EXISTS(SELECT 1 FROM public.evidence_reference WHERE event_id=?::uuid AND original_result_id=?::uuid)",id,source,resultId,at,at,json(values("result_type","garbage.detection","schema_version","1","payload",payload)),json(values("result_id",resultId)),expires,id,resultId);
        }
    }
    public Map<String,Object> event(BusinessActor actor,String id){
        List<Map<String,Object>> rows=store.jdbc().queryForList("SELECT id::text AS event_id,source_id::text,start_at,state,conclusion_json::text,expires_at,expires_at>now() AS valid FROM public.business_event WHERE id=?::uuid AND event_type='garbage.detected'",uuid(id,"event_id"));
        if(rows.isEmpty()){throw BusinessException.notFound("垃圾事件不存在");}
        Map<String,Object> event=rows.get(0);actor.requireSource(event.get("source_id").toString());
        if(!Boolean.TRUE.equals(event.remove("valid"))){throw BusinessException.expired("垃圾事件到期");}
        event.put("detection",parse(event.remove("conclusion_json").toString()));
        List<Map<String,Object>> tasks=store.jdbc().queryForList("SELECT t.task_id::text,t.state,t.error_code,a.external_execution::text FROM public.business_task t LEFT JOIN public.task_attempt a ON a.run_id=t.current_run_id WHERE t.task_kind='garbage.cleanup' AND t.input_json->'input'->'payload'->>'event_id'=? ORDER BY t.created_at DESC LIMIT 1",id);
        if(!tasks.isEmpty()){
            Map<String,Object> task=tasks.get(0);Object external=task.remove("external_execution");task.put("device",external==null?null:parse(external.toString()));event.put("cleanup",task);
        }
        event.put("evidence",store.jdbc().queryForList("SELECT id::text AS evidence_id,asset_id::text,original_result_id::text FROM public.evidence_reference WHERE event_id=?::uuid AND expires_at>now() ORDER BY created_at DESC LIMIT 1",id));
        return event;
    }
    public Map<String,Object> query(BusinessActor actor){
        List<Map<String,Object>> items=new ArrayList<>();
        for(String id:store.jdbc().queryForList("SELECT id::text FROM public.business_event WHERE event_type='garbage.detected' AND expires_at>now() AND source_id=ANY(?::uuid[]) ORDER BY start_at DESC,id DESC LIMIT 100",String.class,"{"+String.join(",",actor.getSourceIds())+"}")){items.add(event(actor,id));}
        return values("items",items);
    }
    public void refreshCleanup(String task){
        store.transaction(jdbc->{
            List<Map<String,Object>> rows=jdbc.queryForList("SELECT t.state,t.error_code,t.input_json->'input'->'payload'->>'event_id' AS event_id,a.external_execution::text FROM public.business_task t LEFT JOIN public.task_attempt a ON a.run_id=t.current_run_id WHERE t.task_id=?::uuid AND t.task_kind='garbage.cleanup'",task);
            if(rows.isEmpty()){return null;}Map<String,Object> row=rows.get(0);String event=uuid(row.get("event_id"),"event_id");
            Map<String,Object> external=row.get("external_execution")==null?values():parse(row.get("external_execution").toString());
            // The existing M20 protocol confirms route completion, not removal of this detected object.
            jdbc.update("UPDATE public.business_event SET conclusion_json=conclusion_json||?::jsonb,revision=revision+1,updated_at=now() WHERE id=?::uuid",json(values("cleanup",values("task_id",task,"state",row.get("state"),"error_code",row.get("error_code"),"device",external))),event);
            return null;
        });
    }
}
