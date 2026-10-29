package edu.cqupt.hxjm.algdeployment.business.service;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;
import static edu.cqupt.hxjm.algdeployment.business.service.BusinessDataAccess.*;

@Service
@ConditionalOnProperty(prefix="hxjm.business",name="enabled",havingValue="true")
public class BusinessSearchService {
    private final BusinessDataAccess data;
    public BusinessSearchService(BusinessDataAccess data){this.data=data;}

    public Map<String,Object> create(BusinessActor actor,Map<String,Object> body){
        fields(body,"request_id","trace_id","query_id","query_kind","object_type","input_asset_id","identity_id","start_at","end_at","source_ids");
        if(actor.getUserId()==null&&!actor.isShared()){throw BusinessException.forbidden();}
        String id=newId(body,"query_id"),kind=text(body,"query_kind",32),object=text(body,"object_type",64),asset=optionalId(body,"input_asset_id"),identity=optionalId(body,"identity_id");
        if(!"image".equals(kind)){throw BusinessException.invalid("本接口接入image查询；身份和时间范围使用活动与历史查询接口");}
        OffsetDateTime from=body.get("start_at")==null?null:time(body,"start_at"),to=body.get("end_at")==null?null:time(body,"end_at");
        if(from!=null&&to!=null&&!to.isAfter(from)){throw BusinessException.invalid("查询时间范围无效");}
        List<String> sources=body.get("source_ids")==null?new ArrayList<>(actor.getSourceIds()):ids(body.get("source_ids"));actor.authorizedSources(sources);
        OffsetDateTime boundary=OffsetDateTime.now().plusDays(7);
        if("image".equals(kind)){if(asset==null){throw BusinessException.invalid("以图查询须上传临时素材");}Map<String,Object> a=data.recordings().asset(actor,asset);if(!"query_image".equals(a.get("asset_type"))){throw BusinessException.invalid("查询须使用query_image素材");}boundary=earlier(boundary,expiry(a));}
        if("identity".equals(kind)&&identity==null){throw BusinessException.invalid("身份查询须提供identity_id");}
        final OffsetDateTime expires=boundary;Map<String,Object> scope=values("schema_version","1","source_ids",sources,"object_types",java.util.Collections.singletonList(object),"start_at",from==null?null:iso(from),"end_at",to==null?null:iso(to));
        return data.store().write(actor,"queries.create",body,expires,jdbc->{
            if(identity!=null){data.identity(jdbc,actor,identity);}
            jdbc.update("INSERT INTO public.query_request(id,owner_user_id,query_kind,object_type,input_asset_id,identity_id,start_at,end_at,scope_json,expires_at) VALUES (?::uuid,?,?,?,?,?::uuid,?,?,?::jsonb,?)",id,actor.getUserId(),kind,object,asset==null?null:UUID.fromString(asset),identity,from,to,json(scope),expires);
            if(asset!=null){jdbc.update("INSERT INTO public.asset_reference(asset_id,query_id,retain_until) VALUES (?::uuid,?::uuid,?)",asset,id,expires);}
            return values("query_id",id,"state","pending","revision",1,"expires_at",iso(expires));
        });
    }

    Map<String,Object> query(BusinessActor actor,String id){Map<String,Object> q=one(data.store().jdbc().queryForList("SELECT * FROM public.query_request WHERE id=?::uuid",id),"查询不存在");fresh(q);SampleFeatureService.authorizeQuery(actor,q);return q;}
    public Map<String,Object> pending(BusinessActor actor,int limit){
        actor.requireOperation("queries.process");if(limit<1||limit>100){throw BusinessException.invalid("limit须为1至100");}
        List<Map<String,Object>> rows=data.store().jdbc().queryForList("SELECT id AS query_id,input_asset_id,input_sample_id,selected_candidate_id,object_type,revision,scope_json,expires_at FROM public.query_request WHERE query_kind='image' AND state='pending' AND expires_at>now() ORDER BY created_at,id LIMIT ?",limit);
        List<Map<String,Object>> items=new ArrayList<>();for(Map<String,Object> row:rows){
            Map<String,Object> scope=parse(row.get("scope_json").toString());boolean allowed=true;for(String source:ids(scope.get("source_ids"))){if(!actor.getSourceIds().contains(source)){allowed=false;}}
            if(allowed){items.add(clean(row));}
        }return values("items",items);
    }
    public Map<String,Object> get(BusinessActor actor,String id){id=uuid(id,"query_id");Map<String,Object> q=query(actor,id);
        q.put("candidates",data.store().jdbc().queryForList("SELECT candidate_id,sample_id::text,object_type,bbox_json,confidence FROM public.query_candidate WHERE query_id=?::uuid AND expires_at>now() ORDER BY candidate_id",id));for(Object value:list(q.get("candidates"))){clean(map(value));}
        q.put("hits",data.store().jdbc().queryForList("SELECT id AS hit_id,rank_no,hit_kind,identity_id,tracklet_id,sample_id,feature_id,feature_space_id,score,score_metric,basis_json,expires_at FROM public.search_hit WHERE query_id=?::uuid AND expires_at>now() ORDER BY rank_no",id));for(Object value:list(q.get("hits"))){clean(map(value));}return clean(q);
    }
    public Map<String,Object> candidates(BusinessActor actor,Map<String,Object> body){
        fields(body,"request_id","trace_id","query_id","expected_revision","candidates");String id=uuid(body,"query_id");Map<String,Object> initial=query(actor,id);List<Object> candidates=list(required(body,"candidates"));
        if(candidates.size()>100){throw BusinessException.invalid("单图候选数量超过100");}
        return data.store().write(actor,"queries.candidates",body,expiry(initial),jdbc->{
            Map<String,Object> q=one(jdbc.queryForList("SELECT * FROM public.query_request WHERE id=?::uuid FOR UPDATE",id),"查询不存在");SampleFeatureService.authorizeQuery(actor,q);fresh(q);revision(q,body);
            if(!"image".equals(q.get("query_kind"))||!"pending".equals(q.get("state"))){throw BusinessException.conflict("查询不再等待候选检测");}
            String selected=null,sample=null;
            for(Object value:candidates){Map<String,Object> c=map(value);fields(c,"candidate_id","sample_id","object_type","bbox","confidence");String candidate=text(c,"candidate_id",32),sampleId=uuid(c,"sample_id"),object=text(c,"object_type",64);double confidence=number(required(c,"confidence"));if(confidence<0||confidence>1){throw BusinessException.invalid("候选评分无效");}Map<String,Object> bbox=map(required(c,"bbox"));SampleFeatureService.box(bbox);Map<String,Object> s=data.sample(jdbc,actor,sampleId);
                if(!id.equals(String.valueOf(s.get("query_id")))||!object.equals(q.get("object_type"))){throw BusinessException.conflict("候选样本不属于本次查询或对象类别");}
                jdbc.update("INSERT INTO public.query_candidate(query_id,candidate_id,sample_id,object_type,bbox_json,confidence,expires_at) VALUES (?::uuid,?,?::uuid,?,?::jsonb,?,?)",id,candidate,sampleId,object,json(bbox),confidence,expiry(q));selected=candidate;sample=sampleId;
            }
            String state=candidates.isEmpty()?"succeeded":candidates.size()==1?"pending":"waiting_input";
            jdbc.update("UPDATE public.query_request SET state=?,selected_candidate_id=?,input_sample_id=?::uuid,revision=revision+1,updated_at=now() WHERE id=?::uuid",state,candidates.size()==1?selected:null,candidates.size()==1?sample:null,id);
            return values("query_id",id,"state",state,"revision",((Number)q.get("revision")).longValue()+1,"candidate_count",candidates.size(),"selected_candidate_id",candidates.size()==1?selected:null);
        });
    }
    public Map<String,Object> select(BusinessActor actor,Map<String,Object> body){
        fields(body,"request_id","trace_id","query_id","candidate_id","expected_revision");String id=uuid(body,"query_id"),candidate=text(body,"candidate_id",32);Map<String,Object> initial=query(actor,id);
        return data.store().write(actor,"queries.select",body,expiry(initial),jdbc->{
            Map<String,Object> q=one(jdbc.queryForList("SELECT * FROM public.query_request WHERE id=?::uuid FOR UPDATE",id),"查询不存在");fresh(q);SampleFeatureService.authorizeQuery(actor,q);revision(q,body);
            if(!"waiting_input".equals(q.get("state"))){throw BusinessException.conflict("查询不再等待目标选择");}
            Map<String,Object> c=one(jdbc.queryForList("SELECT sample_id FROM public.query_candidate WHERE query_id=?::uuid AND candidate_id=? AND expires_at>now()",id,candidate),"候选不存在或已到期");data.sample(jdbc,actor,c.get("sample_id").toString());
            jdbc.update("UPDATE public.query_request SET selected_candidate_id=?,input_sample_id=?::uuid,state='pending',revision=revision+1,updated_at=now() WHERE id=?::uuid",candidate,c.get("sample_id"),id);
            return values("query_id",id,"selected_candidate_id",candidate,"state","pending","revision",((Number)q.get("revision")).longValue()+1);
        });
    }

    public Map<String,Object> search(BusinessActor actor,Map<String,Object> body){
        fields(body,"request_id","trace_id","query_id","feature_id","threshold","limit","expected_revision");String id=uuid(body,"query_id"),feature=uuid(body,"feature_id");double threshold=number(required(body,"threshold"));if(threshold<0||threshold>1){throw BusinessException.invalid("threshold须为0至1");}int limit=body.containsKey("limit")?(int)integer(body,"limit",1,100):20;Map<String,Object> initial=query(actor,id);
        return data.store().write(actor,"search.execute",body,expiry(initial),jdbc->{
            Map<String,Object> q=one(jdbc.queryForList("SELECT * FROM public.query_request WHERE id=?::uuid FOR UPDATE",id),"查询不存在");fresh(q);SampleFeatureService.authorizeQuery(actor,q);revision(q,body);
            if(q.get("input_sample_id")==null||"waiting_input".equals(q.get("state"))){throw BusinessException.conflict("须先完成查询目标选择");}
            Map<String,Object> f=data.feature(jdbc,actor,feature);if(!q.get("input_sample_id").equals(f.get("sample_id"))){throw BusinessException.invalid("查询特征不属于已选择样本");}
            Map<String,Object> space=one(jdbc.queryForList("SELECT metric,object_type FROM public.feature_space WHERE id=? AND enabled",f.get("feature_space_id")),"特征空间未启用");if(!"cosine".equals(space.get("metric"))||!q.get("object_type").equals(space.get("object_type"))){throw BusinessException.invalid("查询须使用同对象cosine特征空间");}
            Map<String,Object> scope=parse(q.get("scope_json").toString());List<String> sources=ids(required(scope,"source_ids"));actor.authorizedSources(sources);
            OffsetDateTime from=q.get("start_at")==null?null:at(q.get("start_at")),to=q.get("end_at")==null?null:at(q.get("end_at"));
            String sql="WITH candidates AS (SELECT CASE WHEN s.purpose='enrollment' THEN 'gallery' ELSE 'historical' END AS hit_kind,COALESCE(a.identity_id,f.identity_id) AS identity_id,f.tracklet_id,s.id AS sample_id,f.id AS feature_id,1-(f.embedding <=> ?::vector) AS score,s.occurred_at,LEAST(f.expires_at,s.expires_at,t.expires_at) AS expires_at,row_number() OVER(PARTITION BY CASE WHEN s.purpose='enrollment' THEN 'gallery:'||f.identity_id::text ELSE 'historical:'||f.tracklet_id::text END ORDER BY f.embedding <=> ?::vector,f.id) AS choice FROM public.feature f JOIN LATERAL(SELECT s.* FROM public.feature_contribution c JOIN public.sample s ON s.id=c.sample_id WHERE c.feature_id=f.id ORDER BY c.ordinal LIMIT 1)s ON true LEFT JOIN public.tracklet t ON t.id=f.tracklet_id LEFT JOIN public.track_identity_assignment a ON a.tracklet_id=t.id AND a.valid_to IS NULL AND a.expires_at>now() LEFT JOIN public.identity i ON i.id=f.identity_id WHERE f.id<>?::uuid AND f.feature_space_id=? AND f.state='ready' AND (f.expires_at IS NULL OR f.expires_at>now()) AND s.available AND (s.expires_at IS NULL OR s.expires_at>now()) AND NOT EXISTS(SELECT 1 FROM public.feature_contribution c JOIN public.sample leaf ON leaf.id=c.sample_id WHERE c.feature_id=f.id AND (NOT leaf.available OR leaf.expires_at<=now())) AND ((s.purpose='enrollment' AND i.identity_kind='registered' AND i.enabled) OR (s.purpose='history' AND t.expires_at>now() AND t.source_id=ANY(?::uuid[]) AND (?::timestamptz IS NULL OR t.last_observed_at>=?) AND (?::timestamptz IS NULL OR t.first_observed_at<?)))) SELECT * FROM candidates WHERE choice=1 AND score>=? ORDER BY score DESC,feature_id LIMIT ?";
            List<Map<String,Object>> matches=jdbc.queryForList(sql,f.get("embedding").toString(),f.get("embedding").toString(),feature,f.get("feature_space_id"),pgArray(sources),from,from,to,to,threshold,limit);
            jdbc.update("DELETE FROM public.search_hit WHERE query_id=?::uuid",id);List<Map<String,Object>> hits=new ArrayList<>();int rank=1;
            for(Map<String,Object> match:matches){String hit=UUID.randomUUID().toString();OffsetDateTime expires=earlier(expiry(q),expiry(match));Map<String,Object> basis=values("schema_version","1","feature_space_id",f.get("feature_space_id"),"query_feature_id",feature);
                jdbc.update("INSERT INTO public.search_hit(id,query_id,rank_no,hit_kind,identity_id,tracklet_id,sample_id,feature_id,feature_space_id,score,score_metric,basis_json,expires_at) VALUES (?::uuid,?::uuid,?,?,?::uuid,?::uuid,?::uuid,?::uuid,?,?,'cosine_similarity',?::jsonb,?)",hit,id,rank,match.get("hit_kind"),match.get("identity_id"),match.get("tracklet_id"),match.get("sample_id"),match.get("feature_id"),f.get("feature_space_id"),match.get("score"),json(basis),expires);
                match.remove("choice");match.put("hit_id",hit);match.put("rank_no",rank++);match.put("expires_at",iso(expires));hits.add(clean(match));
            }
            Map<String,Object> coverage=values("schema_version","1","scope",scope,"searchable_feature_space_id",f.get("feature_space_id"));
            jdbc.update("UPDATE public.query_request SET state='succeeded',feature_space_id=?,coverage_json=?::jsonb,revision=revision+1,updated_at=now() WHERE id=?::uuid",f.get("feature_space_id"),json(coverage),id);
            return values("query_id",id,"state","succeeded","revision",((Number)q.get("revision")).longValue()+1,"feature_space_id",f.get("feature_space_id"),"hits",hits,"coverage",coverage);
        });
    }
}
