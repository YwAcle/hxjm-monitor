package edu.cqupt.hxjm.algdeployment.business.service;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;
import static edu.cqupt.hxjm.algdeployment.business.service.BusinessDataAccess.*;

@Service
@ConditionalOnProperty(prefix="hxjm.business",name="enabled",havingValue="true")
public class ActivityBusinessService {
    private final BusinessDataAccess data;
    public ActivityBusinessService(BusinessDataAccess data){this.data=data;}

    public Map<String,Object> activity(JdbcTemplate jdbc,BusinessActor actor,String id){
        Map<String,Object> a=one(jdbc.queryForList("SELECT id AS activity_id,identity_id,title,start_ts,end_ts,activity_type,state,end_reason,coverage_json,revision,expires_at FROM public.episode WHERE id=?::uuid AND identity_id IS NOT NULL",id),"活动不存在");fresh(a);
        List<Map<String,Object>> tracks=jdbc.queryForList("SELECT t.id AS tracklet_id,t.source_id,t.stream_session_id,t.first_observed_at,t.last_observed_at,t.start_ts,t.end_ts,t.end_reason,t.expires_at FROM public.episode_tracklet_link l JOIN public.tracklet t ON t.id=l.tracklet_id WHERE l.episode_id=?::uuid AND t.expires_at>now() ORDER BY t.first_observed_at,t.id",id);
        if(tracks.isEmpty()){data.identity(jdbc,actor,a.get("identity_id").toString());}
        for(Map<String,Object> t:tracks){actor.requireSource(String.valueOf(t.get("source_id")));clean(t);}a.put("tracks",tracks);return a;
    }
    public Map<String,Object> getActivity(BusinessActor actor,String id){return clean(activity(data.store().jdbc(),actor,uuid(id,"activity_id")));}

    public Map<String,Object> activities(BusinessActor actor,Map<String,Object> body){
        fields(body,"identity_id","source_ids","start_at","end_at","state","limit","trace_id");
        String identity=optionalId(body,"identity_id"),state=optionalText(body,"state",16);List<String> sources=body.get("source_ids")==null?new ArrayList<>(actor.getSourceIds()):ids(body.get("source_ids"));actor.authorizedSources(sources);
        OffsetDateTime from=body.get("start_at")==null?null:time(body,"start_at"),to=body.get("end_at")==null?null:time(body,"end_at");if(from!=null&&to!=null&&!to.isAfter(from)){throw BusinessException.invalid("时间范围无效");}
        int limit=body.containsKey("limit")?(int)integer(body,"limit",1,500):100;
        List<Map<String,Object>> items=new ArrayList<>();
        List<Map<String,Object>> rows=data.store().jdbc().queryForList("SELECT e.id FROM public.episode e WHERE e.identity_id IS NOT NULL AND e.expires_at>now() AND (?::uuid IS NULL OR e.identity_id=?::uuid OR EXISTS(SELECT 1 FROM public.identity_link il WHERE il.temporary_identity_id=e.identity_id AND il.registered_identity_id=?::uuid AND il.valid_to IS NULL AND il.expires_at>now())) AND (?::text IS NULL OR e.state=?) AND (?::timestamptz IS NULL OR e.end_ts>=?) AND (?::timestamptz IS NULL OR e.start_ts<?) AND EXISTS(SELECT 1 FROM public.episode_tracklet_link l JOIN public.tracklet t ON t.id=l.tracklet_id WHERE l.episode_id=e.id AND t.source_id=ANY(?::uuid[]) AND t.expires_at>now()) AND NOT EXISTS(SELECT 1 FROM public.episode_tracklet_link l JOIN public.tracklet t ON t.id=l.tracklet_id WHERE l.episode_id=e.id AND t.expires_at>now() AND NOT(t.source_id=ANY(?::uuid[]))) ORDER BY e.end_ts DESC,e.id LIMIT ?",identity,identity,identity,state,state,from,from,to,to,pgArray(sources),pgArray(actor.getSourceIds()),limit);
        for(Map<String,Object> row:rows){items.add(getActivity(actor,row.get("id").toString()));}return values("items",items,"scope",values("source_ids",sources,"start_at",from==null?null:iso(from),"end_at",to==null?null:iso(to)));
    }

    public Map<String,Object> close(BusinessActor actor,Map<String,Object> body){
        fields(body,"request_id","trace_id","activity_id","expected_revision","end_reason","coverage");
        String id=uuid(body,"activity_id"),reason=text(body,"end_reason",32);
        if(!Arrays.asList("normal","observation_interrupted","cancelled").contains(reason)){throw BusinessException.invalid("活动结束原因无效");}
        Map<String,Object> initial=activity(data.store().jdbc(),actor,id);Map<String,Object> coverage=object(body,"coverage");
        return data.store().write(actor,"activities.close",body,expiry(initial),jdbc->{
            jdbc.queryForList("SELECT id FROM public.episode WHERE id=?::uuid FOR UPDATE",id);Map<String,Object> current=activity(jdbc,actor,id);revision(current,body);
            if(!"open".equals(current.get("state"))){throw BusinessException.conflict("活动已结束");}
            String state="observation_interrupted".equals(reason)?"interrupted":"closed";OffsetDateTime end=at(current.get("end_ts")),expires=end.plusDays(7);
            jdbc.update("UPDATE public.episode SET state=?,end_reason=?,coverage_json=?::jsonb,expires_at=?,revision=revision+1 WHERE id=?::uuid",state,reason,json(coverage),expires,id);
            long rev=((Number)current.get("revision")).longValue()+1;
            data.store().event(jdbc,"activity.closed","episode",id,rev,values("activity_id",id,"identity_id",String.valueOf(current.get("identity_id")),"end_reason",reason),expires);
            return clean(activity(jdbc,actor,id));
        });
    }

    public Map<String,Object> event(BusinessActor actor,Map<String,Object> body){
        fields(body,"request_id","trace_id","event_id","event_type","event_key","source_id","start_at","end_at","state","end_reason","conclusion","run_id","coverage","result_ids","objects","expected_revision");
        String id=newId(body,"event_id"),type=text(body,"event_type",64),key=text(body,"event_key",128),source=optionalId(body,"source_id"),run=uuid(body,"run_id"),state=text(body,"state",16),reason=optionalText(body,"end_reason",32);
        OffsetDateTime start=time(body,"start_at"),end=body.get("end_at")==null?null:time(body,"end_at");
        if(!Arrays.asList("open","closed","interrupted").contains(state)||end!=null&&end.isBefore(start)||"open".equals(state)&&reason!=null||!"open".equals(state)&&(end==null||!Arrays.asList("normal","observation_interrupted","cancelled").contains(reason))){throw BusinessException.invalid("事件状态与时间边界不一致");}
        if(source!=null){actor.requireSource(source);}OffsetDateTime expires=(end==null?start:end).plusDays(7);
        Map<String,Object> conclusion=object(body,"conclusion"),coverage=object(body,"coverage");List<String> results=body.get("result_ids")==null?new ArrayList<>():ids(body.get("result_ids"));
        List<Object> objects=body.get("objects")==null?new ArrayList<>():list(body.get("objects"));
        if(source==null&&results.isEmpty()){throw BusinessException.invalid("事件须提供来源或已保存的成果依据");}
        return data.store().write(actor,"events.register",body,expires,jdbc->{
            data.run(jdbc,actor,run);
            jdbc.queryForObject("SELECT pg_advisory_xact_lock(hashtextextended(?,0)) IS NULL",Boolean.class,"event:"+type+":"+key);
            List<Map<String,Object>> old=jdbc.queryForList("SELECT * FROM public.business_event WHERE id=?::uuid OR (event_type=? AND event_key=?) FOR UPDATE",id,type,key);
            long rev=1;
            if(old.isEmpty()){
                if(body.containsKey("expected_revision")){throw BusinessException.conflict("新事件不接受修订号");}
                jdbc.update("INSERT INTO public.business_event(id,event_type,event_key,source_id,start_at,end_at,state,end_reason,conclusion_json,run_id,coverage_json,expires_at) VALUES (?::uuid,?,?,?::uuid,?,?,?,?,?::jsonb,?::uuid,?::jsonb,?)",id,type,key,source,start,end,state,reason,json(conclusion),run,json(coverage),expires);
            }else{
                Map<String,Object> previous=old.get(0);fresh(previous);
                if(!id.equals(String.valueOf(previous.get("id")))||!type.equals(previous.get("event_type"))||!key.equals(previous.get("event_key"))||!start.equals(at(previous.get("start_at")))){throw BusinessException.conflict("事件稳定标识、类型或起点冲突");}
                authorizeEvent(jdbc,actor,previous);revision(previous,body);
                if(!"open".equals(previous.get("state"))&&!expires.equals(expiry(previous))){throw BusinessException.conflict("已结束事件不能延长期限");}
                rev=((Number)previous.get("revision")).longValue()+1;
                jdbc.update("UPDATE public.business_event SET end_at=?,state=?,end_reason=?,conclusion_json=?::jsonb,run_id=?::uuid,coverage_json=?::jsonb,expires_at=?,revision=?,updated_at=now() WHERE id=?::uuid",end,state,reason,json(conclusion),run,json(coverage),expires,rev,id);
            }
            for(String result:results){
                Map<String,Object> r=one(jdbc.queryForList("SELECT r.*,s.source_id FROM public.algorithm_result r JOIN public.result_set s ON s.id=r.result_set_id WHERE r.id=?::uuid",result),"事件依据成果不存在");fresh(r);actor.requireSource(r.get("source_id").toString());
                if(jdbc.queryForList("SELECT id FROM public.evidence_reference WHERE event_id=?::uuid AND original_result_id=?::uuid",id,result).isEmpty()){
                    String evidence=UUID.randomUUID().toString();String asset=r.get("payload_asset_id")==null?null:r.get("payload_asset_id").toString();
                    jdbc.update("INSERT INTO public.evidence_reference(id,event_id,source_id,asset_id,original_result_id,start_at,end_at,fact_snapshot,provenance_json,expires_at) VALUES (?::uuid,?::uuid,?::uuid,?::uuid,?::uuid,?,?,?::jsonb,?::jsonb,?)",evidence,id,r.get("source_id"),asset,result,r.get("start_at"),r.get("end_at"),json(values("schema_version","1","result_type",r.get("result_type"),"payload",r.get("payload_json")==null?values():parse(r.get("payload_json").toString()))),json(values("schema_version","1","result_id",result,"run_id",run)),expires);
                    if(asset!=null){data.recordings().asset(actor,asset);jdbc.update("INSERT INTO public.asset_reference(asset_id,evidence_id,retain_until) VALUES (?::uuid,?::uuid,?)",asset,evidence,expires);}
                }
            }
            for(Object value:objects){Map<String,Object> object=map(value);fields(object,"identity_id","tracklet_id","sample_id","object_role");String identity=optionalId(object,"identity_id"),track=optionalId(object,"tracklet_id"),sample=optionalId(object,"sample_id"),role=object.get("object_role")==null?"subject":text(object,"object_role",32);
                if((identity==null?0:1)+(track==null?0:1)+(sample==null?0:1)!=1){throw BusinessException.invalid("事件参与对象须恰好指定一种引用");}
                if(identity!=null){data.identity(jdbc,actor,identity);}if(track!=null){data.track(jdbc,actor,track);}if(sample!=null){data.sample(jdbc,actor,sample);}
                jdbc.update("INSERT INTO public.event_object_link(event_id,identity_id,tracklet_id,sample_id,object_role,expires_at) VALUES (?::uuid,?::uuid,?::uuid,?::uuid,?,?) ON CONFLICT DO NOTHING",id,identity,track,sample,role,expires);
            }
            data.store().event(jdbc,"event.updated","business_event",id,rev,values("event_id",id,"event_type",type,"state",state),expires);
            return values("event_id",id,"revision",rev,"state",state,"expires_at",iso(expires));
        });
    }

    public Map<String,Object> getEvent(BusinessActor actor,String id){
        id=uuid(id,"event_id");Map<String,Object> event=one(data.store().jdbc().queryForList("SELECT * FROM public.business_event WHERE id=?::uuid",id),"事件不存在");fresh(event);authorizeEvent(data.store().jdbc(),actor,event);
        event.put("objects",data.store().jdbc().queryForList("SELECT identity_id::text,tracklet_id::text,sample_id::text,object_role FROM public.event_object_link WHERE event_id=?::uuid AND expires_at>now() ORDER BY id",id));
        event.put("evidence",evidence(data.store().jdbc(),"event_id",id));return clean(event);
    }
    void authorizeEvent(JdbcTemplate jdbc,BusinessActor actor,Map<String,Object> event){
        boolean any=false;if(event.get("source_id")!=null){actor.requireSource(event.get("source_id").toString());any=true;}
        for(Map<String,Object> source:jdbc.queryForList("SELECT DISTINCT source_id FROM public.evidence_reference WHERE event_id=?::uuid AND source_id IS NOT NULL AND expires_at>now()",event.get("id"))){actor.requireSource(source.get("source_id").toString());any=true;}
        if(!any){throw BusinessException.forbidden();}
    }
    static List<Map<String,Object>> evidence(JdbcTemplate jdbc,String column,String id){List<Map<String,Object>> rows=jdbc.queryForList("SELECT id AS evidence_id,source_id,asset_id,start_at,end_at,fact_snapshot AS fact_snapshot_json,provenance_json,expires_at FROM public.evidence_reference WHERE "+column+"=?::uuid AND expires_at>now() ORDER BY start_at,id",id);for(Map<String,Object> row:rows){clean(row);}return rows;}

    public Map<String,Object> report(BusinessActor actor,Map<String,Object> body){
        fields(body,"request_id","trace_id","report_id","subject_kind","subject_id","report_type","completeness","coverage","task_id","run_id","model_version","report_json","report_text","evidence_ids","expected_revision");
        String id=newId(body,"report_id"),kind=text(body,"subject_kind",16),subject=uuid(body,"subject_id"),type=text(body,"report_type",64),complete=text(body,"completeness",16),task=uuid(body,"task_id"),run=uuid(body,"run_id");
        if(!Arrays.asList("activity","event","query").contains(kind)||!Arrays.asList("partial","complete").contains(complete)){throw BusinessException.invalid("报告主题或完整性无效");}
        Map<String,Object> content=map(required(body,"report_json")),coverage=object(body,"coverage");String text=body.get("report_text")==null?null:documentText(body,"report_text",1000000),model=optionalText(body,"model_version",128);
        List<String> evidence=body.get("evidence_ids")==null?new ArrayList<>():ids(body.get("evidence_ids"));Map<String,Object> initial=subject(data.store().jdbc(),actor,kind,subject);OffsetDateTime expires=expiry(initial);
        return data.store().write(actor,"reports.register",body,expires,jdbc->{
            Map<String,Object> attempt=data.run(jdbc,actor,run);if(!task.equals(String.valueOf(attempt.get("task_id")))){throw BusinessException.conflict("报告任务与执行不一致");}subject(jdbc,actor,kind,subject);
            jdbc.queryForObject("SELECT pg_advisory_xact_lock(hashtextextended(?,0)) IS NULL",Boolean.class,"report:"+kind+":"+subject+":"+type);
            List<Map<String,Object>> prior=jdbc.queryForList("SELECT * FROM public.llm_report WHERE id=?::uuid OR (subject_kind=? AND subject_id=?::uuid AND report_type=?) FOR UPDATE",id,kind,subject,type);long rev=1;
            if(prior.isEmpty()){
                if(body.containsKey("expected_revision")){throw BusinessException.conflict("新报告不接受修订号");}
                jdbc.update("INSERT INTO public.llm_report(id,episode_id,event_id,query_id,subject_kind,subject_id,report_type,completeness,coverage_json,task_id,run_id,model_version,processed_at,revision,expires_at,report_json,report_text) VALUES (?::uuid,?::uuid,?::uuid,?::uuid,?,?::uuid,?,?,?::jsonb,?::uuid,?::uuid,?,now(),1,?,?::jsonb,?)",id,"activity".equals(kind)?subject:null,"event".equals(kind)?subject:null,"query".equals(kind)?subject:null,kind,subject,type,complete,json(coverage),task,run,model,expires,json(content),text);
            }else{
                Map<String,Object> old=prior.get(0);fresh(old);if(!id.equals(String.valueOf(old.get("id")))||!kind.equals(old.get("subject_kind"))||!subject.equals(String.valueOf(old.get("subject_id")))||!type.equals(old.get("report_type"))){throw BusinessException.conflict("报告业务主题已存在，请更新原报告");}revision(old,body);
                if(old.get("task_id")!=null&&!task.equals(String.valueOf(old.get("task_id")))){throw BusinessException.conflict("补齐报告必须沿用稳定任务");}
                rev=((Number)old.get("revision")).longValue()+1;
                jdbc.update("UPDATE public.llm_report SET completeness=?,coverage_json=?::jsonb,run_id=?::uuid,model_version=?,processed_at=now(),revision=?,report_json=?::jsonb,report_text=? WHERE id=?::uuid",complete,json(coverage),run,model,rev,json(content),text,id);
                jdbc.update("DELETE FROM public.report_evidence_link WHERE report_id=?::uuid",id);
            }
            int ordinal=0;for(String ev:evidence){Map<String,Object> e=one(jdbc.queryForList("SELECT * FROM public.evidence_reference WHERE id=?::uuid",ev),"报告依据不存在");fresh(e);
                if(!subject.equals(String.valueOf(e.get("activity_id")))&&!subject.equals(String.valueOf(e.get("event_id")))){throw BusinessException.invalid("报告依据不属于当前主题");}if(e.get("source_id")!=null){actor.requireSource(e.get("source_id").toString());}
                jdbc.update("INSERT INTO public.report_evidence_link(report_id,evidence_id,report_revision,ordinal) VALUES (?::uuid,?::uuid,?,?)",id,ev,rev,ordinal++);
            }
            data.store().event(jdbc,"report.updated","llm_report",id,rev,values("report_id",id,"subject_kind",kind,"subject_id",subject,"completeness",complete),expires);
            return values("report_id",id,"revision",rev,"subject_kind",kind,"subject_id",subject,"completeness",complete,"expires_at",iso(expires));
        });
    }

    public Map<String,Object> subject(JdbcTemplate jdbc,BusinessActor actor,String kind,String id){
        if("activity".equals(kind)){return activity(jdbc,actor,id);}
        if("event".equals(kind)){Map<String,Object> event=one(jdbc.queryForList("SELECT * FROM public.business_event WHERE id=?::uuid",id),"报告事件不存在");fresh(event);authorizeEvent(jdbc,actor,event);return event;}
        if("query".equals(kind)){Map<String,Object> query=one(jdbc.queryForList("SELECT * FROM public.query_request WHERE id=?::uuid",id),"报告查询不存在");fresh(query);SampleFeatureService.authorizeQuery(actor,query);return query;}
        throw BusinessException.invalid("主题类型无效");
    }
    public Map<String,Object> getReport(BusinessActor actor,String id){id=uuid(id,"report_id");Map<String,Object> report=one(data.store().jdbc().queryForList("SELECT id AS report_id,subject_kind,subject_id,report_type,completeness,coverage_json,task_id,run_id,model_version,processed_at,revision,expires_at,report_json,report_text FROM public.llm_report WHERE id=?::uuid AND subject_id IS NOT NULL",id),"报告不存在");fresh(report);subject(data.store().jdbc(),actor,String.valueOf(report.get("subject_kind")),String.valueOf(report.get("subject_id")));
        report.put("evidence",data.store().jdbc().queryForList("SELECT evidence_id::text,ordinal,report_revision FROM public.report_evidence_link WHERE report_id=?::uuid ORDER BY ordinal",id));return clean(report);
    }
    public Map<String,Object> reports(BusinessActor actor,Map<String,Object> body){fields(body,"subject_kind","subject_id","after_processed_at","after_report_id","limit","trace_id");String kind=text(body,"subject_kind",16),subject=uuid(body,"subject_id");subject(data.store().jdbc(),actor,kind,subject);OffsetDateTime after=body.get("after_processed_at")==null?null:time(body,"after_processed_at");String afterId=optionalId(body,"after_report_id");if((after==null)!=(afterId==null)){throw BusinessException.invalid("报告游标须同时提供处理时间与报告ID");}int limit=body.containsKey("limit")?(int)integer(body,"limit",1,500):100;
        List<Map<String,Object>> rows=data.store().jdbc().queryForList("SELECT id FROM public.llm_report WHERE subject_kind=? AND subject_id=?::uuid AND expires_at>now() AND (?::timestamptz IS NULL OR (processed_at,id)>(?::timestamptz,?::uuid)) ORDER BY processed_at,id LIMIT ?",kind,subject,after,after,afterId,limit+1);
        boolean more=rows.size()>limit;List<Map<String,Object>> items=new ArrayList<>();for(Map<String,Object> row:rows.subList(0,Math.min(limit,rows.size()))){items.add(getReport(actor,row.get("id").toString()));}Map<String,Object> cursor=items.isEmpty()?null:values("after_processed_at",items.get(items.size()-1).get("processed_at"),"after_report_id",items.get(items.size()-1).get("report_id"));return values("items",items,"has_more",more,"next_cursor",more?cursor:null);
    }
}
