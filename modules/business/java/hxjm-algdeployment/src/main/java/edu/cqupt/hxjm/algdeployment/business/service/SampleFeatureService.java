package edu.cqupt.hxjm.algdeployment.business.service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.OffsetDateTime;
import java.util.ArrayList;
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
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;
import static edu.cqupt.hxjm.algdeployment.business.service.BusinessDataAccess.*;

@Service
@ConditionalOnProperty(prefix="hxjm.business",name="enabled",havingValue="true")
public class SampleFeatureService {
    private final BusinessDataAccess data;
    public SampleFeatureService(BusinessDataAccess data){this.data=data;}

    public Map<String,Object> sample(BusinessActor actor,Map<String,Object> body){
        fields(body,"request_id","trace_id","sample_id","purpose","asset_id","input_frame_id","tracklet_id","identity_id","query_id","occurred_at","bbox","quality","expires_at");
        String id=newId(body,"sample_id"),purpose=text(body,"purpose",16),asset=uuid(body,"asset_id");
        if(!Arrays.asList("history","enrollment","query","evidence").contains(purpose)){throw BusinessException.invalid("样本用途无效");}
        OffsetDateTime occurred=time(body,"occurred_at");
        OffsetDateTime expires=body.get("expires_at")==null?null:time(body,"expires_at");
        if(!"enrollment".equals(purpose)&&expires==null){throw BusinessException.invalid("临时样本必须提供期限");}
        String frame=optionalId(body,"input_frame_id"),track=optionalId(body,"tracklet_id"),identity=optionalId(body,"identity_id"),query=optionalId(body,"query_id");
        Map<String,Object> bbox=object(body,"bbox"),quality=object(body,"quality");box(bbox);
        return data.store().write(actor,"samples.register",body,requestExpiry(expires),jdbc->{
            Map<String,Object> assetRow=data.recordings().asset(actor,asset);
            if(!"available".equals(assetRow.get("state"))||!String.valueOf(assetRow.get("content_type")).startsWith("image/")){throw BusinessException.conflict("样本资产须为可用图片");}
            if(expires!=null&&expiry(assetRow)!=null&&expires.isAfter(expiry(assetRow))){throw BusinessException.invalid("样本不得超过资产用途期限");}
            if("history".equals(purpose)){
                if(frame==null||track==null||expires.isAfter(occurred.plusDays(7))){throw BusinessException.invalid("历史样本必须引用帧及轨迹并保留原期限");}
                Map<String,Object> t=data.track(jdbc,actor,track);
                if(!track.equals(t.get("id").toString())){throw BusinessException.invalid("样本须引用规范轨迹");}
                Map<String,Object> f=one(jdbc.queryForList("SELECT * FROM public.input_frame WHERE id=?::uuid",frame),"样本原帧不存在");fresh(f);
                if(!occurred.equals(at(f.get("occurred_at")))||!f.get("stream_session_id").equals(t.get("stream_session_id"))){throw BusinessException.conflict("样本帧、轨迹和发生时间不一致");}
                if(jdbc.queryForList("SELECT 1 FROM public.detection_observation o JOIN public.analysis_frame a ON a.id=o.analysis_frame_id WHERE a.input_frame_id=?::uuid AND o.tracklet_id=?::uuid AND o.observation_kind='observed' AND o.expires_at>now()",frame,track).isEmpty()){throw BusinessException.conflict("历史样本没有实际观测依据");}
            }
            if("enrollment".equals(purpose)){
                actor.requireOperation("identities.register");if(identity==null){throw BusinessException.invalid("登记样本必须指定正式身份");}
                if(!"registered".equals(data.identity(jdbc,actor,identity).get("identity_kind"))||!"enrollment_image".equals(assetRow.get("asset_type"))){throw BusinessException.invalid("永久样本必须使用独立登记身份及登记图片");}
            }else if(identity!=null){data.identity(jdbc,actor,identity);}
            if("query".equals(purpose)){
                if(query==null){throw BusinessException.invalid("查询样本必须引用查询");}
                Map<String,Object> q=one(jdbc.queryForList("SELECT * FROM public.query_request WHERE id=?::uuid",query),"查询不存在");fresh(q);authorizeQuery(actor,q);
                if(expires.isAfter(expiry(q))||!asset.equals(String.valueOf(q.get("input_asset_id")))&&!"crop".equals(assetRow.get("asset_type"))){throw BusinessException.invalid("查询样本超出素材范围或期限");}
            }
            if(!jdbc.queryForList("SELECT id FROM public.sample WHERE id=?::uuid",id).isEmpty()){throw BusinessException.conflict("样本标识已存在，请重试原request_id");}
            jdbc.update("INSERT INTO public.sample(id,purpose,asset_id,input_frame_id,tracklet_id,identity_id,query_id,occurred_at,bbox_json,quality_json,expires_at) VALUES (?::uuid,?,?::uuid,?::uuid,?::uuid,?::uuid,?::uuid,?,?::jsonb,?::jsonb,?)",id,purpose,asset,frame,track,identity,query,occurred,json(bbox),json(quality),expires);
            jdbc.update("INSERT INTO public.asset_reference(asset_id,sample_id,retain_until) VALUES (?::uuid,?::uuid,?)",asset,id,expires);
            data.store().event(jdbc,"sample.registered","sample",id,1,values("sample_id",id,"tracklet_id",track,"purpose",purpose),requestExpiry(expires));
            return values("sample_id",id,"asset_id",asset,"purpose",purpose,"available",true,"expires_at",expires==null?null:iso(expires));
        });
    }

    public Map<String,Object> space(BusinessActor actor,Map<String,Object> body){
        fields(body,"request_id","trace_id","feature_space_id","definition_text","definition_version","definition_sha256","object_type","feature_kind","dimensions","dtype","normalization","metric");
        String id=text(body,"feature_space_id",128),definition=documentText(body,"definition_text",131072),version=text(body,"definition_version",32),digest=text(body,"definition_sha256",64);
        Map<String,Object> definitionJson=parse(definition);
        if(!sha(definition).equals(digest)||!(id.equals("fs-"+digest)||id.equals("clipreid-rn50-"+digest.substring(0,24)))){throw BusinessException.invalid("特征空间ID或摘要与完整定义不一致");}
        int dimensions=(int)integer(body,"dimensions",1,16000);
        String object=text(body,"object_type",64),kind=text(body,"feature_kind",32),dtype=text(body,"dtype",16),normal=text(body,"normalization",16),metric=text(body,"metric",16);
        if(!"float32".equals(dtype)||!Arrays.asList("l2","none").contains(normal)||!Arrays.asList("cosine","l2","inner_product").contains(metric)){throw BusinessException.invalid("特征数值或度量定义无效");}
        return data.store().write(actor,"feature_spaces.register",body,OffsetDateTime.now().plusDays(7),jdbc->{
            List<Map<String,Object>> existing=jdbc.queryForList("SELECT * FROM public.feature_space WHERE id=? OR definition_sha256=? FOR UPDATE",id,digest);
            if(!existing.isEmpty()){
                Map<String,Object> old=existing.get(0);
                if(!id.equals(old.get("id"))||!definition.equals(old.get("definition_text"))||dimensions!=((Number)old.get("dimensions")).intValue()||!object.equals(old.get("object_type"))||!kind.equals(old.get("feature_kind"))||!normal.equals(old.get("normalization"))||!metric.equals(old.get("metric"))||!version.equals(old.get("definition_version"))){throw BusinessException.conflict("特征空间定义不可原地变更");}
                return values("feature_space_id",id,"dimensions",dimensions,"duplicate",true);
            }
            jdbc.update("INSERT INTO public.feature_space(id,definition_sha256,definition_version,definition_text,definition_json,object_type,feature_kind,dimensions,dtype,normalization,metric) VALUES (?,?,?,?,?::jsonb,?,?,?,?,?,?)",id,digest,version,definition,json(definitionJson),object,kind,dimensions,dtype,normal,metric);
            return values("feature_space_id",id,"dimensions",dimensions);
        });
    }

    public Map<String,Object> feature(BusinessActor actor,Map<String,Object> body){
        fields(body,"request_id","trace_id","feature_id","feature_space_id","run_id","producer_feature_key","embedding","sample_id","tracklet_id","identity_id","aggregation_method","input_count","used_count","contributions","processed_at","expires_at");
        String id=newId(body,"feature_id"),space=text(body,"feature_space_id",128),run=uuid(body,"run_id"),key=text(body,"producer_feature_key",128),method=text(body,"aggregation_method",32);
        String sample=optionalId(body,"sample_id"),track=optionalId(body,"tracklet_id"),identity=optionalId(body,"identity_id");
        List<Object> vector=list(required(body,"embedding")),contributions=list(required(body,"contributions"));
        if(vector.isEmpty()||vector.size()>16000){throw BusinessException.invalid("向量维度无效");}double norm=0;for(Object value:vector){double n=number(value);if(!Float.isFinite((float)n)){throw BusinessException.invalid("向量须为有限float32");}norm+=n*n;}
        if(norm<1e-20){throw BusinessException.invalid("不能登记零向量");}final double length=Math.sqrt(norm);
        long input=integer(body,"input_count",1,Integer.MAX_VALUE),used=integer(body,"used_count",1,input);
        if(used!=contributions.size()||!("single".equals(method)&&sample!=null&&used==1||"mean_l2_v1".equals(method)&&sample==null)){throw BusinessException.invalid("聚合方式、样本及贡献数量不一致");}
        OffsetDateTime processed=time(body,"processed_at"),expires=body.get("expires_at")==null?null:time(body,"expires_at");
        return data.store().write(actor,"features.register",body,requestExpiry(expires),jdbc->{
            data.run(jdbc,actor,run);
            Map<String,Object> s=one(jdbc.queryForList("SELECT * FROM public.feature_space WHERE id=? AND enabled",space),"特征空间未启用");
            if(vector.size()!=((Number)s.get("dimensions")).intValue()||"l2".equals(s.get("normalization"))&&Math.abs(length-1)>0.001){throw BusinessException.invalid("向量维度或归一化不符合空间定义");}
            if(track!=null){data.track(jdbc,actor,track);}if(identity!=null){data.identity(jdbc,actor,identity);}
            Set<String> unique=new HashSet<>();OffsetDateTime boundary=null;boolean permanent=true;
            for(Object value:contributions){
                Map<String,Object> c=map(value);fields(c,"sample_id","source_feature_id");String leaf=uuid(c,"sample_id");if(!unique.add(leaf)){throw BusinessException.invalid("同一样本不能重复贡献");}
                Map<String,Object> leafRow=data.sample(jdbc,actor,leaf);boundary=earlier(boundary,expiry(leafRow));permanent&="enrollment".equals(leafRow.get("purpose"));
                if(track!=null&&!track.equals(String.valueOf(leafRow.get("tracklet_id")))){throw BusinessException.conflict("贡献样本不属于指定轨迹");}
                if(sample!=null&&!sample.equals(leaf)){throw BusinessException.invalid("单样本向量的贡献与sample_id不一致");}
                if(c.get("source_feature_id")!=null){Map<String,Object> source=data.feature(jdbc,actor,uuid(c,"source_feature_id"));if(!"single".equals(source.get("aggregation_method"))||!space.equals(source.get("feature_space_id"))||!leaf.equals(String.valueOf(source.get("sample_id")))){throw BusinessException.conflict("贡献特征须为同空间同样本单向量");}}
            }
            if(expires==null&&!permanent||expires!=null&&boundary!=null&&expires.isAfter(boundary)){throw BusinessException.invalid("特征不得延长贡献样本期限");}
            List<Map<String,Object>> old=jdbc.queryForList("SELECT id FROM public.feature WHERE id=?::uuid OR (run_id=?::uuid AND producer_feature_key=?)",id,run,key);
            if(!old.isEmpty()){throw BusinessException.conflict("特征产物已登记，请复用原request_id");}
            jdbc.update("INSERT INTO public.feature(id,feature_space_id,dimensions,embedding,sample_id,tracklet_id,identity_id,run_id,producer_feature_key,aggregation_method,input_count,used_count,processed_at,expires_at) VALUES (?::uuid,?,?,?::vector,?::uuid,?::uuid,?::uuid,?::uuid,?,?,?,?,?,?)",id,space,vector.size(),json(vector),sample,track,identity,run,key,method,input,used,processed,expires);
            int ordinal=0;for(Object value:contributions){Map<String,Object> c=map(value);jdbc.update("INSERT INTO public.feature_contribution(feature_id,ordinal,sample_id,source_feature_id) VALUES (?::uuid,?,?::uuid,?::uuid)",id,ordinal++,uuid(c,"sample_id"),optionalId(c,"source_feature_id"));}
            data.store().event(jdbc,"feature.registered","feature",id,1,values("feature_id",id,"feature_space_id",space,"tracklet_id",track),requestExpiry(expires));
            return values("feature_id",id,"feature_space_id",space,"dimensions",vector.size(),"used_count",used,"state","ready","expires_at",expires==null?null:iso(expires));
        });
    }

    public Map<String,Object> samples(BusinessActor actor,Map<String,Object> body){
        fields(body,"tracklet_id","purpose","limit","trace_id");String track=uuid(body,"tracklet_id");data.track(data.store().jdbc(),actor,track);
        int limit=body.containsKey("limit")?(int)integer(body,"limit",1,500):100;
        String purpose=optionalText(body,"purpose",16);
        List<Map<String,Object>> rows=data.store().jdbc().queryForList("SELECT id,asset_id,purpose,occurred_at,bbox_json,quality_json,expires_at FROM public.sample WHERE tracklet_id=?::uuid AND available AND (expires_at IS NULL OR expires_at>now()) AND (?::text IS NULL OR purpose=?) ORDER BY occurred_at,id LIMIT ?",track,purpose,purpose,limit);
        for(Map<String,Object> row:rows){clean(row);}return values("items",rows);
    }
    public Map<String,Object> pending(BusinessActor actor,String purpose,String space,int limit){
        if(!"enrollment".equals(purpose)||limit<1||limit>100){throw BusinessException.invalid("待处理样本当前支持enrollment且limit为1至100");}
        actor.requireOperation("samples.process");
        List<Map<String,Object>> rows=data.store().jdbc().queryForList("SELECT s.id AS sample_id,s.asset_id,s.identity_id,i.object_type,s.occurred_at,s.expires_at FROM public.sample s JOIN public.identity i ON i.id=s.identity_id JOIN public.media_asset a ON a.id=s.asset_id WHERE s.purpose='enrollment' AND s.available AND i.enabled AND a.state='available' AND (s.expires_at IS NULL OR s.expires_at>now()) AND NOT EXISTS(SELECT 1 FROM public.feature f WHERE f.sample_id=s.id AND f.state='ready' AND (f.expires_at IS NULL OR f.expires_at>now()) AND (?::text IS NULL OR f.feature_space_id=?)) ORDER BY s.created_at,s.id LIMIT ?",space,space,limit);
        for(Map<String,Object> row:rows){data.recordings().asset(actor,row.get("asset_id").toString());clean(row);}return values("items",rows);
    }

    static void box(Map<String,Object> bbox){
        if(bbox.isEmpty()){return;}fields(bbox,"schema_version","xyxy","source_width","source_height");
        if(!"1".equals(text(bbox,"schema_version",16))){throw BusinessException.invalid("bbox版本无效");}integer(bbox,"source_width",1,Integer.MAX_VALUE);integer(bbox,"source_height",1,Integer.MAX_VALUE);
        List<Object> v=list(required(bbox,"xyxy"));if(v.size()!=4){throw BusinessException.invalid("bbox必须四项xyxy");}
        double a=number(v.get(0)),b=number(v.get(1)),c=number(v.get(2)),d=number(v.get(3));if(a<0||b<0||c>1||d>1||c<=a||d<=b){throw BusinessException.invalid("bbox须为有正面积的归一化xyxy");}
    }
    static void authorizeQuery(BusinessActor actor,Map<String,Object> query){
        if(actor.isService()){actor.requireOperation("queries.process");return;}
        Object owner=query.get("owner_user_id");
        if(actor.isShared()&&owner==null){return;}
        if(actor.getUserId()==null||!(owner instanceof Number)||((Number)owner).longValue()!=actor.getUserId()){throw BusinessException.forbidden();}
    }
    static String sha(String value){try{byte[] raw=MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));StringBuilder out=new StringBuilder();for(byte b:raw){out.append(String.format("%02x",b&255));}return out.toString();}catch(Exception failure){throw new IllegalStateException(failure);}}
}
