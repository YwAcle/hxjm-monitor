package edu.cqupt.hxjm.algdeployment.business.service;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessCanonical;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;
import static edu.cqupt.hxjm.algdeployment.business.service.BusinessDataAccess.*;

/** Local factual route reports; no model call or inferred surveillance fact. */
@Service
@ConditionalOnProperty(prefix="hxjm.business",name="enabled",havingValue="true")
public class LocalActivityReportService {
    private static final Logger log=LoggerFactory.getLogger(LocalActivityReportService.class);
    private static final String GENERATOR="local_structured_v1";
    private final BusinessDataAccess data;
    private final TransactionTemplate transaction;
    @Value("${hxjm.business.local-reports.enabled:true}")
    private boolean enabled=true;
    @Value("${hxjm.business.local-reports.inactivity-seconds:60}")
    private long inactivitySeconds=60;

    public LocalActivityReportService(BusinessDataAccess data){
        this.data=data;
        this.transaction=new TransactionTemplate(new DataSourceTransactionManager(data.store().jdbc().getDataSource()));
    }

    @Scheduled(fixedDelayString="${hxjm.business.local-reports.poll-ms:5000}")
    public void poll(){
        if(!enabled){return;}
        try{refresh(inactivitySeconds,OffsetDateTime.now());}
        catch(RuntimeException failure){log.warn("Local activity report refresh failed: {}",failure.getClass().getSimpleName());}
    }

    public int refresh(long idleSeconds,OffsetDateTime now){
        if(idleSeconds<=0){throw new IllegalArgumentException("Activity inactivity must be positive");}
        int updated=0;
        for(Map<String,Object> row:data.store().jdbc().queryForList("SELECT id::text FROM public.episode WHERE identity_id IS NOT NULL AND activity_type='person_activity' AND expires_at>? ORDER BY end_ts,id",now)){
            Boolean changed=transaction.execute(status->refreshOne(row.get("id").toString(),idleSeconds,now));
            if(Boolean.TRUE.equals(changed)){updated++;}
        }
        return updated;
    }

    private boolean refreshOne(String id,long idleSeconds,OffsetDateTime now){
        JdbcTemplate jdbc=data.store().jdbc();
        List<Map<String,Object>> found=jdbc.queryForList("SELECT * FROM public.episode WHERE id=?::uuid AND expires_at>? FOR UPDATE",id,now);
        if(found.isEmpty()){return false;}
        Map<String,Object> activity=found.get(0);
        List<Map<String,Object>> tracks=jdbc.queryForList("SELECT t.id::text AS tracklet_id,t.source_id::text,t.stream_session_id::text,t.first_observed_at,t.last_observed_at,t.revision FROM public.episode_tracklet_link l JOIN public.tracklet t ON t.id=l.tracklet_id WHERE l.episode_id=?::uuid AND t.first_observed_at IS NOT NULL AND t.last_observed_at IS NOT NULL ORDER BY t.first_observed_at,t.id",id);
        if(tracks.isEmpty()){return false;}
        if("open".equals(activity.get("state"))){
            OffsetDateTime first=at(activity.get("start_ts")),last=at(activity.get("end_ts"));
            for(Map<String,Object> track:tracks){if(at(track.get("first_observed_at")).isBefore(first)){first=at(track.get("first_observed_at"));}if(at(track.get("last_observed_at")).isAfter(last)){last=at(track.get("last_observed_at"));}}
            boolean idle=!last.plusSeconds(idleSeconds).isAfter(now);
            if(!first.equals(at(activity.get("start_ts")))||!last.equals(at(activity.get("end_ts")))||idle){
                long revision=((Number)activity.get("revision")).longValue()+1;
                jdbc.update("UPDATE public.episode SET start_ts=?,end_ts=?,expires_at=?,state=?,end_reason=?,revision=? WHERE id=?::uuid",first,last,last.plusDays(7),idle?"closed":"open",idle?"normal":null,revision,id);
                activity.put("start_ts",first);activity.put("end_ts",last);activity.put("expires_at",last.plusDays(7));activity.put("revision",revision);activity.put("state",idle?"closed":"open");activity.put("end_reason",idle?"normal":null);
                if(idle){data.store().event(jdbc,"activity.closed","episode",id,revision,values("activity_id",id,"identity_id",activity.get("identity_id").toString(),"end_reason","normal"),last.plusDays(7));}
            }
            if(!idle){return false;}
        }
        jdbc.queryForObject("SELECT pg_advisory_xact_lock(hashtextextended(?,0)) IS NULL",Boolean.class,"report:activity:"+id+":person_route");
        List<Map<String,Object>> previous=jdbc.queryForList("SELECT * FROM public.llm_report WHERE subject_kind='activity' AND subject_id=?::uuid AND report_type='person_route' FOR UPDATE",id);
        Map<String,Object> old=previous.isEmpty()?null:previous.get(0);
        // A later Agent-authored report owns its content; polling must not replace it.
        if(old!=null&&(old.get("task_id")!=null||!GENERATOR.equals(old.get("model_version")))){return false;}
        List<Map<String,Object>> assetInputs=new ArrayList<>(),coverageInputs=new ArrayList<>();
        for(Map<String,Object> track:tracks){
            for(Map<String,Object> asset:jdbc.queryForList("SELECT id::text AS asset_id,stream_session_id::text,start_ts,duration_ms,state,revision,expires_at FROM public.media_asset WHERE source_id=?::uuid AND stream_session_id=?::uuid AND asset_type='recording' AND state IS NOT NULL AND start_ts<=? AND start_ts+duration_ms*interval '1 millisecond'>? ORDER BY start_ts,id",track.get("source_id"),track.get("stream_session_id"),track.get("last_observed_at"),track.get("first_observed_at"))){asset.put("tracklet_id",track.get("tracklet_id"));assetInputs.add(clean(asset));}
            for(Map<String,Object> coverage:jdbc.queryForList("SELECT id::text,stage,status,reason_code,closed,revision FROM public.processing_coverage WHERE stream_session_id=?::uuid AND stage IN ('input','recording','analysis','registration','features') AND start_at<=? AND end_at>? ORDER BY stage,start_at,id",track.get("stream_session_id"),track.get("last_observed_at"),track.get("first_observed_at"))){coverageInputs.add(clean(coverage));}
            clean(track);
        }
        String signature=BusinessCanonical.digest(values("state",activity.get("state"),"end_reason",activity.get("end_reason"),"tracks",tracks,"assets",assetInputs,"coverage",coverageInputs));
        if(old!=null&&signature.equals(map(parse(old.get("report_json").toString()).get("generator")).get("source_signature"))){return false;}
        OffsetDateTime expires=at(activity.get("expires_at"));
        List<Map<String,Object>> route=new ArrayList<>(),gaps=new ArrayList<>();List<String> evidenceIds=new ArrayList<>();
        long observed=0,located=0;
        for(Map<String,Object> track:tracks){
            String trackId=track.get("tracklet_id").toString();
            List<Map<String,Object>> frameCounts=jdbc.queryForList("SELECT count(DISTINCT f.id) AS observed_frame_count,count(DISTINCT f.id) FILTER(WHERE f.media_pts_ms IS NOT NULL AND a.state='available' AND a.expires_at>?) AS located_frame_count FROM public.detection_observation o JOIN public.analysis_frame af ON af.id=o.analysis_frame_id JOIN public.input_frame f ON f.id=af.input_frame_id LEFT JOIN public.media_asset a ON a.id=f.media_asset_id WHERE o.tracklet_id=?::uuid AND o.observation_kind='observed'",now,trackId);
            long count=((Number)frameCounts.get(0).get("observed_frame_count")).longValue(),ready=((Number)frameCounts.get(0).get("located_frame_count")).longValue();observed+=count;located+=ready;
            List<Map<String,Object>> clips=new ArrayList<>();
            String factId=evidence(jdbc,id,track,null,expires);evidenceIds.add(factId);
            for(Map<String,Object> asset:assetInputs){
                if(!trackId.equals(asset.get("tracklet_id"))||!"available".equals(asset.get("state"))||!time(asset,"expires_at").isAfter(now)){continue;}
                String evidence=evidence(jdbc,id,track,asset,expires);evidenceIds.add(evidence);
                Map<String,Object> offsets=jdbc.queryForMap("SELECT min(f.media_pts_ms) AS first_media_pts_ms,max(f.media_pts_ms) AS last_media_pts_ms FROM public.input_frame f JOIN public.analysis_frame af ON af.input_frame_id=f.id JOIN public.detection_observation o ON o.analysis_frame_id=af.id WHERE o.tracklet_id=?::uuid AND o.observation_kind='observed' AND f.media_asset_id=?::uuid",trackId,asset.get("asset_id"));
                clips.add(values("evidence_id",evidence,"asset_id",asset.get("asset_id"),"start_at",asset.get("start_ts"),"duration_ms",asset.get("duration_ms"),"first_media_pts_ms",offsets.get("first_media_pts_ms"),"last_media_pts_ms",offsets.get("last_media_pts_ms"),"state","available"));
            }
            if(count==0||ready<count){gaps.add(values("tracklet_id",trackId,"stage","recording","reason_code",count==0?"OBSERVATIONS_UNAVAILABLE":"RECORDING_LOCATION_PENDING","observed_frame_count",count,"located_frame_count",ready));}
            if(time(track,"last_observed_at").isAfter(at(activity.get("end_ts")))){gaps.add(values("tracklet_id",trackId,"stage","activity","reason_code","LATE_OBSERVATIONS_AFTER_CLOSURE"));}
            route.add(values("tracklet_id",trackId,"source_id",track.get("source_id"),"stream_session_id",track.get("stream_session_id"),"first_observed_at",track.get("first_observed_at"),"last_observed_at",track.get("last_observed_at"),"observed_frame_count",count,"located_frame_count",ready,"evidence_id",factId,"recordings",clips));
        }
        for(Map<String,Object> coverage:coverageInputs){if(!"complete".equals(coverage.get("status"))){gaps.add(values("stage",coverage.get("stage"),"coverage_id",coverage.get("id"),"reason_code",coverage.get("reason_code"),"status",coverage.get("status")));}}
        if("interrupted".equals(activity.get("state"))){gaps.add(values("stage","input","reason_code","OBSERVATION_INTERRUPTED"));}
        String completeness=gaps.isEmpty()?"complete":"partial";
        Map<String,Object> coverage=values("schema_version","1","status",completeness,"scope","persisted_associated_tracks","observed_frame_count",observed,"located_frame_count",located,"gaps",gaps);
        Map<String,Object> content=values("schema_version","1","activity_id",id,"identity_id",activity.get("identity_id").toString(),"start_at",iso(at(activity.get("start_ts"))),"end_at",iso(at(activity.get("end_ts"))),"state",activity.get("state"),"end_reason",activity.get("end_reason"),"route",route,"coverage",coverage,"generator",values("kind","local_structured","version",GENERATOR,"source_signature",signature));
        String report=old==null?UUID.randomUUID().toString():old.get("id").toString();long revision=old==null?1:((Number)old.get("revision")).longValue()+1;
        if(old==null){jdbc.update("INSERT INTO public.llm_report(id,episode_id,subject_kind,subject_id,report_type,completeness,coverage_json,model_version,processed_at,revision,expires_at,report_json,report_text) VALUES (?::uuid,?::uuid,'activity',?::uuid,'person_route',?,?::jsonb,?,now(),?,?,?::jsonb,?)",report,id,id,completeness,json(coverage),GENERATOR,revision,expires,json(content),"人员活动路线，共"+route.size()+"段出现记录。");}
        else{jdbc.update("UPDATE public.llm_report SET completeness=?,coverage_json=?::jsonb,processed_at=now(),revision=?,report_json=?::jsonb,report_text=? WHERE id=?::uuid",completeness,json(coverage),revision,json(content),"人员活动路线，共"+route.size()+"段出现记录。",report);jdbc.update("DELETE FROM public.report_evidence_link WHERE report_id=?::uuid",report);}
        int ordinal=0;for(String evidence:evidenceIds){jdbc.update("INSERT INTO public.report_evidence_link(report_id,evidence_id,report_revision,ordinal) VALUES (?::uuid,?::uuid,?,?)",report,evidence,revision,ordinal++);}
        jdbc.update("UPDATE public.episode SET coverage_json=?::jsonb WHERE id=?::uuid",json(coverage),id);
        data.store().event(jdbc,"report.updated","llm_report",report,revision,values("report_id",report,"subject_kind","activity","subject_id",id,"completeness",completeness),expires);
        return true;
    }

    private String evidence(JdbcTemplate jdbc,String activity,Map<String,Object> track,Map<String,Object> asset,OffsetDateTime expires){
        String assetId=asset==null?null:asset.get("asset_id").toString();
        List<Map<String,Object>> rows=jdbc.queryForList("SELECT id::text FROM public.evidence_reference WHERE activity_id=?::uuid AND original_tracklet_id=?::uuid AND asset_id IS NOT DISTINCT FROM ?::uuid AND provenance_json->>'generator'=? ORDER BY id LIMIT 1",activity,track.get("tracklet_id"),assetId,GENERATOR);
        String id=rows.isEmpty()?UUID.randomUUID().toString():rows.get(0).get("id").toString();
        Map<String,Object> snapshot=values("schema_version","1","tracklet_id",track.get("tracklet_id"),"source_id",track.get("source_id"),"first_observed_at",track.get("first_observed_at"),"last_observed_at",track.get("last_observed_at"));
        Map<String,Object> provenance=values("schema_version","1","generator",GENERATOR,"stream_session_id",track.get("stream_session_id"));
        OffsetDateTime start=time(track,"first_observed_at"),end=time(track,"last_observed_at");
        if(asset!=null){OffsetDateTime assetStart=time(asset,"start_ts"),assetEnd=assetStart.plusNanos(((Number)asset.get("duration_ms")).longValue()*1000000);if(assetStart.isAfter(start)){start=assetStart;}if(assetEnd.isBefore(end)){end=assetEnd;}}
        if(rows.isEmpty()){jdbc.update("INSERT INTO public.evidence_reference(id,activity_id,source_id,asset_id,original_tracklet_id,start_at,end_at,fact_snapshot,provenance_json,expires_at) VALUES (?::uuid,?::uuid,?::uuid,?::uuid,?::uuid,?,?,?::jsonb,?::jsonb,?)",id,activity,track.get("source_id"),assetId,track.get("tracklet_id"),start,end,json(snapshot),json(provenance),expires);}
        else{jdbc.update("UPDATE public.evidence_reference SET start_at=?,end_at=?,fact_snapshot=?::jsonb WHERE id=?::uuid",start,end,json(snapshot),id);}
        if(assetId!=null){jdbc.update("INSERT INTO public.asset_reference(asset_id,evidence_id,retain_until) SELECT ?::uuid,?::uuid,? WHERE NOT EXISTS(SELECT 1 FROM public.asset_reference WHERE asset_id=?::uuid AND evidence_id=?::uuid)",assetId,id,expires,assetId,id);}
        return id;
    }
}
