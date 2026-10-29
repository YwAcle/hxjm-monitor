package edu.cqupt.hxjm.algdeployment.business.service;

import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.sql.Savepoint;
import java.sql.Timestamp;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessCanonical;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessStore;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessSchemas;

/** Reliable result registration. Live WebSocket delivery does not enter this transaction. */
@Service
@ConditionalOnProperty(prefix="hxjm.business",name="enabled",havingValue="true")
public class ResultRegistrationService {
    private final BusinessStore store;
    private volatile Boolean identitySchema;
    public ResultRegistrationService(BusinessStore store) { this.store=store; }

    public Map<String,Object> register(BusinessActor actor, Map<String,Object> body) {
        fields(body,"request_id","trace_id","task_id","run_id","result_set_id","set_key","capability_code",
                "result_type","schema_version","source_id","stream_session_id","tracking_context_id","tracking_context",
                "results","processed_at","analysis_coverage");
        String source=uuid(body,"source_id"); actor.requireSource(source);
        uuid(body,"task_id"); uuid(body,"run_id"); uuid(body,"result_set_id"); uuid(body,"stream_session_id");
        text(body,"set_key"); text(body,"capability_code",64); text(body,"result_type",64); text(body,"schema_version",32);
        time(body,"processed_at");
        List<Object> results=list(required(body,"results"));
        Map<String,Object> coverage=map(required(body,"analysis_coverage"));
        validateCoverage(coverage,results,"detection.frame".equals(body.get("result_type")));
        Set<String> resultIds=new HashSet<>(),producerKeys=new HashSet<>();
        for (Object item:results) {
            Map<String,Object> result=map(item);
            if (!resultIds.add(uuid(result,"result_id")) || !producerKeys.add(text(result,"producer_result_key"))) {
                throw BusinessException.invalid("同一批次成果标识和生产键不能重复");
            }
        }
        return store.write(actor,"results.register",body,time(coverage,"end_at").plusDays(7),
                jdbc -> registerTransaction(jdbc,actor,body,coverage,results));
    }

    private Map<String,Object> registerTransaction(JdbcTemplate jdbc, BusinessActor actor,Map<String,Object> body,
                                                   Map<String,Object> coverage,List<Object> results) {
        String source=uuid(body,"source_id"),sessionId=uuid(body,"stream_session_id"),run=uuid(body,"run_id"),set=uuid(body,"result_set_id");
        Map<String,Object> task=one(jdbc,"SELECT t.*,a.lease_owner,a.state AS attempt_state,a.generation AS attempt_generation,"+
                "a.expires_at AS attempt_expires_at FROM public.business_task t JOIN public.task_attempt a ON a.task_id=t.task_id "+
                "WHERE t.task_id=?::uuid AND a.run_id=?::uuid FOR UPDATE OF t,a",uuid(body,"task_id"),run);
        if (!actor.getActorKey().equals(task.get("lease_owner")) && !actor.getActorKey().equals(task.get("actor_key"))) {
            throw BusinessException.forbidden();
        }
        live(task,"expires_at"); live(task,"attempt_expires_at");
        if (!body.get("capability_code").equals(task.get("capability_code"))) { throw BusinessException.conflict("任务能力不匹配"); }
        if (!java.util.Arrays.asList("running","waiting_input","succeeded","partial").contains(task.get("attempt_state"))) {
            throw BusinessException.conflict("执行状态不接收成果");
        }
        Map<String,Object> snapshot=parse(task.get("input_json").toString());
        if (!list(required(snapshot,"requested_outputs")).contains(body.get("result_type"))) {
            throw BusinessException.invalid("成果类型不在任务请求输出内");
        }
        Map<String,Object> input=map(snapshot.get("input"));
        if ("live_video".equals(input.get("kind"))) {
            if (!source.equals(input.get("source_id"))) { throw BusinessException.conflict("任务输入来源不匹配"); }
        } else if ("recording".equals(input.get("kind"))) {
            boolean matches=false;
            for (Object assetId:list(required(input,"asset_ids"))) {
                matches |= !jdbc.queryForList("SELECT id FROM public.media_asset WHERE id=?::uuid AND source_id=?::uuid AND stream_session_id=?::uuid AND expires_at>now()",
                        uuid(assetId,"asset_id"),source,sessionId).isEmpty();
            }
            if (!matches || time(coverage,"start_at").isBefore(time(input,"start_at")) || time(coverage,"end_at").isAfter(time(input,"end_at"))) {
                throw BusinessException.conflict("成果来源、会话或时间不属于录像任务输入");
            }
        } else { throw BusinessException.invalid("本阶段成果登记接收直播及录像任务"); }
        if (input.get("stream_session_id")!=null && !sessionId.equals(input.get("stream_session_id"))) {
            throw BusinessException.conflict("任务输入会话不匹配");
        }
        Map<String,Object> session=one(jdbc,"SELECT s.*,c.stream_name FROM public.stream_session s "+
                "LEFT JOIN public.camera_stream c ON c.id=s.camera_stream_id WHERE s.id=?::uuid AND s.source_id=?::uuid FOR UPDATE OF s",sessionId,source);
        live(session,"expires_at");
        if (session.get("camera_stream_id")==null) { throw BusinessException.conflict("视频会话尚未绑定已有流目录"); }
        if (time(coverage,"start_at").isBefore(at(session.get("started_at"))) ||
                (session.get("ended_at")!=null && time(coverage,"end_at").isAfter(at(session.get("ended_at"))))) {
            throw BusinessException.invalid("分析范围不在输入会话内");
        }
        Map<String,Object> type=one(jdbc,"SELECT * FROM public.result_type WHERE type_code=? AND schema_version=? AND enabled=true",
                text(body,"result_type",64),text(body,"schema_version",32));
        long generation=((Number)task.get("attempt_generation")).longValue();
        OffsetDateTime expires=time(coverage,"end_at").plusDays(7);
        jdbc.update("INSERT INTO public.result_set(id,run_id,source_id,stream_session_id,capability_code,set_key,generation,expires_at) "+
                "VALUES (?::uuid,?::uuid,?::uuid,?::uuid,?,?,?,?) ON CONFLICT DO NOTHING",set,run,source,sessionId,
                text(body,"capability_code",64),text(body,"set_key"),generation,expires);
        Map<String,Object> resultSet=one(jdbc,"SELECT *,run_id::text AS run_text,source_id::text AS source_text,"+
                "stream_session_id::text AS session_text FROM public.result_set WHERE id=?::uuid FOR UPDATE",set);
        live(resultSet,"expires_at");
        if (!run.equals(resultSet.get("run_text")) || !source.equals(resultSet.get("source_text")) ||
                !sessionId.equals(resultSet.get("session_text")) || !body.get("set_key").equals(resultSet.get("set_key")) ||
                !body.get("capability_code").equals(resultSet.get("capability_code"))) {
            throw BusinessException.conflict("成果集标识对应不同执行或输入");
        }
        jdbc.update("UPDATE public.result_set SET expires_at=GREATEST(expires_at,?) WHERE id=?::uuid",expires,set);
        String context=createContext(jdbc,body,results,session,expires);
        boolean uuidStream=Boolean.TRUE.equals(jdbc.queryForObject("SELECT a.atttypid='uuid'::regtype FROM pg_attribute a "+
                "WHERE a.attrelid='public.tracklet'::regclass AND a.attname='stream_id'",Boolean.class));
        List<String> accepted=new ArrayList<>(),duplicates=new ArrayList<>();
        List<Object> rejected=new ArrayList<>(),tracklets=new ArrayList<>();
        Set<String> mappedTracks=new HashSet<>();
        return jdbc.execute((ConnectionCallback<Map<String,Object>>) connection -> {
            for (Object item:results) {
                Map<String,Object> result=map(item);
                Savepoint checkpoint=connection.setSavepoint();
                List<Object> frameTracks=new ArrayList<>();
                try {
                    if (json(result).getBytes(StandardCharsets.UTF_8).length>((Number)type.get("max_inline_bytes")).intValue()) {
                        throw BusinessException.invalid("单项成果超过已登记的载荷上限");
                    }
                    boolean duplicate;
                    if ("detection.frame".equals(body.get("result_type"))) {
                        duplicate=saveFrame(jdbc,body,result,session,context,uuidStream,frameTracks);
                    } else { duplicate=saveTyped(jdbc,body,result,type); }
                    (duplicate?duplicates:accepted).add(uuid(result,"result_id"));
                    for (Object track:frameTracks) {
                        Map<String,Object> mapping=map(track);
                        if (mappedTracks.add(mapping.get("tracklet_id").toString())) { tracklets.add(mapping); }
                    }
                    connection.releaseSavepoint(checkpoint);
                } catch (BusinessException exception) {
                    connection.rollback(checkpoint); connection.releaseSavepoint(checkpoint);
                    rejected.add(values("result_id",uuid(result,"result_id"),"code",exception.getCode(),
                            "message",exception.getMessage(),"retryable",exception.isRetryable()));
                } catch (DataIntegrityViolationException exception) {
                    connection.rollback(checkpoint); connection.releaseSavepoint(checkpoint);
                    rejected.add(values("result_id",uuid(result,"result_id"),"code","CONFLICT",
                            "message","成果标识、关联或内容约束冲突","retryable",false));
                }
            }
            Map<String,Object> confirmed=saveCoverage(jdbc,body,coverage,rejected.isEmpty(),generation,
                    run.equals(String.valueOf(task.get("current_run_id"))),list(snapshot.get("requested_outputs")));
            if (!accepted.isEmpty()) {
                if ("open".equals(session.get("state"))) {
                    jdbc.update("UPDATE public.stream_session SET expires_at=GREATEST(expires_at,?) WHERE id=?::uuid",expires,sessionId);
                }
                jdbc.update("UPDATE public.business_task SET last_input_at=GREATEST(last_input_at,?),updated_at=now() WHERE task_id=?::uuid",
                        time(coverage,"end_at"),uuid(body,"task_id"));
                if ("continuous".equals(task.get("task_mode"))) {
                    jdbc.update("UPDATE public.business_task SET expires_at=GREATEST(expires_at,?) WHERE task_id=?::uuid",expires,uuid(body,"task_id"));
                    jdbc.update("UPDATE public.task_attempt SET expires_at=GREATEST(expires_at,?) WHERE run_id=?::uuid",expires,run);
                }
                store.event(jdbc,"results.registered","result_set",set,nextEventRevision(jdbc,set),
                        values("result_set_id",set,"result_ids",accepted),expires);
            }
            return values("result_set_id",set,"accepted_result_ids",accepted,"duplicate_result_ids",duplicates,
                    "rejected_results",rejected,"tracklets",tracklets,"coverage",confirmed);
        });
    }

    private String createContext(JdbcTemplate jdbc,Map<String,Object> body,List<Object> results,
                                  Map<String,Object> session,OffsetDateTime expires) {
        if (body.get("tracking_context_id")==null) { return null; }
        String id=uuid(body,"tracking_context_id"),run=uuid(body,"run_id"),sessionId=uuid(body,"stream_session_id");
        List<Map<String,Object>> old=jdbc.queryForList("SELECT *,run_id::text AS run_text,stream_session_id::text AS session_text "+
                "FROM public.tracking_context WHERE id=?::uuid FOR UPDATE",id);
        Map<String,Object> definition=body.get("tracking_context")==null?null:map(body.get("tracking_context"));
        int width=((Number)session.get("source_width")).intValue(),height=((Number)session.get("source_height")).intValue();
        if (!results.isEmpty() && "detection.frame".equals(body.get("result_type"))) {
            width=(int)integer(map(results.get(0)),"source_width",1,Integer.MAX_VALUE);
            height=(int)integer(map(results.get(0)),"source_height",1,Integer.MAX_VALUE);
        }
        if (old.isEmpty()) {
            if (definition==null) { throw BusinessException.invalid("首次登记跟踪上下文须提供定义"); }
            fields(definition,"context_key","started_at","reset_reason");
            jdbc.update("INSERT INTO public.tracking_context(id,stream_session_id,run_id,context_key,source_width,source_height,started_at,reset_reason,expires_at) "+
                    "VALUES (?::uuid,?::uuid,?::uuid,?,?,?,?,?,?)",id,sessionId,run,text(definition,"context_key"),width,height,
                    time(definition,"started_at"),definition.get("reset_reason"),expires);
        } else {
            Map<String,Object> previous=old.get(0); live(previous,"expires_at");
            if (!run.equals(previous.get("run_text")) || !sessionId.equals(previous.get("session_text")) ||
                    width!=((Number)previous.get("source_width")).intValue() || height!=((Number)previous.get("source_height")).intValue() ||
                    (definition!=null && (!text(definition,"context_key").equals(previous.get("context_key")) ||
                            !time(definition,"started_at").isEqual(at(previous.get("started_at"))) ||
                            !java.util.Objects.equals(definition.get("reset_reason"),previous.get("reset_reason"))))) {
                throw BusinessException.conflict("同一跟踪上下文的定义不同");
            }
            jdbc.update("UPDATE public.tracking_context SET expires_at=GREATEST(expires_at,?) WHERE id=?::uuid",expires,id);
        }
        return id;
    }

    public static void validateFrame(Map<String,Object> result,boolean tracking) {
        fields(result,"result_id","producer_result_key","frame_id","frame_seq","occurred_at","stream_pts_ms","time_quality",
                "media_asset_id","media_pts_ms","source_width","source_height","targets");
        uuid(result,"result_id"); text(result,"producer_result_key"); uuid(result,"frame_id");
        integer(result,"frame_seq",0,Long.MAX_VALUE); time(result,"occurred_at");
        integer(result,"source_width",1,Integer.MAX_VALUE); integer(result,"source_height",1,Integer.MAX_VALUE);
        if (!java.util.Arrays.asList("source_clock","ingest_estimated","reconciled").contains(result.get("time_quality"))) {
            throw BusinessException.invalid("time_quality无效");
        }
        if (result.get("stream_pts_ms")!=null) { integer(result,"stream_pts_ms",0,Long.MAX_VALUE); }
        if ((result.get("media_asset_id")==null)!=(result.get("media_pts_ms")==null)) {
            throw BusinessException.invalid("录像资产与文件偏移须同时提供");
        }
        if (result.get("media_asset_id")!=null) { uuid(result,"media_asset_id"); integer(result,"media_pts_ms",0,Long.MAX_VALUE); }
        Set<Long> indices=new HashSet<>(); Set<Long> localIds=new HashSet<>();
        for (Object item:list(required(result,"targets"))) {
            Map<String,Object> target=map(item);
            fields(target,"target_index","object_type","class_code","bbox","confidence","is_prediction","local_track_id");
            if (!indices.add(integer(target,"target_index",0,Integer.MAX_VALUE))) { throw BusinessException.invalid("同帧target_index重复"); }
            text(target,"object_type",64); text(target,"class_code",64);
            if (!(target.get("is_prediction") instanceof Boolean)) { throw BusinessException.invalid("is_prediction须为布尔值"); }
            List<Object> box=list(required(target,"bbox"));
            if (box.size()!=4) { throw BusinessException.invalid("bbox须为四项归一化xyxy"); }
            double left=unit(box.get(0)),top=unit(box.get(1)),right=unit(box.get(2)),bottom=unit(box.get(3));
            if (right<=left || bottom<=top) { throw BusinessException.invalid("bbox须有正面积"); }
            if (!Boolean.TRUE.equals(target.get("is_prediction")) || target.get("confidence")!=null) { unit(required(target,"confidence")); }
            if (tracking) {
                if (!localIds.add(integer(target,"local_track_id",0,Long.MAX_VALUE))) { throw BusinessException.invalid("同帧局部跟踪号重复"); }
            } else if (target.get("local_track_id")!=null) { throw BusinessException.invalid("局部跟踪号须提供跟踪上下文"); }
        }
    }

    private boolean saveFrame(JdbcTemplate jdbc,Map<String,Object> body,Map<String,Object> result,
                              Map<String,Object> session,String context,boolean uuidStream,List<Object> mappings) {
        validateFrame(result,context!=null);
        OffsetDateTime occurred=time(result,"occurred_at"),expires=occurred.plusDays(7);
        if (!expires.isAfter(OffsetDateTime.now())) { throw BusinessException.expired("输入帧已到期"); }
        if (occurred.isBefore(at(session.get("started_at"))) || (session.get("ended_at")!=null && !occurred.isBefore(at(session.get("ended_at"))))) {
            throw BusinessException.invalid("输入帧不在会话范围内");
        }
        String set=uuid(body,"result_set_id"),id=uuid(result,"result_id"),frameId=uuid(result,"frame_id"),digest=resultDigest(body,result);
        List<Map<String,Object>> old=jdbc.queryForList("SELECT id::text AS id,result_set_id::text AS set_id,payload_digest,expires_at FROM public.analysis_frame "+
                "WHERE id=?::uuid OR (result_set_id=?::uuid AND (producer_result_key=? OR input_frame_id=?::uuid))",
                id,set,text(result,"producer_result_key"),frameId);
        if (!old.isEmpty()) {
            if (old.size()!=1 || !set.equals(old.get(0).get("set_id")) || !id.equals(old.get(0).get("id")) || !digest.equals(old.get(0).get("payload_digest"))) {
                throw BusinessException.conflict("相同成果标识或生产键对应不同内容");
            }
            live(old.get(0),"expires_at"); collectMappings(jdbc,id,mappings); return true;
        }
        if (context!=null) {
            Map<String,Object> tracking=one(jdbc,"SELECT started_at,ended_at FROM public.tracking_context WHERE id=?::uuid",context);
            if (occurred.isBefore(at(tracking.get("started_at"))) ||
                    (tracking.get("ended_at")!=null && occurred.isAfter(at(tracking.get("ended_at"))))) {
                throw BusinessException.invalid("输入帧不在跟踪状态范围内");
            }
        }
        if (result.get("media_asset_id")!=null) {
            Map<String,Object> asset=one(jdbc,"SELECT source_id::text AS source,stream_session_id::text AS session,state,expires_at,duration_ms "+
                    "FROM public.media_asset WHERE id=?::uuid",uuid(result,"media_asset_id"));
            live(asset,"expires_at");
            if (!body.get("source_id").equals(asset.get("source")) || !body.get("stream_session_id").equals(asset.get("session")) ||
                    !"available".equals(asset.get("state")) || integer(result,"media_pts_ms",0,Long.MAX_VALUE)>=((Number)asset.get("duration_ms")).longValue()) {
                throw BusinessException.invalid("录像位置无效或未就绪");
            }
        }
        jdbc.update("INSERT INTO public.input_frame(id,stream_session_id,frame_seq,occurred_at,stream_pts_ms,media_asset_id,media_pts_ms,time_quality,width,height,expires_at) "+
                "VALUES (?::uuid,?::uuid,?,?,?,?::uuid,?,?,?,?,?) ON CONFLICT DO NOTHING",frameId,uuid(body,"stream_session_id"),
                integer(result,"frame_seq",0,Long.MAX_VALUE),occurred,result.get("stream_pts_ms"),result.get("media_asset_id"),result.get("media_pts_ms"),
                result.get("time_quality"),integer(result,"source_width",1,Integer.MAX_VALUE),integer(result,"source_height",1,Integer.MAX_VALUE),expires);
        Map<String,Object> frame=one(jdbc,"SELECT *,stream_session_id::text AS session FROM public.input_frame WHERE id=?::uuid FOR UPDATE",frameId);
        live(frame,"expires_at");
        if (!body.get("stream_session_id").equals(frame.get("session")) || ((Number)frame.get("frame_seq")).longValue()!=integer(result,"frame_seq",0,Long.MAX_VALUE) ||
                !occurred.isEqual(at(frame.get("occurred_at"))) || !numbersEqual(result.get("stream_pts_ms"),frame.get("stream_pts_ms")) ||
                ((Number)frame.get("width")).longValue()!=integer(result,"source_width",1,Integer.MAX_VALUE) ||
                ((Number)frame.get("height")).longValue()!=integer(result,"source_height",1,Integer.MAX_VALUE)) {
            throw BusinessException.conflict("公共帧引用对应不同输入");
        }
        if (result.get("media_asset_id")!=null && (!result.get("media_asset_id").equals(String.valueOf(frame.get("media_asset_id"))) ||
                !numbersEqual(result.get("media_pts_ms"),frame.get("media_pts_ms")))) {
            throw BusinessException.conflict("公共帧已有不同录像定位");
        }
        // Derive storage location without changing the producer payload or its immutable digest.
        RecordingService.alignFrame(jdbc,frame);
        List<Object> targets=list(result.get("targets"));
        jdbc.update("INSERT INTO public.analysis_frame(id,result_set_id,input_frame_id,producer_result_key,schema_version,target_count,payload_digest,expires_at) "+
                "VALUES (?::uuid,?::uuid,?::uuid,?,?,?,?,?)",id,set,frameId,text(result,"producer_result_key"),text(body,"schema_version",32),targets.size(),digest,expires);
        for (Object item:targets) {
            Map<String,Object> target=map(item); List<Object> box=list(target.get("bbox"));
            String track=context==null?null:tracklet(jdbc,body,target,result,session,context,uuidStream,expires);
            jdbc.update("INSERT INTO public.detection_observation(analysis_frame_id,target_index,tracklet_id,object_type,class_code,confidence,observation_kind,"+
                    "bbox_left,bbox_top,bbox_right,bbox_bottom,expires_at) VALUES (?::uuid,?,?::uuid,?,?,?,?,?,?,?,?,?)",id,
                    integer(target,"target_index",0,Integer.MAX_VALUE),track,target.get("object_type"),target.get("class_code"),target.get("confidence"),
                    Boolean.TRUE.equals(target.get("is_prediction"))?"predicted":"observed",unit(box.get(0)),unit(box.get(1)),unit(box.get(2)),unit(box.get(3)),expires);
        }
        collectMappings(jdbc,id,mappings); return false;
    }

    private String tracklet(JdbcTemplate jdbc,Map<String,Object> body,Map<String,Object> target,Map<String,Object> result,
                            Map<String,Object> session,String context,boolean uuidStream,OffsetDateTime expires) {
        OffsetDateTime occurred=time(result,"occurred_at");
        boolean observed=!Boolean.TRUE.equals(target.get("is_prediction"));
        String id=UUID.randomUUID().toString(); long local=integer(target,"local_track_id",0,Long.MAX_VALUE);
        String stream=uuidStream?String.valueOf(session.get("camera_stream_id")):String.valueOf(session.get("stream_name"));
        jdbc.update("INSERT INTO public.tracklet(id,stream_id,start_ts,cls_name,source_id,stream_session_id,tracking_context_id,local_track_id,"+
                "origin_result_set_id,first_observed_at,last_observed_at,expires_at) VALUES (?::uuid,"+(uuidStream?"?::uuid":"?")+
                ",?,?,?::uuid,?::uuid,?::uuid,?,?::uuid,?,?,?) ON CONFLICT (tracking_context_id,local_track_id) WHERE tracking_context_id IS NOT NULL DO NOTHING",
                id,stream,occurred,text(target,"class_code",64),uuid(body,"source_id"),uuid(body,"stream_session_id"),context,local,
                uuid(body,"result_set_id"),observed?occurred:null,observed?occurred:null,expires);
        Map<String,Object> track=one(jdbc,"SELECT id::text AS id,cls_name FROM public.tracklet WHERE tracking_context_id=?::uuid AND local_track_id=? FOR UPDATE",context,local);
        id=track.get("id").toString();
        jdbc.update("UPDATE public.tracklet SET start_ts=LEAST(start_ts,?),expires_at=GREATEST(expires_at,?),revision=revision+1,updated_at=now() "+
                "WHERE id=?::uuid",occurred,expires,id);
        if (observed) {
            jdbc.update("UPDATE public.tracklet SET first_observed_at=LEAST(first_observed_at,?),last_observed_at=GREATEST(last_observed_at,?) WHERE id=?::uuid",occurred,occurred,id);
            refreshIdentity(jdbc,id);
        }
        return id;
    }

    private void refreshIdentity(JdbcTemplate jdbc,String track){
        if(identitySchema==null){identitySchema=Boolean.TRUE.equals(jdbc.queryForObject("SELECT to_regclass('public.track_identity_assignment') IS NOT NULL",Boolean.class));}
        if(!identitySchema){return;}
        // Only a real saved observation extends current identity relationships.
        jdbc.update("UPDATE public.track_identity_assignment a SET expires_at=GREATEST(a.expires_at,t.last_observed_at+interval '7 days') FROM public.tracklet t WHERE a.tracklet_id=t.id AND t.id=?::uuid AND a.valid_to IS NULL AND a.expires_at>now()",track);
        jdbc.update("UPDATE public.identity i SET first_seen_at=LEAST(i.first_seen_at,t.first_observed_at),last_seen_at=GREATEST(i.last_seen_at,t.last_observed_at),expires_at=GREATEST(i.expires_at,t.last_observed_at+interval '7 days'),revision=i.revision+1,updated_at=now() FROM public.track_identity_assignment a,public.tracklet t WHERE a.tracklet_id=t.id AND t.id=?::uuid AND a.identity_id=i.id AND a.valid_to IS NULL AND a.expires_at>now() AND i.identity_kind='temporary' AND i.enabled AND i.expires_at>now() AND (i.first_seen_at IS NULL OR i.last_seen_at IS NULL OR t.first_observed_at<i.first_seen_at OR t.last_observed_at>i.last_seen_at)",track);
        jdbc.update("UPDATE public.identity_link l SET expires_at=GREATEST(l.expires_at,i.expires_at) FROM public.identity i,public.track_identity_assignment a WHERE a.tracklet_id=?::uuid AND a.identity_id=i.id AND l.temporary_identity_id=i.id AND a.valid_to IS NULL AND a.expires_at>now() AND l.valid_to IS NULL AND l.expires_at>now() AND i.enabled AND i.expires_at>now()",track);
        jdbc.update("UPDATE public.episode e SET start_ts=LEAST(e.start_ts,t.first_observed_at),end_ts=GREATEST(e.end_ts,t.last_observed_at),expires_at=GREATEST(e.end_ts,t.last_observed_at)+interval '7 days',revision=e.revision+1 FROM public.episode_tracklet_link l,public.tracklet t WHERE l.episode_id=e.id AND l.tracklet_id=t.id AND t.id=?::uuid AND e.activity_type='person_activity' AND e.state='open' AND e.expires_at>now() AND (t.first_observed_at<e.start_ts OR t.last_observed_at>e.end_ts)",track);
    }

    private boolean saveTyped(JdbcTemplate jdbc,Map<String,Object> body,Map<String,Object> result,Map<String,Object> type) {
        fields(result,"result_id","producer_result_key","frame_id","tracklet_id","start_at","end_at","payload","payload_asset_id");
        String id=uuid(result,"result_id"),set=uuid(body,"result_set_id"); text(result,"producer_result_key");
        OffsetDateTime start=time(result,"start_at"),end=result.get("end_at")==null?start:time(result,"end_at"),expires=end.plusDays(7);
        if (end.isBefore(start)) { throw BusinessException.invalid("成果结束时间早于开始时间"); }
        if (!expires.isAfter(OffsetDateTime.now())) { throw BusinessException.expired("算法成果已到期"); }
        Map<String,Object> payload=map(required(result,"payload"));
        String encoded=json(payload);
        if (encoded.getBytes(StandardCharsets.UTF_8).length>((Number)type.get("max_inline_bytes")).intValue()) {
            throw BusinessException.invalid("成果超过内嵌载荷上限");
        }
        BusinessSchemas.validate(parse(type.get("json_schema").toString()),payload);
        Map<String,Object> asset=null;
        if (result.get("payload_asset_id")!=null) {
            asset=one(jdbc,"SELECT state,checksum_sha256,expires_at FROM public.media_asset "+
                    "WHERE id=?::uuid AND source_id=?::uuid AND stream_session_id=?::uuid FOR UPDATE",
                    uuid(result,"payload_asset_id"),uuid(body,"source_id"),uuid(body,"stream_session_id"));
        }
        String digest=resultDigest(body,result,asset==null?null:String.valueOf(asset.get("checksum_sha256")).trim());
        List<Map<String,Object>> old=jdbc.queryForList("SELECT id::text AS id,result_set_id::text AS set_id,payload_digest,expires_at FROM public.algorithm_result "+
                "WHERE id=?::uuid OR (result_set_id=?::uuid AND producer_result_key=?)",id,set,text(result,"producer_result_key"));
        if (!old.isEmpty()) {
            if (old.size()!=1 || !set.equals(old.get(0).get("set_id")) || !id.equals(old.get(0).get("id")) || !digest.equals(old.get(0).get("payload_digest"))) {
                throw BusinessException.conflict("相同成果标识或生产键对应不同内容");
            }
            live(old.get(0),"expires_at"); return true;
        }
        for (String reference:java.util.Arrays.asList("frame_id","tracklet_id","payload_asset_id")) {
            if (result.get(reference)!=null) { uuid(result,reference); }
        }
        if (result.get("frame_id")!=null) {
            one(jdbc,"SELECT id FROM public.input_frame WHERE id=?::uuid AND stream_session_id=?::uuid AND expires_at>now()",uuid(result,"frame_id"),uuid(body,"stream_session_id"));
        }
        if (result.get("tracklet_id")!=null) {
            one(jdbc,"SELECT id FROM public.tracklet WHERE id=?::uuid AND source_id=?::uuid AND stream_session_id=?::uuid AND expires_at>now()",
                    uuid(result,"tracklet_id"),uuid(body,"source_id"),uuid(body,"stream_session_id"));
        }
        if (asset!=null && (!"available".equals(asset.get("state")) || asset.get("checksum_sha256")==null ||
                at(asset.get("expires_at")).isBefore(expires))) {
            throw BusinessException.invalid("外置成果资产须已就绪，且有效期限覆盖成果期限");
        }
        jdbc.update("INSERT INTO public.algorithm_result(id,result_set_id,producer_result_key,result_type,schema_version,input_frame_id,tracklet_id,start_at,end_at,payload_json,"+
                "payload_asset_id,payload_digest,expires_at) VALUES (?::uuid,?::uuid,?,?,?,?::uuid,?::uuid,?,?,?::jsonb,?::uuid,?,?)",id,set,
                text(result,"producer_result_key"),text(body,"result_type",64),text(body,"schema_version",32),result.get("frame_id"),result.get("tracklet_id"),
                start,result.get("end_at")==null?null:end,encoded,result.get("payload_asset_id"),digest,expires);
        if (result.get("payload_asset_id")!=null) {
            jdbc.update("INSERT INTO public.asset_reference(asset_id,result_id,retain_until) VALUES (?::uuid,?::uuid,?)",uuid(result,"payload_asset_id"),id,expires);
        }
        return false;
    }

    private Map<String,Object> saveCoverage(JdbcTemplate jdbc,Map<String,Object> body,Map<String,Object> coverage,
                                            boolean noRejected,long generation,boolean current,List<Object> requestedOutputs) {
        String source=uuid(body,"source_id"),set=uuid(body,"result_set_id");
        boolean frameType="detection.frame".equals(body.get("result_type"));
        List<Object> manifest=list(coverage.get(frameType?"frame_ids":"result_ids"));
        List<String> saved=new ArrayList<>();
        for (Object reference:manifest) {
            String id=uuid(reference,"manifest");
            Object[] parameters=frameType?new Object[]{set,id,text(body,"schema_version",32)}:
                    new Object[]{set,id,text(body,"result_type",64),text(body,"schema_version",32)};
            List<String> found=jdbc.queryForList(frameType?
                    "SELECT input_frame_id::text FROM public.analysis_frame WHERE result_set_id=?::uuid AND input_frame_id=?::uuid AND schema_version=? AND expires_at>now()":
                    "SELECT id::text FROM public.algorithm_result WHERE result_set_id=?::uuid AND id=?::uuid AND result_type=? AND schema_version=? AND expires_at>now()",
                    String.class,parameters);
            if (!found.isEmpty()) { saved.add(id); }
        }
        boolean complete=Boolean.TRUE.equals(coverage.get("closed")) && noRejected && saved.size()==manifest.size()
                && (!frameType || !manifest.isEmpty()) && list(coverage.get("gaps")).isEmpty();
        OffsetDateTime start=time(coverage,"start_at"),end=time(coverage,"end_at"),expires=end.plusDays(7);
        String key="set:"+set+":"+BusinessCanonical.digest(values("start",iso(start),"end",iso(end),
                "result_type",body.get("result_type"),"schema_version",body.get("schema_version"))).substring(0,32);
        Map<String,Object> declaration=values("result_type",body.get("result_type"),"schema_version",body.get("schema_version"),
                "frame_ids",coverage.get("frame_ids"),"result_ids",coverage.get("result_ids"),"gaps",coverage.get("gaps"));
        for (String stage:java.util.Arrays.asList("analysis","registration")) {
            List<Map<String,Object>> previous=jdbc.queryForList("SELECT closed,frame_manifest_json::text AS manifest FROM public.processing_coverage "+
                    "WHERE source_id=?::uuid AND stage=? AND coverage_key=? FOR UPDATE",source,stage,key);
            if (!previous.isEmpty()) {
                Map<String,Object> recorded=parse(previous.get(0).get("manifest").toString());
                Object oldManifest=recorded.get(frameType?"frame_ids":"result_ids");
                if ((oldManifest!=null && !manifest.containsAll(list(oldManifest))) ||
                        (Boolean.TRUE.equals(previous.get(0).get("closed")) && !Boolean.TRUE.equals(coverage.get("closed")))) {
                    throw BusinessException.conflict("已登记的覆盖清单不能减少，闭合窗口不能重新打开");
                }
            }
            Map<String,Object> manifestRecord=new LinkedHashMap<>(declaration); manifestRecord.put("saved_ids",saved);
            jdbc.update("INSERT INTO public.processing_coverage(source_id,stream_session_id,run_id,result_set_id,stage,coverage_key,closed,start_at,end_at,status,"+
                    "analyzed_frame_count,saved_frame_count,frame_manifest_json,reason_code,expires_at) VALUES (?::uuid,?::uuid,?::uuid,?::uuid,?,?,?,?,?,?,?,?,?::jsonb,?,?) "+
                    "ON CONFLICT (source_id,stage,coverage_key) DO UPDATE SET closed=EXCLUDED.closed,status=EXCLUDED.status,analyzed_frame_count=EXCLUDED.analyzed_frame_count,"+
                    "saved_frame_count=EXCLUDED.saved_frame_count,frame_manifest_json=EXCLUDED.frame_manifest_json,reason_code=EXCLUDED.reason_code,revision=processing_coverage.revision+1",
                    source,uuid(body,"stream_session_id"),uuid(body,"run_id"),set,stage,key,coverage.get("closed"),start,end,
                    complete?"complete":"partial",frameType?manifest.size():0,frameType?saved.size():0,json(manifestRecord),complete?null:"RESULTS_PENDING",expires);
        }
        boolean allOutputs=complete;
        for (Object output:requestedOutputs) {
            if (!allOutputs) { break; }
            allOutputs=Boolean.TRUE.equals(jdbc.queryForObject("SELECT tstzrange(?,?,'[)') <@ COALESCE(range_agg(tstzrange(start_at,end_at,'[)')), '{}'::tstzmultirange) "+
                    "FROM public.processing_coverage WHERE result_set_id=?::uuid AND stage='registration' AND status='complete' AND closed "+
                    "AND expires_at>now() AND frame_manifest_json->>'result_type'=?",Boolean.class,start,end,set,String.valueOf(output)));
        }
        if (allOutputs && current) { adoptUnselected(jdbc,source,text(body,"capability_code",64),set,generation,start,end,expires); }
        if (allOutputs) { jdbc.update("UPDATE public.result_set SET state='ready' WHERE id=?::uuid",set); }
        List<Object> done=new ArrayList<>(),gaps=new ArrayList<>();
        if (complete) { done.add(values("source_id",source,"stage","registration","start_at",iso(start),"end_at",iso(end))); }
        else { gaps.add(values("source_id",source,"stage","registration","start_at",iso(start),"end_at",iso(end),"reason_code","RESULTS_PENDING")); }
        return values("schema_version","1","completed",done,"gaps",gaps);
    }

    private void adoptUnselected(JdbcTemplate jdbc,String source,String capability,String set,long generation,
                                 OffsetDateTime start,OffsetDateTime end,OffsetDateTime expires) {
        jdbc.queryForObject("SELECT pg_advisory_xact_lock(hashtextextended(?,0)) IS NULL",Boolean.class,"selection:"+source+":"+capability);
        List<Map<String,Object>> selections=jdbc.queryForList("SELECT range_start,range_end FROM public.result_selection WHERE source_id=?::uuid "+
                "AND capability_code=? AND range_start<? AND range_end>? ORDER BY range_start FOR UPDATE",source,capability,end,start);
        OffsetDateTime cursor=start;
        for (Map<String,Object> selection:selections) {
            OffsetDateTime selectedStart=at(selection.get("range_start")),selectedEnd=at(selection.get("range_end"));
            if (selectedStart.isAfter(cursor)) { insertSelection(jdbc,source,capability,set,generation,cursor,selectedStart.isBefore(end)?selectedStart:end,expires); }
            if (selectedEnd.isAfter(cursor)) { cursor=selectedEnd; }
            if (!cursor.isBefore(end)) { break; }
        }
        if (cursor.isBefore(end)) { insertSelection(jdbc,source,capability,set,generation,cursor,end,expires); }
    }
    private void insertSelection(JdbcTemplate jdbc,String source,String capability,String set,long generation,OffsetDateTime start,OffsetDateTime end,OffsetDateTime expires) {
        jdbc.update("INSERT INTO public.result_selection(source_id,capability_code,range_start,range_end,result_set_id,generation,expires_at) VALUES (?::uuid,?,?,?,?::uuid,?,?)",
                source,capability,start,end,set,generation,expires);
    }
    private static void collectMappings(JdbcTemplate jdbc,String result,List<Object> mappings) {
        mappings.addAll(jdbc.queryForList("SELECT DISTINCT t.tracking_context_id::text,t.local_track_id,t.id::text AS tracklet_id "+
                "FROM public.detection_observation d JOIN public.tracklet t ON t.id=d.tracklet_id WHERE d.analysis_frame_id=?::uuid",result));
    }
    private static long nextEventRevision(JdbcTemplate jdbc,String set) {
        return jdbc.queryForObject("SELECT COALESCE(MAX(aggregate_revision),0)+1 FROM public.outbox_event WHERE event_type='results.registered' AND aggregate_type='result_set' AND aggregate_id=?::uuid",Long.class,set);
    }
    private static void validateCoverage(Map<String,Object> coverage,List<Object> results,boolean frameType) {
        fields(coverage,"start_at","end_at","closed","analyzed_frame_count","frame_ids","result_ids","gaps");
        OffsetDateTime start=time(coverage,"start_at"),end=time(coverage,"end_at");
        if (!end.isAfter(start) || !(coverage.get("closed") instanceof Boolean)) { throw BusinessException.invalid("分析范围或closed无效"); }
        List<Object> frames=list(required(coverage,"frame_ids")),ids=frameType?frames:list(required(coverage,"result_ids"));
        if (integer(coverage,"analyzed_frame_count",0,Long.MAX_VALUE)!=frames.size()) { throw BusinessException.invalid("分析帧数须等于实际帧清单"); }
        Set<String> unique=new HashSet<>();
        for (Object id:ids) { if (!unique.add(uuid(id,"manifest"))) { throw BusinessException.invalid("成果清单标识重复"); } }
        for (Object item:results) {
            Map<String,Object> result=map(item);
            if (!unique.contains(uuid(result,frameType?"frame_id":"result_id"))) { throw BusinessException.invalid("本批成果不在分析清单内"); }
            OffsetDateTime occurred=time(result,frameType?"occurred_at":"start_at");
            if (occurred.isBefore(start) || !occurred.isBefore(end)) { throw BusinessException.invalid("成果时间不在分析范围内"); }
        }
        for (Object item:list(required(coverage,"gaps"))) {
            Map<String,Object> gap=map(item); fields(gap,"start_at","end_at","reason_code"); text(gap,"reason_code",64);
            OffsetDateTime left=time(gap,"start_at"),right=time(gap,"end_at");
            if (left.isBefore(start) || right.isAfter(end) || !right.isAfter(left)) { throw BusinessException.invalid("分析缺口范围无效"); }
        }
    }
    private static Map<String,Object> one(JdbcTemplate jdbc,String sql,Object... args) {
        List<Map<String,Object>> rows=jdbc.queryForList(sql,args);
        if (rows.size()!=1) { throw BusinessException.notFound("引用对象不存在或不在有效范围内"); }
        return rows.get(0);
    }
    private static void live(Map<String,Object> row,String key) {
        if (row.get(key)==null || !at(row.get(key)).isAfter(OffsetDateTime.now())) { throw BusinessException.expired("引用对象已到期"); }
    }
    private static OffsetDateTime at(Object value) {
        if (value instanceof OffsetDateTime) { return (OffsetDateTime)value; }
        if (value instanceof Timestamp) { return ((Timestamp)value).toInstant().atOffset(ZoneOffset.UTC); }
        throw BusinessException.conflict("存储时间类型不匹配");
    }
    private static String resultDigest(Map<String,Object> body,Map<String,Object> result) {
        return resultDigest(body,result,null);
    }
    private static String resultDigest(Map<String,Object> body,Map<String,Object> result,String assetChecksum) {
        Map<String,Object> content=values("result_type",body.get("result_type"),"schema_version",body.get("schema_version"),
                "tracking_context_id",body.get("tracking_context_id"),"result",result);
        if (assetChecksum!=null) { content.put("payload_asset_sha256",assetChecksum); }
        return BusinessCanonical.digest(content);
    }
    private static boolean numbersEqual(Object left,Object right) {
        return left==null?right==null:right instanceof Number && new BigDecimal(left.toString()).compareTo(new BigDecimal(right.toString()))==0;
    }
    private static double unit(Object value) {
        if (!(value instanceof Number)) { throw BusinessException.invalid("坐标与置信度须为数值"); }
        double number=((Number)value).doubleValue();
        if (!Double.isFinite(number) || number<0 || number>1) { throw BusinessException.invalid("坐标与置信度须在[0,1]"); }
        return number;
    }
}
