package edu.cqupt.hxjm.algdeployment.business.security;

import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.service.ResultRegistrationService;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessStore;

/** Execute production registration SQL against an explicitly opted-in synthetic test database. */
public final class BusinessResultPipelineCheck {
    public static void main(String[] args) {
        String url=System.getenv("HXJM_TEST_JDBC_URL");
        if (!"1".equals(System.getenv("HXJM_ISOLATED_TEST")) || url==null ||
                !url.matches("jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/hxjm_stage1_[a-z0-9_]+")) {
            throw new IllegalArgumentException("An explicitly opted-in isolated database is required");
        }
        BusinessStore store=new BusinessStore(new DriverManagerDataSource(url,System.getenv("HXJM_TEST_DB_USER"),System.getenv("HXJM_TEST_DB_PASSWORD")));
        ResultRegistrationService service=new ResultRegistrationService(store);
        String source=id(),stream=id(),session=id(),task=id(),run=id(),set=id(),context=id();
        String capability="tracking_"+UUID.randomUUID().toString().replace("-","");
        OffsetDateTime now=OffsetDateTime.now(ZoneOffset.UTC).withNano(0),expires=now.plusDays(7);
        BusinessSecurityProperties.Grant grant=new BusinessSecurityProperties.Grant();
        grant.setOperations(new HashSet<>(Collections.singletonList("results.register"))); grant.setSourceIds(Collections.singleton(source));
        BusinessActor actor=new BusinessActor("service:fixture-results",null,"fixture-results",grant);
        store.jdbc().update("INSERT INTO public.camera(id,camera_code,name) VALUES (?::uuid,?,?)",source,"result-"+source,"synthetic result camera");
        store.jdbc().update("INSERT INTO public.camera_stream(id,camera_id,stream_name,task_type) VALUES (?::uuid,?::uuid,?,'track')",stream,source,"live/"+source);
        store.jdbc().update("INSERT INTO public.stream_session(id,source_id,camera_stream_id,session_key,started_at,time_origin_at,time_basis,source_timezone,source_width,source_height,expires_at) VALUES (?::uuid,?::uuid,?::uuid,?,?,?,'ingest_clock','UTC',1920,1080,?)",session,source,stream,"session:"+session,now,now,expires);
        store.jdbc().update("INSERT INTO public.capability_definition(capability_code,display_name,object_types,input_kinds) VALUES (?,?,'{person}','{live_video}')",capability,"fixture tracking");
        store.jdbc().update("INSERT INTO public.result_type(type_code,schema_version) VALUES ('detection.frame','1') ON CONFLICT DO NOTHING");
        Map<String,Object> snapshot=values("input",values("kind","live_video","source_id",source,"stream_session_id",session),"requested_outputs",Collections.singletonList("detection.frame"));
        store.jdbc().update("INSERT INTO public.business_task(task_id,task_kind,task_mode,actor_key,capability_code,state,input_json,input_digest,expires_at) VALUES (?::uuid,'tracking','continuous',?,?,'running',?::jsonb,?,?)",task,actor.getActorKey(),capability,json(snapshot),String.join("",Collections.nCopies(64,"a")),expires);
        store.jdbc().update("INSERT INTO public.task_attempt(run_id,task_id,generation,state,implementation_code,implementation_version,lease_owner,started_at,expires_at) VALUES (?::uuid,?::uuid,1,'running','fixture','1',?,?,?)",run,task,actor.getActorKey(),now,expires);
        store.jdbc().update("UPDATE public.business_task SET current_run_id=?::uuid,generation=1 WHERE task_id=?::uuid",run,task);
        List<Object> targets=new ArrayList<>();
        targets.add(values("target_index",0,"object_type","person","class_code","person","bbox",Arrays.asList(.1,.2,.5,.9),"confidence",.9,"is_prediction",false,"local_track_id",7));
        targets.add(values("target_index",1,"object_type","person","class_code","person","bbox",Arrays.asList(.6,.2,.8,.9),"confidence",null,"is_prediction",true,"local_track_id",8));
        Map<String,Object> first=frame(now.plusSeconds(1),1,targets),empty=frame(now.plusSeconds(2),2,Collections.emptyList());
        Map<String,Object> body=values("request_id",id(),"task_id",task,"run_id",run,"result_set_id",set,"set_key","tracking","capability_code",capability,
                "result_type","detection.frame","schema_version","1","source_id",source,"stream_session_id",session,"tracking_context_id",context,
                "tracking_context",values("context_key","tracker:1","started_at",iso(now)),"processed_at",iso(now.plusSeconds(3)),
                "results",Arrays.asList(first,empty),"analysis_coverage",values("start_at",iso(now),"end_at",iso(now.plusSeconds(3)),
                        "closed",true,"analyzed_frame_count",2,"frame_ids",Arrays.asList(first.get("frame_id"),empty.get("frame_id")),"gaps",Collections.emptyList()));
        Map<String,Object> saved=service.register(actor,body);
        check(list(saved.get("accepted_result_ids")).size()==2,"two complete frames");
        check(store.jdbc().queryForObject("SELECT count(*) FROM public.detection_observation WHERE analysis_frame_id=?::uuid",Long.class,first.get("result_id"))==2,"all targets persisted");
        check(store.jdbc().queryForObject("SELECT target_count FROM public.analysis_frame WHERE id=?::uuid",Integer.class,empty.get("result_id"))==0,"zero-target frame retained");
        check(store.jdbc().queryForObject("SELECT last_observed_at IS NULL FROM public.tracklet WHERE tracking_context_id=?::uuid AND local_track_id=8",Boolean.class,context),"prediction does not refresh person observation");
        check(store.jdbc().queryForObject("SELECT count(*) FROM public.result_selection WHERE result_set_id=?::uuid",Long.class,set)==1,"closed saved range adopted");
        check(Boolean.TRUE.equals(service.register(actor,body).get("duplicate")),"immutable request replay");
        Map<String,Object> another=parse(json(body)); another.put("request_id",id());
        check(list(service.register(actor,another).get("duplicate_result_ids")).size()==2,"new request reuses immutable results");
        Map<String,Object> changed=parse(json(body)); changed.put("processed_at",iso(now.plusSeconds(4)));
        fails(409,()->service.register(actor,changed));
        Map<String,Object> badFrame=frame(now.plusSeconds(4),3,Arrays.asList(values("target_index",0,"object_type","person","class_code","person","bbox",Arrays.asList(.9,.2,.1,.8),"confidence",.9,"is_prediction",false,"local_track_id",7)));
        Map<String,Object> bad=parse(json(body)); bad.put("request_id",id()); bad.put("results",Collections.singletonList(badFrame));
        bad.put("analysis_coverage",values("start_at",iso(now.plusSeconds(4)),"end_at",iso(now.plusSeconds(5)),"closed",true,
                "analyzed_frame_count",1,"frame_ids",Collections.singletonList(badFrame.get("frame_id")),"gaps",Collections.emptyList()));
        Map<String,Object> rejected=service.register(actor,bad);
        check(list(rejected.get("rejected_results")).size()==1,"invalid frame rejected individually");
        check(store.jdbc().queryForObject("SELECT count(*) FROM public.analysis_frame WHERE id=?::uuid",Long.class,badFrame.get("result_id"))==0,"no partial analysis frame");
        check(store.jdbc().queryForObject("SELECT count(*) FROM public.input_frame WHERE id=?::uuid",Long.class,badFrame.get("frame_id"))==0,"no orphan input frame");
        String nextContext=id(); Map<String,Object> nextFrame=frame(now.plusSeconds(6),4,Collections.singletonList(targets.get(0)));
        Map<String,Object> restarted=parse(json(body)); restarted.put("request_id",id()); restarted.put("tracking_context_id",nextContext);
        restarted.put("tracking_context",values("context_key","tracker:2","started_at",iso(now.plusSeconds(6)),"reset_reason","worker_restart"));
        restarted.put("results",Collections.singletonList(nextFrame));
        restarted.put("analysis_coverage",values("start_at",iso(now.plusSeconds(6)),"end_at",iso(now.plusSeconds(7)),"closed",true,
                "analyzed_frame_count",1,"frame_ids",Collections.singletonList(nextFrame.get("frame_id")),"gaps",Collections.emptyList()));
        service.register(actor,restarted);
        check(store.jdbc().queryForObject("SELECT count(*) FROM public.tracklet WHERE source_id=?::uuid AND local_track_id=7",Long.class,source)==2,"local number reuse is scoped to tracker");
        checkMultipleOutputs(store,service,actor,body,now,source,stream,session);
        System.out.println("BusinessResultPipelineCheck passed: production registration, complete/zero frames, predictions, dedup, atomic rejection, tracker resets and multiple outputs.");
    }
    private static void checkMultipleOutputs(BusinessStore store,ResultRegistrationService service,BusinessActor actor,
            Map<String,Object> original,OffsetDateTime now,String source,String stream,String session) {
        String type="fixture.metric",asset=id(),set=id();
        store.jdbc().update("INSERT INTO public.result_type(type_code,schema_version) VALUES (?,'1') ON CONFLICT DO NOTHING",type);
        store.jdbc().update("UPDATE public.business_task SET input_json=jsonb_set(input_json,'{requested_outputs}',?::jsonb) WHERE task_id=?::uuid",
                json(Arrays.asList("detection.frame",type)),original.get("task_id"));
        Map<String,Object> batch=parse(json(original)),frame=frame(now.plusSeconds(8),5,Collections.emptyList());
        batch.put("request_id",id()); batch.put("result_set_id",set); batch.put("set_key","multiple-outputs");
        batch.put("results",Collections.singletonList(frame));
        batch.put("analysis_coverage",values("start_at",iso(now.plusSeconds(8)),"end_at",iso(now.plusSeconds(9)),
                "closed",true,"analyzed_frame_count",1,"frame_ids",Collections.singletonList(frame.get("frame_id")),"gaps",Collections.emptyList()));
        service.register(actor,batch);
        check(store.jdbc().queryForObject("SELECT count(*) FROM public.result_selection WHERE result_set_id=?::uuid",Long.class,set)==0,"wait for other requested output");
        boolean uuidStream=Boolean.TRUE.equals(store.jdbc().queryForObject("SELECT atttypid='uuid'::regtype FROM pg_attribute WHERE attrelid='public.media_asset'::regclass AND attname='stream_id'",Boolean.class));
        OffsetDateTime end=now.plusSeconds(9),expires=end.plusDays(7);
        String checksum=String.join("",Collections.nCopies(64,"b"));
        store.jdbc().update("INSERT INTO public.media_asset(id,stream_id,asset_type,start_ts,duration_ms,source_id,stream_session_id,state,checksum_sha256,expires_at) "+
                "VALUES (?::uuid,"+(uuidStream?"?::uuid":"?")+",'algorithm_output',?,1000,?::uuid,?::uuid,'available',?,?)",
                asset,uuidStream?stream:"live/"+source,now.plusSeconds(8),source,session,checksum,expires.minusSeconds(1));
        Map<String,Object> typed=values("result_id",id(),"producer_result_key","metric:1","start_at",iso(now.plusSeconds(8)),
                "end_at",iso(end),"payload",values("count",0),"payload_asset_id",asset);
        Map<String,Object> output=parse(json(batch)); output.put("request_id",id()); output.put("result_type",type);
        output.remove("tracking_context_id"); output.remove("tracking_context"); output.put("results",Collections.singletonList(typed));
        output.put("analysis_coverage",values("start_at",iso(now.plusSeconds(8)),"end_at",iso(end),"closed",true,
                "analyzed_frame_count",0,"frame_ids",Collections.emptyList(),"result_ids",Collections.singletonList(typed.get("result_id")),"gaps",Collections.emptyList()));
        check(list(service.register(actor,output).get("rejected_results")).size()==1,"asset lifetime must cover result");
        store.jdbc().update("UPDATE public.media_asset SET expires_at=? WHERE id=?::uuid",expires,asset);
        output.put("request_id",id());
        check(list(service.register(actor,output).get("accepted_result_ids")).size()==1,"typed result accepted");
        check(store.jdbc().queryForObject("SELECT count(*) FROM public.asset_reference WHERE asset_id=?::uuid",Long.class,asset)==1,"asset reference saved atomically");
        check(store.jdbc().queryForObject("SELECT count(*) FROM public.result_selection WHERE result_set_id=?::uuid",Long.class,set)==1,"all output types complete before adoption");
        Map<String,Object> digest=values("result_type",type,"schema_version","1","tracking_context_id",null,"result",typed,"payload_asset_sha256",checksum);
        check(edu.cqupt.hxjm.algdeployment.business.store.BusinessCanonical.digest(digest).equals(store.jdbc().queryForObject(
                "SELECT payload_digest FROM public.algorithm_result WHERE id=?::uuid",String.class,typed.get("result_id"))),"external checksum in immutable result digest");
        String otherType="fixture.other_metric";
        store.jdbc().update("INSERT INTO public.result_type(type_code,schema_version) VALUES (?,'1') ON CONFLICT DO NOTHING",otherType);
        store.jdbc().update("UPDATE public.business_task SET input_json=jsonb_set(input_json,'{requested_outputs}',?::jsonb) WHERE task_id=?::uuid",
                json(Arrays.asList("detection.frame",type,otherType)),original.get("task_id"));
        Map<String,Object> wrongType=parse(json(output)); wrongType.put("request_id",id()); wrongType.put("result_type",otherType);
        wrongType.put("results",Collections.emptyList());
        Map<String,Object> confirmation=service.register(actor,wrongType);
        check(list(map(confirmation.get("coverage")).get("completed")).isEmpty(),"other type cannot borrow a saved result ID");
    }
    private static Map<String,Object> frame(OffsetDateTime at,int sequence,List<Object> targets) {
        return values("result_id",id(),"producer_result_key","frame:"+sequence,"frame_id",id(),"frame_seq",sequence,"occurred_at",iso(at),
                "stream_pts_ms",sequence*1000,"time_quality","ingest_estimated","source_width",1920,"source_height",1080,"targets",targets);
    }
    private static String id(){return UUID.randomUUID().toString();}
    private static void check(boolean value,String message){if(!value){throw new AssertionError(message);}}
    private static void fails(int status,Runnable work){try{work.run();throw new AssertionError("Expected "+status);}catch(BusinessException expected){check(expected.getStatus()==status,"Expected error status");}}
}
