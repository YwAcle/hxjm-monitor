package edu.cqupt.hxjm.algdeployment.business.service;

import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessCanonical;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;
import static edu.cqupt.hxjm.algdeployment.business.service.BusinessDataAccess.*;

/** Read-only discovery for the shared page and Agent business contract. */
@Service
@ConditionalOnProperty(prefix="hxjm.business",name="enabled",havingValue="true")
public class BusinessDiscoveryService {
    private final BusinessDataAccess data;
    private final ActivityBusinessService activities;
    public BusinessDiscoveryService(BusinessDataAccess data,ActivityBusinessService activities){this.data=data;this.activities=activities;}

    // Resolve current identity aliases without merging the underlying stored identities.
    private static final String RELATIONS =
        "keys AS (SELECT i.id,coalesce(l.registered_identity_id,i.id) AS resolved_id FROM public.identity i LEFT JOIN public.identity_link l ON l.temporary_identity_id=i.id AND l.valid_to IS NULL AND l.expires_at>now() AND EXISTS(SELECT 1 FROM public.identity r WHERE r.id=l.registered_identity_id AND r.enabled AND (r.expires_at IS NULL OR r.expires_at>now())) WHERE i.enabled AND (i.expires_at IS NULL OR i.expires_at>now())),"+
        "tracks AS (SELECT DISTINCT t.id,t.source_id,t.stream_session_id,t.first_observed_at,t.last_observed_at,t.expires_at,a.identity_id,k.resolved_id FROM public.track_identity_assignment a JOIN keys k ON k.id=a.identity_id JOIN public.tracklet raw ON raw.id=a.tracklet_id JOIN public.tracklet t ON t.id=coalesce(raw.canonical_tracklet_id,raw.id) WHERE a.valid_to IS NULL AND a.expires_at>now() AND raw.expires_at>now() AND t.expires_at>now() AND t.first_observed_at IS NOT NULL AND t.last_observed_at IS NOT NULL),"+
        "wanted AS (SELECT DISTINCT k.resolved_id FROM keys k WHERE k.id=ANY(?::uuid[]))";

    public Map<String,Object> identities(BusinessActor actor,Map<String,Object> body){
        fields(body,"identity_kind","object_type","display_name","source_ids","start_at","end_at","limit","cursor","trace_id");
        Query q=new Query(actor,body,"identities",100,500,false);
        String kind=optionalText(body,"identity_kind",16),object=optionalText(body,"object_type",64),name=optionalText(body,"display_name",200);
        if(kind!=null&&!Arrays.asList("registered","temporary").contains(kind)){throw BusinessException.invalid("identity_kind无效");}
        q.scope.put("identity_kind",kind);q.scope.put("object_type",object);q.scope.put("display_name",name);
        String sql="WITH "+RELATIONS+" SELECT i.id AS identity_id,i.identity_kind,i.object_type,i.display_no,i.display_name,i.employee_id,i.registered_at,v.first_seen_at,v.last_seen_at,i.revision,i.expires_at FROM public.identity i JOIN keys k ON k.id=i.id LEFT JOIN LATERAL (SELECT min(t.first_observed_at) AS first_seen_at,max(t.last_observed_at) AS last_seen_at FROM tracks t WHERE t.resolved_id=k.resolved_id AND t.source_id=ANY(?::uuid[])"+q.timeFilter("t.first_observed_at","t.last_observed_at")+")v ON true WHERE (?::text IS NULL OR i.identity_kind=?) AND (?::text IS NULL OR i.object_type=?) AND (?::text IS NULL OR i.display_name=?) AND "+(q.appearanceFilter?"v.last_seen_at IS NOT NULL":"(i.identity_kind='registered' OR v.last_seen_at IS NOT NULL)");
        List<Object> args=new ArrayList<>(Arrays.asList("{}",pgArray(q.sources)));q.timeArgs(args);
        Collections.addAll(args,kind,kind,object,object,name,name);
        return q.page(sql,args,"identity_id",null,false);
    }

    public Map<String,Object> tracklets(BusinessActor actor,Map<String,Object> body){
        fields(body,"identity_ids","source_ids","start_at","end_at","limit","cursor","trace_id");
        Query q=new Query(actor,body,"tracklets",20,100,true);List<String> people=q.people(true);
        String sql="WITH "+RELATIONS+" SELECT DISTINCT ON(t.id) t.id AS tracklet_id,t.identity_id,t.resolved_id AS resolved_identity_id,i.display_name,t.source_id,c.name AS source_name,t.stream_session_id,t.first_observed_at,t.last_observed_at,t.expires_at,(SELECT e.id FROM public.episode_tracklet_link l JOIN public.episode e ON e.id=l.episode_id JOIN public.tracklet lt ON lt.id=l.tracklet_id WHERE coalesce(lt.canonical_tracklet_id,lt.id)=t.id AND e.expires_at>now() ORDER BY e.start_ts,e.id LIMIT 1) AS activity_id FROM tracks t JOIN public.identity i ON i.id=t.resolved_id JOIN public.camera c ON c.id=t.source_id WHERE t.resolved_id IN(SELECT resolved_id FROM wanted) AND t.source_id=ANY(?::uuid[])"+q.timeFilter("t.first_observed_at","t.last_observed_at")+" ORDER BY t.id,t.identity_id";
        List<Object> args=new ArrayList<>(Arrays.asList(pgArray(people),pgArray(q.sources)));q.timeArgs(args);
        return q.page(sql,args,"tracklet_id","first_observed_at",false);
    }

    public Map<String,Object> events(BusinessActor actor,Map<String,Object> body){
        fields(body,"mode","source_ids","start_at","end_at","limit","cursor","trace_id");
        String mode=text(body,"mode",16);if(!Arrays.asList("latest","range").contains(mode)){throw BusinessException.invalid("mode须为latest或range");}
        if("latest".equals(mode)&&(body.containsKey("start_at")||body.containsKey("end_at"))){throw BusinessException.invalid("latest不接受时间范围");}
        Query q=new Query(actor,body,"events",20,100,"range".equals(mode));q.scope.put("mode",mode);
        String sql="SELECT e.id AS event_id,e.event_type,e.source_id,c.name AS source_name,e.start_at,e.end_at,e.state,e.end_reason,e.conclusion_json,e.coverage_json,e.revision,e.expires_at FROM public.business_event e LEFT JOIN public.camera c ON c.id=e.source_id WHERE e.expires_at>now() AND (e.source_id IS NULL OR e.source_id=ANY(?::uuid[])) AND NOT EXISTS(SELECT 1 FROM public.evidence_reference ev WHERE ev.event_id=e.id AND ev.expires_at>now() AND ev.source_id IS NOT NULL AND NOT(ev.source_id=ANY(?::uuid[]))) AND (e.source_id IS NOT NULL OR EXISTS(SELECT 1 FROM public.evidence_reference ev WHERE ev.event_id=e.id AND ev.expires_at>now() AND ev.source_id=ANY(?::uuid[]))) AND (e.source_id=ANY(?::uuid[]) OR EXISTS(SELECT 1 FROM public.evidence_reference ev WHERE ev.event_id=e.id AND ev.expires_at>now() AND ev.source_id=ANY(?::uuid[])))"+q.timeFilter("e.start_at","e.end_at");
        List<Object> args=new ArrayList<>(Arrays.asList(pgArray(q.authorized),pgArray(q.authorized),pgArray(q.authorized),pgArray(q.sources),pgArray(q.sources)));q.timeArgs(args);
        return q.page(sql,args,"event_id","start_at",true);
    }

    public Map<String,Object> reports(BusinessActor actor,Map<String,Object> body){
        fields(body,"identity_ids","source_ids","start_at","end_at","report_type","limit","cursor","trace_id");
        Query q=new Query(actor,body,"reports",20,100,true);List<String> people=q.people(false);String type=optionalText(body,"report_type",64);q.scope.put("report_type",type);
        String sql="WITH "+RELATIONS+", subjects AS ("+
            "SELECT 'activity'::text AS kind,e.id,e.start_ts AS start_at,e.end_ts AS end_at FROM public.episode e WHERE e.expires_at>now() UNION ALL "+
            "SELECT 'event',e.id,e.start_at,e.end_at FROM public.business_event e WHERE e.expires_at>now() UNION ALL "+
            "SELECT 'query',q.id,q.start_at,q.end_at FROM public.query_request q WHERE q.expires_at>now() AND (q.owner_user_id=?::bigint OR (q.owner_user_id IS NULL AND ?::boolean))),"+
            "subject_sources AS ("+
            "SELECT 'activity'::text AS kind,l.episode_id AS id,t.source_id FROM public.episode_tracklet_link l JOIN public.tracklet t ON t.id=l.tracklet_id UNION "+
            "SELECT 'event',e.id,e.source_id FROM public.business_event e WHERE e.source_id IS NOT NULL UNION "+
            "SELECT CASE WHEN ev.activity_id IS NOT NULL THEN 'activity' ELSE 'event' END,coalesce(ev.activity_id,ev.event_id),ev.source_id FROM public.evidence_reference ev WHERE ev.expires_at>now() AND ev.source_id IS NOT NULL UNION "+
            "SELECT 'query',q.id,(j.value#>>'{}')::uuid FROM public.query_request q CROSS JOIN LATERAL jsonb_array_elements(coalesce(q.scope_json->'source_ids','[]'::jsonb)) j),"+
            "subject_people AS ("+
            "SELECT 'activity'::text AS kind,e.id,e.identity_id FROM public.episode e WHERE e.identity_id IS NOT NULL UNION "+
            "SELECT 'event',o.event_id,coalesce(o.identity_id,a.identity_id,s.identity_id,sa.identity_id) FROM public.event_object_link o LEFT JOIN public.track_identity_assignment a ON a.tracklet_id=o.tracklet_id AND a.valid_to IS NULL AND a.expires_at>now() LEFT JOIN public.sample s ON s.id=o.sample_id AND s.available AND (s.expires_at IS NULL OR s.expires_at>now()) LEFT JOIN public.track_identity_assignment sa ON sa.tracklet_id=s.tracklet_id AND sa.valid_to IS NULL AND sa.expires_at>now() WHERE o.expires_at>now() UNION "+
            "SELECT 'query',q.id,q.identity_id FROM public.query_request q WHERE q.identity_id IS NOT NULL),"+
            "catalog AS (SELECT r.id AS report_id,r.subject_kind,r.subject_id,r.report_type,s.start_at AS event_start_at,s.end_at AS event_end_at,r.processed_at,r.revision,r.completeness,r.coverage_json,r.report_text,r.report_json,r.expires_at,"+
            "ARRAY(SELECT DISTINCT k.resolved_id FROM subject_people p JOIN keys k ON k.id=p.identity_id WHERE p.kind=s.kind AND p.id=s.id ORDER BY k.resolved_id) AS identity_ids,"+
            "ARRAY(SELECT DISTINCT all_sources.source_id FROM (SELECT ss.source_id FROM subject_sources ss WHERE ss.kind=s.kind AND ss.id=s.id UNION SELECT ev.source_id FROM public.report_evidence_link rel JOIN public.evidence_reference ev ON ev.id=rel.evidence_id WHERE rel.report_id=r.id AND ev.expires_at>now() AND ev.source_id IS NOT NULL) all_sources ORDER BY all_sources.source_id) AS source_ids FROM public.llm_report r JOIN subjects s ON s.kind=r.subject_kind AND s.id=r.subject_id WHERE r.expires_at>now()) "+
            "SELECT r.* FROM catalog r WHERE r.event_start_at IS NOT NULL AND r.source_ids<@?::uuid[] AND (?::boolean OR r.identity_ids && ARRAY(SELECT resolved_id FROM wanted)) AND (?::boolean OR r.source_ids && ?::uuid[]) AND (?::text IS NULL OR r.report_type=?)"+q.timeFilter("r.event_start_at","r.event_end_at");
        List<Object> args=new ArrayList<>(Arrays.asList(pgArray(people),actor.getUserId(),actor.isShared()||actor.isService(),pgArray(q.authorized),people.isEmpty(),!body.containsKey("source_ids"),pgArray(q.sources),type,type));q.timeArgs(args);
        Map<String,Object> page=q.page(sql,args,"report_id","event_start_at",true);
        for(Object value:list(page.get("items"))){
            Map<String,Object> row=map(value);String report=row.get("report_id").toString();activities.getReport(actor,report);
            List<Map<String,Object>> evidence=data.store().jdbc().queryForList("SELECT ev.id AS evidence_id,l.ordinal,l.report_revision,ev.source_id,ev.asset_id,ev.start_at,ev.end_at,ev.fact_snapshot AS fact_snapshot_json,ev.provenance_json,ev.expires_at,greatest(0,extract(epoch FROM (ev.start_at-a.start_ts))*1000)::bigint AS offset_ms FROM public.report_evidence_link l JOIN public.evidence_reference ev ON ev.id=l.evidence_id LEFT JOIN public.media_asset a ON a.id=ev.asset_id WHERE l.report_id=?::uuid AND ev.expires_at>now() ORDER BY l.ordinal",report);
            for(Map<String,Object> item:evidence){clean(item);}row.put("evidence",evidence);
        }
        return page;
    }

    private final class Query {
        final BusinessActor actor;final Map<String,Object> body,scope=new LinkedHashMap<>();
        final String operation;final int limit;final List<String> authorized,sources;final OffsetDateTime from,to;final boolean appearanceFilter;
        Query(BusinessActor actor,Map<String,Object> body,String operation,int defaultLimit,int maxLimit,boolean requiredTime){
            this.actor=actor;this.body=body;this.operation=operation;
            authorized=new ArrayList<>(actor.getSourceIds());Collections.sort(authorized);
            sources=body.containsKey("source_ids")?ids(required(body,"source_ids")):new ArrayList<>(authorized);Collections.sort(sources);actor.authorizedSources(sources);
            if(body.containsKey("source_ids")&&sources.isEmpty()){throw BusinessException.invalid("source_ids不能为空");}
            if(!sources.isEmpty()&&data.store().jdbc().queryForObject("SELECT count(*) FROM public.camera WHERE id=ANY(?::uuid[])",Long.class,pgArray(sources))!=sources.size()){throw BusinessException.notFound("请求包含不存在的视频来源");}
            from=body.get("start_at")==null?null:time(body,"start_at");to=body.get("end_at")==null?null:time(body,"end_at");
            if((from==null)!=(to==null)||requiredTime&&from==null||from!=null&&!to.isAfter(from)){throw BusinessException.invalid("须同时提供有效的start_at和end_at");}
            limit=body.containsKey("limit")?(int)integer(body,"limit",1,maxLimit):defaultLimit;
            appearanceFilter=body.containsKey("source_ids")||from!=null;
            scope.put("source_ids",sources);scope.put("start_at",from==null?null:iso(from));scope.put("end_at",to==null?null:iso(to));
        }
        List<String> people(boolean required){List<String> people=body.containsKey("identity_ids")?ids(required(body,"identity_ids")):new ArrayList<>();if(required&&people.isEmpty()||body.containsKey("identity_ids")&&(people.isEmpty()||list(body.get("identity_ids")).size()>100)){throw BusinessException.invalid("identity_ids须为1至100个UUID");}Collections.sort(people);for(String id:people){data.identity(data.store().jdbc(),actor,id);}scope.put("identity_ids",people);return people;}
        String timeFilter(String start,String end){return from==null?"":" AND "+start+"<? AND ("+end+" IS NULL OR "+end+">? OR ("+end+"="+start+" AND "+start+">=?))";}
        void timeArgs(List<Object> args){if(from!=null){Collections.addAll(args,to,from,from);}}
        Map<String,Object> page(String select,List<Object> args,String id,String stamp,boolean descending){
            Map<String,Object> binding=values("operation",operation,"scope",scope,"limit",limit,"actor",actor.getActorKey(),"authorized",authorized,"explicit_sources",body.containsKey("source_ids"));
            String digest=BusinessCanonical.digest(binding),afterId=null,afterTime=null;
            if(body.containsKey("cursor")){
                try{String raw=text(body,"cursor",4096);Map<String,Object> cursor=parse(new String(Base64.getUrlDecoder().decode(raw),StandardCharsets.UTF_8));fields(cursor,"binding","id","time");if(!digest.equals(cursor.get("binding"))){throw BusinessException.invalid("游标与查询条件不匹配");}afterId=uuid(cursor,"id");if(stamp!=null){afterTime=iso(time(cursor,"time"));}else if(cursor.get("time")!=null){throw BusinessException.invalid("游标类型错误");}}
                catch(IllegalArgumentException ex){throw BusinessException.invalid("游标无效");}
            }
            String sql="SELECT * FROM ("+select+") discovery WHERE true";
            if(afterId!=null){sql+=" AND "+(stamp==null?id+">?::uuid":"("+stamp+","+id+")"+(descending?"<":">")+"(?::timestamptz,?::uuid)");if(stamp!=null){args.add(afterTime);}args.add(afterId);}
            sql+=" ORDER BY "+(stamp==null?"":stamp+(descending?" DESC,":" ASC,"))+id+(descending?" DESC":" ASC")+" LIMIT ?";args.add(limit+1);
            List<Map<String,Object>> rows=data.store().jdbc().queryForList(sql,args.toArray());boolean more=rows.size()>limit;List<Map<String,Object>> items=new ArrayList<>(rows.subList(0,Math.min(limit,rows.size())));
            for(Map<String,Object> row:items){clean(row);for(String column:Arrays.asList("identity_ids","source_ids")){if(row.get(column) instanceof java.sql.Array){try{List<String> array=new ArrayList<>();for(Object value:(Object[])((java.sql.Array)row.get(column)).getArray()){array.add(value.toString());}row.put(column,array);}catch(java.sql.SQLException ex){throw new IllegalStateException(ex);}}}}
            String next=null;if(more){Map<String,Object> last=items.get(items.size()-1);next=Base64.getUrlEncoder().withoutPadding().encodeToString(json(values("binding",digest,"id",last.get(id),"time",stamp==null?null:last.get(stamp))).getBytes(StandardCharsets.UTF_8));}
            return values("items",items,"has_more",more,"next_cursor",next,"scope",scope);
        }
    }
}
