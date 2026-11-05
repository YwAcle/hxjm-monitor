package edu.cqupt.hxjm.algdeployment.business.service;

import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;
import java.sql.Timestamp;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessStore;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessCanonical;

/** Ordered producer lifecycle events; absence from a displayed frame is not a close event. */
@Service
@ConditionalOnProperty(prefix="hxjm.business",name="enabled",havingValue="true")
public class TrackingLifecycleService {
    private final BusinessStore store;
    public TrackingLifecycleService(BusinessStore store) { this.store=store; }

    public Map<String,Object> close(BusinessActor actor,Map<String,Object> body) {
        fields(body,"request_id","trace_id","source_id","task_id","run_id","tracking_context_id",
                "end_reason","ended_at","reason_code","close_context","local_track_ids","gap_start_at","gap_end_at");
        String source=uuid(body,"source_id"); actor.requireSource(source);
        String task=uuid(body,"task_id"),run=uuid(body,"run_id"),context=uuid(body,"tracking_context_id");
        String reason=text(body,"end_reason",32); text(body,"reason_code",64);
        if(!Arrays.asList("normal","observation_interrupted","cancelled").contains(reason)){
            throw BusinessException.invalid("轨迹结束原因无效");
        }
        if(!(body.get("close_context") instanceof Boolean)){throw BusinessException.invalid("close_context须为布尔值");}
        boolean closeContext=Boolean.TRUE.equals(body.get("close_context"));
        List<Object> localIds=list(required(body,"local_track_ids"));
        Set<Long> unique=new HashSet<>();
        for(Object id:localIds){
            Map<String,Object> field=values("id",id);
            if(!unique.add(integer(field,"id",0,9007199254740991L))){throw BusinessException.invalid("局部号不能重复");}
        }
        if((!closeContext&&localIds.isEmpty())||localIds.size()>10000){throw BusinessException.invalid("轨迹清单为空或过大");}
        OffsetDateTime ended=time(body,"ended_at");
        if(body.containsKey("gap_start_at")!=body.containsKey("gap_end_at")){throw BusinessException.invalid("缺口起止时间须同时给出");}
        final OffsetDateTime gapStart=body.containsKey("gap_start_at")?time(body,"gap_start_at"):null;
        final OffsetDateTime gapEnd=body.containsKey("gap_end_at")?time(body,"gap_end_at"):null;
        if(gapStart!=null&&(!closeContext||!gapEnd.isAfter(gapStart))){throw BusinessException.invalid("缺口范围无效");}
        return store.write(actor,"tracking.close",body,ended.plusDays(7),jdbc->{
            Map<String,Object> attempt=one(jdbc,"SELECT t.actor_key,t.input_json::text,a.lease_owner,a.state,a.expires_at,"+
                    "t.current_run_id::text AS current_run_id FROM public.business_task t JOIN public.task_attempt a ON a.task_id=t.task_id "+
                    "WHERE t.task_id=?::uuid AND a.run_id=?::uuid FOR UPDATE OF t,a",task,run);
            if(!actor.getActorKey().equals(attempt.get("lease_owner"))||!actor.getActorKey().equals(attempt.get("actor_key"))){
                throw BusinessException.forbidden();
            }
            Map<String,Object> input=map(parse(attempt.get("input_json").toString()).get("input"));
            if(!"live_video".equals(input.get("kind"))||!source.equals(input.get("source_id"))){throw BusinessException.forbidden();}
            if(!at(attempt.get("expires_at")).isAfter(OffsetDateTime.now())){throw BusinessException.expired("执行已到期");}
            List<Map<String,Object>> contexts=jdbc.queryForList("SELECT x.*,s.source_id::text AS source FROM public.tracking_context x "+
                    "JOIN public.stream_session s ON s.id=x.stream_session_id WHERE x.id=?::uuid AND x.run_id=?::uuid FOR UPDATE OF x",context,run);
            int updated=0;
            if(contexts.isEmpty()&&!jdbc.queryForList("SELECT id FROM public.tracking_context WHERE id=?::uuid",context).isEmpty()){
                throw BusinessException.forbidden();
            }
            if(!contexts.isEmpty()){
                Map<String,Object> row=contexts.get(0);
                if(!source.equals(row.get("source"))){throw BusinessException.forbidden();}
                if(ended.isBefore(at(row.get("started_at")))){throw BusinessException.invalid("结束早于上下文开始");}
                List<Map<String,Object>> tracks=jdbc.queryForList("SELECT id::text,local_track_id,last_observed_at,start_ts,end_reason "+
                        "FROM public.tracklet WHERE tracking_context_id=?::uuid ORDER BY id FOR UPDATE",context);
                Set<Long> found=new HashSet<>();
                for(Map<String,Object> track:tracks){
                    long local=((Number)track.get("local_track_id")).longValue();
                    if(!closeContext&&!unique.contains(local)){continue;}
                    found.add(local);
                    if(track.get("end_reason")!=null){continue;}
                    OffsetDateTime last=track.get("last_observed_at")==null?at(track.get("start_ts")):at(track.get("last_observed_at"));
                    if(!last.isBefore(ended)){throw BusinessException.conflict("结束边界未包含已保存真实观测");}
                    updated+=jdbc.update("UPDATE public.tracklet SET end_ts=?,end_reason=?,expires_at=?,revision=revision+1,updated_at=now() "+
                            "WHERE id=?::uuid AND end_reason IS NULL",last,reason,last.plusDays(7),track.get("id"));
                }
                if(!closeContext&&!found.containsAll(unique)){throw BusinessException.conflict("结束事件引用尚未登记的轨迹");}
                if(closeContext){
                    Timestamp last=jdbc.queryForObject("SELECT max(f.occurred_at) FROM public.analysis_frame af "+
                            "JOIN public.input_frame f ON f.id=af.input_frame_id JOIN public.result_set rs ON rs.id=af.result_set_id "+
                            "WHERE rs.run_id=?::uuid AND rs.set_key=?",Timestamp.class,run,"tracking:"+context);
                    if(last!=null&&!at(last).isBefore(ended)){throw BusinessException.conflict("结束边界未包含已保存帧");}
                    if(row.get("ended_at")!=null&&!ended.isEqual(at(row.get("ended_at")))){throw BusinessException.conflict("上下文已有不同结束边界");}
                    jdbc.update("UPDATE public.tracking_context SET ended_at=?,expires_at=GREATEST(expires_at,?) WHERE id=?::uuid",ended,ended.plusDays(7),context);
                }
            }else if(!closeContext){throw BusinessException.notFound("跟踪上下文尚未登记");}
            // A context with no successful frames still owns a task that must be retired.
            if(closeContext&&jdbc.queryForObject("SELECT count(*) FROM public.tracking_context WHERE run_id=?::uuid AND ended_at IS NULL",Long.class,run)==0){
                String state="cancelled".equals(reason)?"cancelled":("normal".equals(reason)?"succeeded":"partial");
                jdbc.update("UPDATE public.task_attempt SET state=?,finished_at=now(),lease_until=NULL,updated_at=now() WHERE run_id=?::uuid "+
                        "AND state IN ('running','waiting_input')",state,run);
                jdbc.update("UPDATE public.business_task SET state=?,revision=revision+1,updated_at=now() WHERE task_id=?::uuid "+
                        "AND current_run_id=?::uuid AND state IN ('running','waiting_input')",state,task,run);
            }
            if(gapStart!=null){
                jdbc.update("INSERT INTO public.processing_coverage(source_id,run_id,stage,coverage_key,closed,start_at,end_at,status,"+
                        "analyzed_frame_count,saved_frame_count,frame_manifest_json,reason_code,expires_at) "+
                        "VALUES (?::uuid,?::uuid,'analysis',?,true,?,?,'gap',0,0,?::jsonb,?,?) ON CONFLICT (source_id,stage,coverage_key) DO NOTHING",
                        source,run,"tracking-gap:"+BusinessCanonical.digest(body),gapStart,gapEnd,
                        json(values("schema_version","1","frame_ids",java.util.Collections.emptyList())),text(body,"reason_code",64),gapEnd.plusDays(7));
            }
            Map<String,Object> response=values("tracking_context_id",context,"closed_track_count",updated,"context_closed",closeContext);
            // Request-scoped event identity avoids revision collisions between separate local IDs.
            store.event(jdbc,"tracking.closed","tracking_context",context,
                    jdbc.queryForObject("SELECT coalesce(max(aggregate_revision),0)+1 FROM public.outbox_event "+
                            "WHERE aggregate_type='tracking_context' AND aggregate_id=?::uuid",Long.class,context),response,ended.plusDays(7));
            return response;
        });
    }

    private static OffsetDateTime at(Object value){return value instanceof OffsetDateTime?(OffsetDateTime)value:((Timestamp)value).toInstant().atOffset(ZoneOffset.UTC);}
    private static Map<String,Object> one(JdbcTemplate jdbc,String sql,Object... args){
        List<Map<String,Object>> rows=jdbc.queryForList(sql,args);
        if(rows.isEmpty()){throw BusinessException.notFound("跟踪执行不存在");}return rows.get(0);
    }
}
