package edu.cqupt.hxjm.algdeployment.business.service;

import java.time.OffsetDateTime;
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
public class IdentityBusinessService {
    private final BusinessDataAccess data;
    public IdentityBusinessService(BusinessDataAccess data){this.data=data;}

    public Map<String,Object> register(BusinessActor actor,Map<String,Object> body){
        fields(body,"request_id","trace_id","identity_id","object_type","display_name","employee_id","enrollment_assets");
        String id=newId(body,"identity_id"),object=text(body,"object_type",64),name=optionalText(body,"display_name",200),employee=optionalText(body,"employee_id",64);
        List<Object> assets=body.get("enrollment_assets")==null?java.util.Collections.emptyList():list(body.get("enrollment_assets"));
        return data.store().write(actor,"identities.register",body,OffsetDateTime.now().plusDays(7),jdbc->{
            jdbc.update("INSERT INTO public.identity(id,identity_kind,object_type,display_name,employee_id,registered_at) VALUES (?::uuid,'registered',?,?,?,now())",id,object,name,employee);
            for(Object value:assets){Map<String,Object> input=map(value);fields(input,"asset_id","sample_id");String asset=uuid(input,"asset_id"),sample=newId(input,"sample_id");Map<String,Object> a=data.recordings().asset(actor,asset);
                if(!"enrollment_image".equals(a.get("asset_type"))||!"available".equals(a.get("state"))){throw BusinessException.invalid("登记须使用已保存的独立登记图片");}
                jdbc.update("INSERT INTO public.sample(id,purpose,asset_id,identity_id,occurred_at) VALUES (?::uuid,'enrollment',?::uuid,?::uuid,?)",sample,asset,id,a.get("start_ts"));
                jdbc.update("INSERT INTO public.asset_reference(asset_id,sample_id,retain_until) VALUES (?::uuid,?::uuid,NULL)",asset,sample);
                data.store().event(jdbc,"sample.registered","sample",sample,1,values("sample_id",sample,"identity_id",id,"purpose","enrollment"),OffsetDateTime.now().plusDays(7));
            }
            return summary(jdbc,id);
        });
    }

    public Map<String,Object> associate(BusinessActor actor,Map<String,Object> body){
        fields(body,"request_id","trace_id","tracklet_id","feature_id","run_id","threshold");
        String track=uuid(body,"tracklet_id"),feature=uuid(body,"feature_id"),run=uuid(body,"run_id");
        double threshold=number(required(body,"threshold"));if(threshold<0||threshold>1){throw BusinessException.invalid("threshold须为0至1");}
        Map<String,Object> initial=data.track(data.store().jdbc(),actor,track);
        return data.store().write(actor,"identities.associate",body,expiry(initial),jdbc->{
            data.run(jdbc,actor,run);
            Map<String,Object> t=data.track(jdbc,actor,track);String canonical=t.get("id").toString();
            if(t.get("first_observed_at")==null||t.get("last_observed_at")==null){throw BusinessException.conflict("纯预测轨迹不能建立身份");}
            Map<String,Object> f=data.feature(jdbc,actor,feature);
            if(!canonical.equals(String.valueOf(f.get("tracklet_id")))){throw BusinessException.invalid("特征不属于指定轨迹");}
            Map<String,Object> space=one(jdbc.queryForList("SELECT * FROM public.feature_space WHERE id=? AND enabled",f.get("feature_space_id")),"特征空间未启用");
            if(!"cosine".equals(space.get("metric"))){throw BusinessException.invalid("自动归属当前接入cosine空间");}
            String type=space.get("object_type").toString();
            jdbc.queryForObject("SELECT pg_advisory_xact_lock(hashtextextended(?,0)) IS NULL",Boolean.class,"identity-space:"+f.get("feature_space_id"));
            jdbc.queryForList("SELECT id FROM public.tracklet WHERE id=?::uuid FOR UPDATE",canonical);
            List<Map<String,Object>> current=jdbc.queryForList("SELECT id,identity_id FROM public.track_identity_assignment WHERE tracklet_id=?::uuid AND valid_to IS NULL FOR UPDATE",canonical);
            if(!current.isEmpty()){
                String identity=current.get(0).get("identity_id").toString();data.identity(jdbc,actor,identity);
                OffsetDateTime first=at(t.get("first_observed_at")),last=at(t.get("last_observed_at"));
                jdbc.update("UPDATE public.identity SET first_seen_at=LEAST(first_seen_at,?),last_seen_at=GREATEST(last_seen_at,?),expires_at=GREATEST(last_seen_at,?)+interval '7 days',revision=revision+1,updated_at=now() WHERE id=?::uuid AND identity_kind='temporary' AND expires_at>now()",first,last,last,identity);
                jdbc.update("UPDATE public.identity_link SET expires_at=GREATEST(expires_at,?) WHERE temporary_identity_id=?::uuid AND valid_to IS NULL",last.plusDays(7),identity);
                jdbc.update("UPDATE public.track_identity_assignment SET expires_at=? WHERE id=?::uuid",expiry(t),current.get(0).get("id"));
                jdbc.update("UPDATE public.feature SET identity_id=?::uuid WHERE id=?::uuid",identity,feature);
                String activity=activity(jdbc,identity,t);
                return values("identity_id",identity,"assignment_id",current.get(0).get("id").toString(),"activity_id",activity,"created",false,"duplicate",true);
            }
            List<Map<String,Object>> matches=jdbc.queryForList("SELECT i.id,i.identity_kind,1-(f.embedding <=> ?::vector) AS score FROM public.feature f JOIN public.identity i ON i.id=f.identity_id LEFT JOIN public.tracklet t ON t.id=f.tracklet_id WHERE f.id<>?::uuid AND f.feature_space_id=? AND f.state='ready' AND (f.expires_at IS NULL OR f.expires_at>now()) AND i.enabled AND i.object_type=? AND (i.expires_at IS NULL OR i.expires_at>now()) AND (i.identity_kind='registered' OR t.source_id=ANY(?::uuid[])) AND NOT EXISTS(SELECT 1 FROM public.feature_contribution c JOIN public.sample s ON s.id=c.sample_id WHERE c.feature_id=f.id AND (NOT s.available OR s.expires_at<=now())) ORDER BY score DESC,i.id LIMIT 1",f.get("embedding").toString(),feature,f.get("feature_space_id"),type,pgArray(actor.getSourceIds()));
            String identity=null,registered=null;Double score=null;boolean created=false;
            if(!matches.isEmpty()&&number(matches.get(0).get("score"))>=threshold){
                Map<String,Object> match=matches.get(0);score=number(match.get("score"));
                if("temporary".equals(match.get("identity_kind"))){identity=match.get("id").toString();}
                else{
                    registered=match.get("id").toString();
                    List<Map<String,Object>> linked=jdbc.queryForList("SELECT i.id FROM public.identity_link l JOIN public.identity i ON i.id=l.temporary_identity_id WHERE l.registered_identity_id=?::uuid AND l.valid_to IS NULL AND l.expires_at>now() AND i.enabled AND i.expires_at>now() ORDER BY i.last_seen_at DESC,i.id LIMIT 1 FOR UPDATE OF i",registered);
                    if(!linked.isEmpty()){identity=linked.get(0).get("id").toString();}
                }
            }
            OffsetDateTime first=at(t.get("first_observed_at")),last=at(t.get("last_observed_at"));
            if(identity==null){
                identity=UUID.randomUUID().toString();created=true;
                jdbc.update("INSERT INTO public.identity(id,identity_kind,object_type,first_seen_at,last_seen_at,expires_at) VALUES (?::uuid,'temporary',?,?,?,?)",identity,type,first,last,last.plusDays(7));
            }else{
                jdbc.update("UPDATE public.identity SET first_seen_at=LEAST(first_seen_at,?),last_seen_at=GREATEST(last_seen_at,?),expires_at=GREATEST(last_seen_at,?)+interval '7 days',revision=revision+1,updated_at=now() WHERE id=?::uuid AND expires_at>now()",first,last,last,identity);
            }
            if(registered!=null){
                jdbc.update("INSERT INTO public.identity_link(temporary_identity_id,registered_identity_id,valid_from,basis_type,score,run_id,expires_at) VALUES (?::uuid,?::uuid,now(),'feature_match',?,?::uuid,?) ON CONFLICT (temporary_identity_id) WHERE valid_to IS NULL DO UPDATE SET expires_at=GREATEST(identity_link.expires_at,EXCLUDED.expires_at)",identity,registered,score,run,last.plusDays(7));
            }
            String assignment=UUID.randomUUID().toString();
            jdbc.update("INSERT INTO public.track_identity_assignment(id,tracklet_id,identity_id,valid_from,basis_type,score,run_id,expires_at) VALUES (?::uuid,?::uuid,?::uuid,now(),'cross_camera_match',?,?::uuid,?)",assignment,canonical,identity,score,run,expiry(t));
            jdbc.update("UPDATE public.feature SET identity_id=?::uuid WHERE id=?::uuid",identity,feature);
            String activity=activity(jdbc,identity,t);
            data.store().event(jdbc,"identity.associated","identity",identity,((Number)summary(jdbc,identity).get("revision")).longValue(),values("identity_id",identity,"tracklet_id",canonical,"activity_id",activity),last.plusDays(7));
            return values("identity_id",identity,"registered_identity_id",registered,"assignment_id",assignment,"activity_id",activity,"score",score,"created",created);
        });
    }

    public Map<String,Object> get(BusinessActor actor,String id){id=uuid(id,"identity_id");data.identity(data.store().jdbc(),actor,id);Map<String,Object> value=summary(data.store().jdbc(),id);
        value.put("tracks",data.store().jdbc().queryForList("SELECT a.tracklet_id::text,t.source_id::text,t.first_observed_at,t.last_observed_at FROM public.track_identity_assignment a JOIN public.tracklet t ON t.id=a.tracklet_id WHERE (a.identity_id=?::uuid OR EXISTS(SELECT 1 FROM public.identity_link l WHERE l.temporary_identity_id=a.identity_id AND l.registered_identity_id=?::uuid AND l.valid_to IS NULL AND l.expires_at>now())) AND a.valid_to IS NULL AND a.expires_at>now() AND t.expires_at>now() AND t.source_id=ANY(?::uuid[]) ORDER BY t.first_observed_at,t.id",id,id,pgArray(actor.getSourceIds())));
        value.put("links",data.store().jdbc().queryForList("SELECT temporary_identity_id::text,registered_identity_id::text,basis_type,score FROM public.identity_link WHERE (temporary_identity_id=?::uuid OR registered_identity_id=?::uuid) AND valid_to IS NULL AND expires_at>now()",id,id));
        for(Object item:list(value.get("tracks"))){clean(map(item));}return value;
    }

    public Map<String,Object> query(BusinessActor actor,Map<String,Object> body){
        return new BusinessDiscoveryService(data,new ActivityBusinessService(data)).identities(actor,body);
    }

    static Map<String,Object> summary(JdbcTemplate jdbc,String id){return clean(one(jdbc.queryForList("SELECT id AS identity_id,identity_kind,object_type,display_no,display_name,employee_id,registered_at,first_seen_at,last_seen_at,enabled,revision,expires_at FROM public.identity WHERE id=?::uuid",id),"身份不存在"));}

    static String activity(JdbcTemplate jdbc,String identity,Map<String,Object> track){
        jdbc.queryForList("SELECT id FROM public.identity WHERE id=?::uuid FOR UPDATE",identity);
        List<Map<String,Object>> linked=jdbc.queryForList("SELECT e.id,e.state FROM public.episode e JOIN public.episode_tracklet_link l ON l.episode_id=e.id WHERE e.identity_id=?::uuid AND l.tracklet_id=?::uuid AND e.expires_at>now() ORDER BY e.start_ts,e.id LIMIT 1 FOR UPDATE OF e",identity,track.get("id"));
        if(!linked.isEmpty()&&!"open".equals(linked.get(0).get("state"))){return linked.get(0).get("id").toString();}
        List<Map<String,Object>> open=linked.isEmpty()?jdbc.queryForList("SELECT id FROM public.episode WHERE identity_id=?::uuid AND activity_type='person_activity' AND state='open' AND expires_at>now() ORDER BY start_ts,id FOR UPDATE",identity):linked;
        OffsetDateTime first=at(track.get("first_observed_at")),last=at(track.get("last_observed_at"));String id;
        if(open.isEmpty()){
            id=UUID.randomUUID().toString();jdbc.update("INSERT INTO public.episode(id,title,start_ts,end_ts,identity_id,activity_type,state,coverage_json,revision,expires_at) VALUES (?::uuid,'人员活动',?,?,?::uuid,'person_activity','open','{}'::jsonb,1,?)",id,first,last,identity,last.plusDays(7));
        }else{id=open.get(0).get("id").toString();jdbc.update("UPDATE public.episode SET start_ts=LEAST(start_ts,?),end_ts=GREATEST(end_ts,?),expires_at=GREATEST(end_ts,?)+interval '7 days',revision=revision+1 WHERE id=?::uuid",first,last,last,id);}
        jdbc.update("INSERT INTO public.episode_tracklet_link(episode_id,tracklet_id) SELECT ?::uuid,?::uuid WHERE NOT EXISTS(SELECT 1 FROM public.episode_tracklet_link WHERE episode_id=?::uuid AND tracklet_id=?::uuid)",id,track.get("id"),id,track.get("id"));
        return id;
    }
}
