package edu.cqupt.hxjm.algdeployment.business.service;

import java.sql.Timestamp;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

/** Business-owned validation of task subjects, assets and live input references. */
@Service
@ConditionalOnProperty(prefix="hxjm.business", name="enabled", havingValue="true")
public class BusinessTaskInputs {
    private final BusinessDataAccess businessData;
    private final ActivityBusinessService activityService;
    public BusinessTaskInputs(BusinessDataAccess businessData, ActivityBusinessService activityService) {
        this.businessData=businessData;this.activityService=activityService;
    }
    public Scope resolve(JdbcTemplate jdbc, BusinessActor actor, Map<String,Object> input, String mode, boolean processing) {
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
        if(expires==null||!expires.isAfter(OffsetDateTime.now())){throw BusinessException.expired("输入已到期");}return new Scope(sources,expires);
    }

    public static final class Scope {
        public final Set<String> sources;
        public final OffsetDateTime expires;
        public Scope(Set<String> sources, OffsetDateTime expires) {this.sources=sources;this.expires=expires;}
    }
    private static List<String> uuids(Object value){List<String> result=new ArrayList<>();for(Object item:list(value)){String id=uuid(item,"id");if(!result.contains(id)){result.add(id);}}return result;}
    private static OffsetDateTime timestamp(Object value){if(value instanceof OffsetDateTime){return (OffsetDateTime)value;}return ((Timestamp)value).toInstant().atOffset(ZoneOffset.UTC);}
}
