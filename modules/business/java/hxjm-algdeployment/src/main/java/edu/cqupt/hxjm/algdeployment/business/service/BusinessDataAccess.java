package edu.cqupt.hxjm.algdeployment.business.service;

import java.sql.Timestamp;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessStore;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

/** Shared checks for the new identity, feature, activity and query endpoints. */
@Component
@ConditionalOnProperty(prefix="hxjm.business",name="enabled",havingValue="true")
public class BusinessDataAccess {
    private final BusinessStore store;
    private final RecordingService recordings;
    public BusinessDataAccess(BusinessStore store,RecordingService recordings){this.store=store;this.recordings=recordings;}
    public BusinessStore store(){return store;}
    public RecordingService recordings(){return recordings;}
    static OffsetDateTime at(Object value){return value instanceof OffsetDateTime?(OffsetDateTime)value:((Timestamp)value).toInstant().atOffset(ZoneOffset.UTC);}
    static String optionalId(Map<String,Object> body,String key){return body.get(key)==null?null:uuid(body,key);}
    static String optionalText(Map<String,Object> body,String key,int size){return body.get(key)==null?null:text(body,key,size);}
    static String documentText(Map<String,Object> body,String key,int size){Object value=required(body,key);if(!(value instanceof String)||((String)value).length()>size||((String)value).indexOf('\0')>=0){throw BusinessException.invalid(key+"须为允许长度内的文本");}return (String)value;}
    static Map<String,Object> object(Map<String,Object> body,String key){return body.get(key)==null?values():map(body.get(key));}
    static Map<String,Object> one(List<Map<String,Object>> rows,String message){if(rows.isEmpty()){throw BusinessException.notFound(message);}return rows.get(0);}
    static void fresh(Map<String,Object> row){if(row.get("expires_at")!=null&&!at(row.get("expires_at")).isAfter(OffsetDateTime.now())){throw BusinessException.expired("业务数据已到期");}}
    static OffsetDateTime earlier(OffsetDateTime a,OffsetDateTime b){return a==null?b:b==null?a:a.isBefore(b)?a:b;}
    static OffsetDateTime expiry(Map<String,Object> row){return row.get("expires_at")==null?null:at(row.get("expires_at"));}
    static OffsetDateTime requestExpiry(OffsetDateTime expiry){return expiry==null?OffsetDateTime.now().plusDays(7):expiry;}
    static String newId(Map<String,Object> body,String key){String id=uuid(body,key);if(UUID.fromString(id).version()!=4){throw BusinessException.invalid(key+"须为UUIDv4");}return id;}
    static void revision(Map<String,Object> row,Map<String,Object> body){if(integer(body,"expected_revision",1,Long.MAX_VALUE)!=((Number)row.get("revision")).longValue()){throw BusinessException.conflict("修订号已改变");}}
    static double number(Object value){if(!(value instanceof Number)||!Double.isFinite(((Number)value).doubleValue())){throw BusinessException.invalid("数值必须有限");}return ((Number)value).doubleValue();}
    static List<String> ids(Object raw){List<String> out=new ArrayList<>();for(Object value:list(raw)){String id=uuid(value,"id");if(!out.contains(id)){out.add(id);}}return out;}
    static String pgArray(Iterable<String> values){List<String> out=new ArrayList<>();for(String value:values){out.add("\""+value.replace("\\","\\\\").replace("\"","\\\"")+"\"");}return "{"+String.join(",",out)+"}";}
    static Map<String,Object> clean(Map<String,Object> row){for(Map.Entry<String,Object> e:row.entrySet()){Object value=e.getValue();if(value instanceof Timestamp||value instanceof OffsetDateTime){e.setValue(iso(at(value)));}else if(value instanceof UUID){e.setValue(value.toString());}else if(e.getKey().endsWith("_json")&&value!=null){e.setValue(parse(value.toString()));}}return row;}
    public Map<String,Object> track(JdbcTemplate jdbc,BusinessActor actor,String id){
        Map<String,Object> row=one(jdbc.queryForList("SELECT * FROM public.tracklet WHERE id=?::uuid",id),"轨迹不存在");
        if(row.get("canonical_tracklet_id")!=null){row=one(jdbc.queryForList("SELECT * FROM public.tracklet WHERE id=?::uuid",row.get("canonical_tracklet_id").toString()),"规范轨迹不存在");}
        if(row.get("source_id")==null){throw BusinessException.conflict("轨迹尚未接入统一来源");}actor.requireSource(row.get("source_id").toString());fresh(row);return row;
    }
    public Map<String,Object> sample(JdbcTemplate jdbc,BusinessActor actor,String id){
        Map<String,Object> row=one(jdbc.queryForList("SELECT * FROM public.sample WHERE id=?::uuid AND available",id),"样本不存在或已失效");fresh(row);recordings.asset(actor,row.get("asset_id").toString());return row;
    }
    public Map<String,Object> feature(JdbcTemplate jdbc,BusinessActor actor,String id){
        Map<String,Object> row=one(jdbc.queryForList("SELECT * FROM public.feature WHERE id=?::uuid AND state='ready'",id),"特征不存在或已失效");fresh(row);
        List<Map<String,Object>> contributions=jdbc.queryForList("SELECT sample_id FROM public.feature_contribution WHERE feature_id=?::uuid ORDER BY ordinal",id);
        if(contributions.isEmpty()){throw BusinessException.conflict("特征缺少有效贡献");}for(Map<String,Object> c:contributions){sample(jdbc,actor,c.get("sample_id").toString());}return row;
    }
    public Map<String,Object> identity(JdbcTemplate jdbc,BusinessActor actor,String id){
        Map<String,Object> row=one(jdbc.queryForList("SELECT * FROM public.identity WHERE id=?::uuid AND enabled",id),"身份不存在或已停用");fresh(row);
        if("temporary".equals(row.get("identity_kind"))){
            List<Map<String,Object>> sources=jdbc.queryForList("SELECT DISTINCT t.source_id FROM public.track_identity_assignment a JOIN public.tracklet t ON t.id=a.tracklet_id WHERE a.identity_id=?::uuid AND a.valid_to IS NULL AND a.expires_at>now() AND t.expires_at>now()",id);
            boolean allowed=false;for(Map<String,Object> source:sources){if(actor.getSourceIds().contains(source.get("source_id").toString())){allowed=true;}}
            if(!allowed){throw BusinessException.forbidden();}
        }return row;
    }
    public Map<String,Object> run(JdbcTemplate jdbc,BusinessActor actor,String id){
        Map<String,Object> row=one(jdbc.queryForList("SELECT a.*,t.current_run_id,t.actor_key,t.state AS task_state FROM public.task_attempt a JOIN public.business_task t ON t.task_id=a.task_id WHERE a.run_id=?::uuid FOR UPDATE OF t",id),"执行不存在");fresh(row);
        if(!actor.getActorKey().equals(row.get("lease_owner"))||!actor.getActorKey().equals(row.get("actor_key"))){throw BusinessException.forbidden();}
        if(!id.equals(String.valueOf(row.get("current_run_id")))||!"running".equals(row.get("state"))||!"running".equals(row.get("task_state"))){throw BusinessException.conflict("执行已被替换或结束");}return row;
    }
}
