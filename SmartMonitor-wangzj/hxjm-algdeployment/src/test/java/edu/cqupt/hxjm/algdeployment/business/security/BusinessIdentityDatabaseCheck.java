package edu.cqupt.hxjm.algdeployment.business.security;

import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import javax.imageio.ImageIO;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.service.*;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessStore;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

/** Real production services against synthetic data in the isolated migration database. */
public class BusinessIdentityDatabaseCheck {
    private static BusinessStore store;
    private static BusinessActor service,user;
    private static SampleFeatureService features;
    private static ImageAssetService images;
    private static byte[] image;
    private static String space;
    public static void main(String[] args)throws Exception{
        String url=System.getenv("HXJM_TEST_JDBC_URL");
        if(!"1".equals(System.getenv("HXJM_ISOLATED_TEST"))||url==null||!url.matches("jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/hxjm_stage2_[a-z0-9_]+")){throw new IllegalArgumentException("Explicit disposable stage-two database required");}
        store=new BusinessStore(new DriverManagerDataSource(url,System.getenv("HXJM_TEST_DB_USER"),System.getenv("HXJM_TEST_DB_PASSWORD")));
        Path root=Files.createTempDirectory(Paths.get("/data/nfs_storage/hxjm"),".test-identity-");
        try{
            String source1=id(),source2=id();BusinessSecurityProperties.Grant grant=new BusinessSecurityProperties.Grant();
            grant.setSourceIds(new HashSet<>(Arrays.asList(source1,source2)));grant.setOperations(new HashSet<>(Arrays.asList("results.register","assets.upload","assets.process","identities.query","identities.register","samples.register","samples.query","feature_spaces.register","features.register","identities.associate","activities.close","activities.query","reports.register","reports.query","events.register","queries.process","queries.create","queries.candidates","queries.select","search.execute","tasks.finish")));
            service=new BusinessActor("service:stage2",null,"stage2",grant);user=new BusinessActor("user:71",71L,null,grant);
            images=new ImageAssetService(store,root.toString());RecordingService recordings=new RecordingService(store,root.toString());
            BusinessDataAccess data=new BusinessDataAccess(store,recordings);features=new SampleFeatureService(data);IdentityBusinessService identities=new IdentityBusinessService(data);ActivityBusinessService activities=new ActivityBusinessService(data);BusinessSearchService search=new BusinessSearchService(data);List<String> reportFailures=new ArrayList<>();
            BufferedImage picture=new BufferedImage(20,30,BufferedImage.TYPE_INT_RGB);picture.setRGB(1,1,0xff00);ByteArrayOutputStream bytes=new ByteArrayOutputStream();ImageIO.write(picture,"png",bytes);image=bytes.toByteArray();
            String definition="{\"synthetic\":\""+id()+"\"}";byte[] digest=MessageDigest.getInstance("SHA-256").digest(definition.getBytes(StandardCharsets.UTF_8));StringBuilder hex=new StringBuilder();for(byte b:digest){hex.append(String.format("%02x",b&255));}space="fs-"+hex;
            features.space(service,values("request_id",id(),"feature_space_id",space,"definition_text",definition,"definition_sha256",hex.toString(),"definition_version","canonical_json_v1","object_type","person","feature_kind","body_appearance","dimensions",3,"dtype","float32","normalization","l2","metric","cosine"));
            check(store.jdbc().queryForObject("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='input_frame' AND column_name='source_id'",Long.class)==0,"frame source is derived from its input session");
            Map<String,Object> first=frame(source1),second=frame(source2);
            Map<String,Object> f1=history(first),f2=history(second);
            check(store.jdbc().queryForObject("SELECT count(*) FROM public.media_asset WHERE asset_type='crop' AND source_id IN (?::uuid,?::uuid) AND stream_session_id IS NOT NULL",Long.class,source1,source2)==2,"history image upload derives source from session without a duplicated frame source column");
            Map<String,Object> assoc=values("request_id",id(),"tracklet_id",first.get("tracklet_id"),"feature_id",f1.get("feature_id"),"run_id",first.get("run_id"),"threshold",0.8);
            Map<String,Object> a1=identities.associate(service,assoc);
            check(Boolean.TRUE.equals(identities.associate(service,assoc).get("duplicate")),"association replay");
            Map<String,Object> a2=identities.associate(service,values("request_id",id(),"tracklet_id",second.get("tracklet_id"),"feature_id",f2.get("feature_id"),"run_id",second.get("run_id"),"threshold",0.8));
            check(a1.get("identity_id").equals(a2.get("identity_id")),"cross-source temporary identity");check(a1.get("activity_id").equals(a2.get("activity_id")),"cross-source activity");
            OffsetDateTime seen=OffsetDateTime.parse(identities.get(user,a1.get("identity_id").toString()).get("last_seen_at").toString());
            nextFrame(first,2,true);
            check(seen.equals(OffsetDateTime.parse(identities.get(user,a1.get("identity_id").toString()).get("last_seen_at").toString())),"prediction cannot extend identity observation time");
            OffsetDateTime observed=nextFrame(first,3,false);
            Map<String,Object> continued=identities.get(user,a1.get("identity_id").toString());
            check(observed.equals(OffsetDateTime.parse(continued.get("last_seen_at").toString())),"real saved frame refreshes identity time");
            check(observed.plusDays(7).equals(OffsetDateTime.parse(continued.get("expires_at").toString())),"real saved frame refreshes identity lifetime");
            check(store.jdbc().queryForObject("SELECT expires_at>=? FROM public.track_identity_assignment WHERE tracklet_id=?::uuid AND valid_to IS NULL",Boolean.class,observed.plusDays(7),first.get("tracklet_id")),"current assignment follows real observation");
            Map<String,Object> activity=activities.getActivity(user,a1.get("activity_id").toString());check(list(activity.get("tracks")).size()==2,"complete route has both tracks");
            LocalActivityReportService localReports=new LocalActivityReportService(data);
            check(localReports.refresh(10,OffsetDateTime.now())==1,"idle activity automatically closes and reports");
            Map<String,Object> closed=activities.getActivity(user,a1.get("activity_id").toString());check("closed".equals(closed.get("state")),"normal activity closes");
            String localReport=store.jdbc().queryForObject("SELECT id::text FROM public.llm_report WHERE subject_kind='activity' AND subject_id=?::uuid AND report_type='person_route'",String.class,a1.get("activity_id"));
            Map<String,Object> local=activities.getReport(user,localReport);check("partial".equals(local.get("completeness")),"recording gap remains visible");
            check(list(map(local.get("report_json")).get("route")).size()==2,"local report includes both source appearances");
            check(localReports.refresh(10,OffsetDateTime.now())==0,"unchanged report is not revised on polling");
            store.jdbc().update("UPDATE public.processing_coverage SET revision=revision+1 WHERE stream_session_id=(SELECT stream_session_id FROM public.tracklet WHERE id=?::uuid)",first.get("tracklet_id"));
            check(localReports.refresh(10,OffsetDateTime.now())==1,"persisted coverage change refreshes report");
            check(((Number)activities.getReport(user,localReport).get("revision")).longValue()==2,"local report keeps stable id and increments revision");
            check(store.jdbc().queryForObject("SELECT count(*) FROM public.report_evidence_link WHERE report_id=?::uuid",Long.class,localReport)==2,"factual evidence linked atomically");
            store.jdbc().update("DELETE FROM public.report_evidence_link WHERE report_id=?::uuid",localReport);
            store.jdbc().update("DELETE FROM public.llm_report WHERE id=?::uuid",localReport);
            Map<String,Object> repeated=with(assoc,"request_id",id());check(a1.get("activity_id").equals(identities.associate(service,repeated).get("activity_id")),"late feature cannot duplicate a closed activity");
            String event=id();Map<String,Object> eventBody=values("request_id",id(),"event_id",event,"event_type","synthetic.alert","event_key",event,"source_id",source1,"start_at",first.get("occurred_at"),"end_at",first.get("occurred_at"),"state","closed","end_reason","normal","conclusion",values("schema_version","1","label","synthetic"),"run_id",first.get("run_id"),"objects",Collections.singletonList(values("identity_id",a1.get("identity_id"))));
            activities.event(service,eventBody);check(Boolean.TRUE.equals(activities.event(service,eventBody).get("duplicate")),"event replay");check(list(activities.getEvent(user,event).get("objects")).size()==1,"event participant references");
            checkSubjectReport(activities,"event",event,first,reportFailures);
            String report=id();Map<String,Object> reportBody=values("request_id",id(),"report_id",report,"subject_kind","activity","subject_id",a1.get("activity_id"),"report_type","person_route","completeness","partial","coverage",values("schema_version","1"),"task_id",first.get("task_id"),"run_id",first.get("run_id"),"report_json",values("route",activity.get("tracks")),"report_text","synthetic route");
            activities.report(service,reportBody);Map<String,Object> updated=parse(json(reportBody));updated.put("request_id",id());updated.put("expected_revision",1);updated.put("completeness","complete");
            check(((Number)activities.report(service,updated).get("revision")).longValue()==2,"same report updated");check("complete".equals(activities.getReport(user,report).get("completeness")),"current report queried");
            fails(409,()->activities.report(service,with(updated,"request_id",id())));
            String registered=id();identities.register(user,values("request_id",id(),"identity_id",registered,"object_type","person","display_name","synthetic registration"));
            store.jdbc().update("INSERT INTO public.identity_link(temporary_identity_id,registered_identity_id,valid_from,basis_type,expires_at) VALUES (?::uuid,?::uuid,now(),'manual',?)",a1.get("identity_id"),registered,observed.plusDays(7));
            Map<String,Object> registeredRow=map(list(identities.query(user,values("identity_kind","registered")).get("items")).stream().filter(v->registered.equals(map(v).get("identity_id"))).findFirst().get());
            check(observed.equals(OffsetDateTime.parse(registeredRow.get("last_seen_at").toString())),"registered list aggregates linked temporary appearances");
            BusinessDiscoveryDatabaseCheck.verify(data,identities,activities,user,service,registered,a1.get("identity_id").toString(),event,report,first,second);
            String enrollment=id();images.upload(user,values("request_id",id(),"asset_id",enrollment,"purpose","enrollment"),image);
            String enrollmentSample=id();features.sample(service,values("request_id",id(),"sample_id",enrollmentSample,"purpose","enrollment","identity_id",registered,"asset_id",enrollment,"occurred_at",first.get("occurred_at")));
            feature(enrollmentSample,null,registered,first,null);
            checkTaskCompletion(data,activities,first,enrollmentSample,registered,enrollment);
            String asset=id();images.upload(user,values("request_id",id(),"asset_id",asset,"purpose","query"),image);
            String query=id();search.create(user,values("request_id",id(),"query_id",query,"query_kind","image","object_type","person","input_asset_id",asset));
            checkSubjectReport(activities,"query",query,first,reportFailures);
            Map<String,Object> q=search.get(user,query);String querySample=id(),otherSample=id();
            features.sample(service,values("request_id",id(),"sample_id",querySample,"purpose","query","query_id",query,"asset_id",asset,"occurred_at",first.get("occurred_at"),"expires_at",q.get("expires_at")));
            features.sample(service,values("request_id",id(),"sample_id",otherSample,"purpose","query","query_id",query,"asset_id",asset,"occurred_at",first.get("occurred_at"),"expires_at",q.get("expires_at")));
            Map<String,Object> bbox=values("schema_version","1","xyxy",Arrays.asList(.1,.1,.9,.9),"source_width",20,"source_height",30);
            search.candidates(service,values("request_id",id(),"query_id",query,"expected_revision",1,"candidates",Arrays.asList(values("candidate_id","1","sample_id",otherSample,"object_type","person","bbox",bbox,"confidence",.9),values("candidate_id","2","sample_id",querySample,"object_type","person","bbox",bbox,"confidence",.8))));
            check("waiting_input".equals(search.get(user,query).get("state")),"multiple targets wait for selection");
            search.select(user,values("request_id",id(),"query_id",query,"candidate_id","2","expected_revision",2));
            check(querySample.equals(search.get(user,query).get("input_sample_id").toString()),"chosen target is resolved within its query");
            Map<String,Object> queryFeature=feature(querySample,null,null,first,q.get("expires_at"));
            Map<String,Object> hits=search.search(user,values("request_id",id(),"query_id",query,"feature_id",queryFeature.get("feature_id"),"threshold",.8,"expected_revision",3));
            List<Object> found=list(hits.get("hits"));check(found.size()==3,"gallery plus two historical appearances");
            check(found.stream().anyMatch(v->"gallery".equals(map(v).get("hit_kind"))),"registered gallery is searchable");
            BusinessActor other=new BusinessActor("user:72",72L,null,grant);fails(403,()->search.get(other,query));
            store.jdbc().update("UPDATE public.sample SET expires_at=now()-interval '1 second' WHERE id=?::uuid",querySample);fails(410,()->features.feature(service,values("request_id",id(),"feature_id",id(),"feature_space_id",space,"run_id",first.get("run_id"),"producer_feature_key",id(),"embedding",Arrays.asList(1,0,0),"sample_id",querySample,"aggregation_method","single","input_count",1,"used_count",1,"contributions",Collections.singletonList(values("sample_id",querySample)),"processed_at",first.get("occurred_at"),"expires_at",q.get("expires_at"))));
            BusinessActor shared=new BusinessActor("shared:business",null,null,grant);
            String sharedAsset=id(),sharedQuery=id(),sharedRequest=id();
            images.upload(shared,values("request_id",id(),"asset_id",sharedAsset,"purpose","query"),image);
            Map<String,Object> sharedBody=values("request_id",sharedRequest,"query_id",sharedQuery,"query_kind","image","object_type","person","input_asset_id",sharedAsset);
            search.create(shared,sharedBody);
            check(search.get(shared,sharedQuery).get("owner_user_id")==null,"shared query has no fabricated user ID");
            check(Boolean.TRUE.equals(search.create(shared,sharedBody).get("duplicate")),"shared query request replay");
            search.get(service,sharedQuery);
            fails(403,()->search.get(shared,query));
            fails(403,()->search.get(user,sharedQuery));
            fails(403,()->recordings.asset(shared,asset));
            fails(403,()->images.upload(shared,values("request_id",id(),"asset_id",id(),"purpose","history","source_id",source1,"input_frame_id",first.get("frame_id")),image));
            String sharedSample=id();
            features.sample(service,values("request_id",id(),"sample_id",sharedSample,"purpose","query","query_id",sharedQuery,"asset_id",sharedAsset,"occurred_at",OffsetDateTime.now().toString(),"expires_at",search.get(shared,sharedQuery).get("expires_at")));
            search.candidates(service,values("request_id",id(),"query_id",sharedQuery,"expected_revision",1,"candidates",Arrays.asList(values("candidate_id","1","sample_id",sharedSample,"object_type","person","bbox",bbox,"confidence",.9),values("candidate_id","2","sample_id",sharedSample,"object_type","person","bbox",bbox,"confidence",.8))));
            search.select(shared,values("request_id",id(),"query_id",sharedQuery,"candidate_id","2","expected_revision",2));
            check("pending".equals(search.get(shared,sharedQuery).get("state")),"shared candidate selection continues processing");
            String sharedEnrollment=id();images.upload(shared,values("request_id",id(),"asset_id",sharedEnrollment,"purpose","enrollment"),image);
            identities.register(shared,values("request_id",id(),"identity_id",id(),"object_type","person","enrollment_assets",Collections.singletonList(values("asset_id",sharedEnrollment,"sample_id",id()))));
            store.jdbc().update("UPDATE public.query_request SET expires_at=now()-interval '1 second' WHERE id=?::uuid",sharedQuery);
            fails(410,()->search.get(shared,sharedQuery));
            check(reportFailures.isEmpty(),"typed report registration rejected by legacy constraint: "+reportFailures);
            System.out.println("BusinessIdentityDatabaseCheck passed: samples/features, cross-source identity/activity, automatic and event/query reports, task completion, vector search and ownership.");
        }finally{try(java.util.stream.Stream<Path> paths=Files.walk(root)){for(Path path:(Iterable<Path>)paths.sorted(Comparator.reverseOrder())::iterator){Files.delete(path);}}}
    }
    private static void checkSubjectReport(ActivityBusinessService activities,String kind,String subject,Map<String,Object> frame,List<String> failures){
        String report=id();Map<String,Object> body=values("request_id",id(),"report_id",report,"subject_kind",kind,"subject_id",subject,"report_type","fixture_subject","completeness","partial","coverage",values("schema_version","1"),"task_id",frame.get("task_id"),"run_id",frame.get("run_id"),"report_json",values("summary","synthetic "+kind));
        try{
            activities.report(service,body);Map<String,Object> saved=activities.getReport(user,report);
            check(kind.equals(saved.get("subject_kind"))&&subject.equals(saved.get("subject_id").toString()),kind+" report keeps its typed subject");
        }catch(BusinessException error){
            if(error.getStatus()!=409){throw error;}
            failures.add(kind+": 409 "+error.getMessage());
        }
    }
    private static void checkTaskCompletion(BusinessDataAccess data,ActivityBusinessService activities,Map<String,Object> frame,String sample,String identity,String asset){
        String task=id(),run=id();OffsetDateTime now=OffsetDateTime.now(),expiry=now.plusDays(6);
        String capability=store.jdbc().queryForObject("SELECT capability_code FROM public.business_task WHERE task_id=?::uuid",String.class,frame.get("task_id"));
        Map<String,Object> input=values("input",values("kind","image","asset_ids",Collections.singletonList(asset)),"requested_outputs",Collections.singletonList("feature.embedding"));
        store.jdbc().update("INSERT INTO public.business_task(task_id,task_kind,task_mode,actor_key,capability_code,state,input_json,input_digest,expires_at) VALUES (?::uuid,'features','once',?,?,'running',?::jsonb,?,?)",task,service.getActorKey(),capability,json(input),String.join("",Collections.nCopies(64,"b")),expiry);
        store.jdbc().update("INSERT INTO public.task_attempt(run_id,task_id,generation,state,implementation_code,implementation_version,lease_owner,started_at,expires_at) VALUES (?::uuid,?::uuid,1,'running','synthetic','1',?,?,?)",run,task,service.getActorKey(),now,expiry);
        store.jdbc().update("UPDATE public.business_task SET current_run_id=?::uuid,generation=1 WHERE task_id=?::uuid",run,task);
        CapabilityTaskService tasks=new CapabilityTaskService(store,data,activities);
        Map<String,Object> finish=values("request_id",id(),"task_id",task,"run_id",run,"expected_revision",1,"feature_ids",Collections.singletonList(id()));
        fails(404,()->tasks.finish(service,finish));
        check("running".equals(store.jdbc().queryForObject("SELECT state FROM public.business_task WHERE task_id=?::uuid",String.class,task)),"invalid output cannot partially complete task");
        Map<String,Object> frameWithRun=with(frame,"run_id",run);Map<String,Object> feature=feature(sample,null,identity,frameWithRun,null);
        finish.put("request_id",id());finish.put("feature_ids",Collections.singletonList(feature.get("feature_id")));
        Map<String,Object> done=tasks.finish(service,finish);check("succeeded".equals(done.get("state"))&&((Number)done.get("progress")).intValue()==100,"feature task is completed");
        check("succeeded".equals(store.jdbc().queryForObject("SELECT state FROM public.task_attempt WHERE run_id=?::uuid",String.class,run)),"attempt completes with task");
        check(Boolean.TRUE.equals(tasks.finish(service,finish).get("duplicate")),"completion retries return same result");
        check(list(tasks.get(service,task,null).get("output_refs")).stream().anyMatch(v->feature.get("feature_id").equals(map(v).get("id"))),"completed feature task retains output refs on GET");
        fails(409,()->tasks.finish(service,with(finish,"request_id",id())));
        check(store.jdbc().queryForObject("SELECT count(*) FROM public.outbox_event WHERE aggregate_id=?::uuid AND event_type='tasks.succeeded'",Long.class,task)==1,"completion event is emitted once");
    }
    private static Map<String,Object> frame(String source){
        String stream=id(),session=id(),task=id(),run=id(),set=id(),context=id(),frame=id(),result=id(),cap="stage2_"+source.replace("-","");OffsetDateTime now=OffsetDateTime.now().withNano(0).minusSeconds(30),expires=now.plusDays(7);
        store.jdbc().update("INSERT INTO public.camera(id,camera_code,name) VALUES (?::uuid,?,'synthetic')",source,"stage2-"+source);
        store.jdbc().update("INSERT INTO public.camera_stream(id,camera_id,stream_name,task_type) VALUES (?::uuid,?::uuid,?,'track')",stream,source,"live/"+source);
        store.jdbc().update("INSERT INTO public.stream_session(id,source_id,camera_stream_id,session_key,started_at,time_origin_at,time_basis,source_timezone,source_width,source_height,expires_at) VALUES (?::uuid,?::uuid,?::uuid,?,?,?,'ingest_clock','UTC',20,30,?)",session,source,stream,session,now,now,expires);
        store.jdbc().update("INSERT INTO public.capability_definition(capability_code,display_name,object_types,input_kinds) VALUES (?,'synthetic','{person}','{live_video}')",cap);
        store.jdbc().update("INSERT INTO public.result_type(type_code,schema_version) VALUES ('detection.frame','1') ON CONFLICT DO NOTHING");Map<String,Object> input=values("input",values("kind","live_video","source_id",source,"stream_session_id",session),"requested_outputs",Collections.singletonList("detection.frame"));
        store.jdbc().update("INSERT INTO public.business_task(task_id,task_kind,task_mode,actor_key,capability_code,state,input_json,input_digest,expires_at) VALUES (?::uuid,'tracking','continuous',?,?,'running',?::jsonb,?,?)",task,service.getActorKey(),cap,json(input),String.join("",Collections.nCopies(64,"a")),expires);
        store.jdbc().update("INSERT INTO public.task_attempt(run_id,task_id,generation,state,implementation_code,implementation_version,lease_owner,started_at,expires_at) VALUES (?::uuid,?::uuid,1,'running','synthetic','1',?,?,?)",run,task,service.getActorKey(),now,expires);store.jdbc().update("UPDATE public.business_task SET current_run_id=?::uuid,generation=1 WHERE task_id=?::uuid",run,task);
        OffsetDateTime observed=now.plusSeconds(1);Map<String,Object> f=values("result_id",result,"producer_result_key","frame:1","frame_id",frame,"frame_seq",1,"occurred_at",iso(observed),"stream_pts_ms",1000,"time_quality","ingest_estimated","source_width",20,"source_height",30,"targets",Collections.singletonList(values("target_index",0,"object_type","person","class_code","person","bbox",Arrays.asList(.1,.1,.9,.9),"confidence",.9,"is_prediction",false,"local_track_id",1)));
        Map<String,Object> batch=values("request_id",id(),"task_id",task,"run_id",run,"result_set_id",set,"set_key","tracking","capability_code",cap,"result_type","detection.frame","schema_version","1","source_id",source,"stream_session_id",session,"tracking_context_id",context,"tracking_context",values("context_key",context,"started_at",iso(now)),"processed_at",iso(observed),"results",Collections.singletonList(f),"analysis_coverage",values("start_at",iso(now),"end_at",iso(now.plusSeconds(2)),"closed",true,"analyzed_frame_count",1,"frame_ids",Collections.singletonList(frame),"gaps",Collections.emptyList()));
        new ResultRegistrationService(store).register(service,batch);
        String track=store.jdbc().queryForObject("SELECT id::text FROM public.tracklet WHERE tracking_context_id=?::uuid AND local_track_id=1",String.class,context);
        return values("source_id",source,"frame_id",frame,"tracklet_id",track,"task_id",task,"run_id",run,"occurred_at",iso(observed),"expires_at",iso(observed.plusDays(7)),"batch",batch);
    }
    private static OffsetDateTime nextFrame(Map<String,Object> original,int seconds,boolean predicted){
        Map<String,Object> batch=parse(json(original.get("batch"))),frame=map(list(batch.get("results")).get(0));
        OffsetDateTime at=OffsetDateTime.parse(original.get("occurred_at").toString()).plusSeconds(seconds);String frameId=id();
        frame.put("frame_id",frameId);frame.put("result_id",id());frame.put("producer_result_key","frame:"+(seconds+1));frame.put("frame_seq",seconds+1);frame.put("stream_pts_ms",1000L*(seconds+1));frame.put("occurred_at",iso(at));map(list(frame.get("targets")).get(0)).put("is_prediction",predicted);
        batch.put("request_id",id());batch.put("processed_at",iso(at));batch.put("analysis_coverage",values("start_at",iso(at),"end_at",iso(at.plusSeconds(1)),"closed",true,"analyzed_frame_count",1,"frame_ids",Collections.singletonList(frameId),"gaps",Collections.emptyList()));
        check(list(new ResultRegistrationService(store).register(service,batch).get("accepted_result_ids")).size()==1,"next frame persisted");return at;
    }
    private static Map<String,Object> history(Map<String,Object> frame){String asset=id(),sample=id();images.upload(service,values("request_id",id(),"asset_id",asset,"purpose","history","source_id",frame.get("source_id"),"input_frame_id",frame.get("frame_id"),"tracklet_id",frame.get("tracklet_id"),"occurred_at",frame.get("occurred_at")),image);
        features.sample(service,values("request_id",id(),"sample_id",sample,"purpose","history","asset_id",asset,"input_frame_id",frame.get("frame_id"),"tracklet_id",frame.get("tracklet_id"),"occurred_at",frame.get("occurred_at"),"expires_at",frame.get("expires_at")));
        return feature(sample,frame.get("tracklet_id"),null,frame,frame.get("expires_at"));}
    private static Map<String,Object> feature(String sample,Object track,Object identity,Map<String,Object> frame,Object expiry){return features.feature(service,values("request_id",id(),"feature_id",id(),"feature_space_id",space,"run_id",frame.get("run_id"),"producer_feature_key",id(),"embedding",Arrays.asList(1,0,0),"sample_id",sample,"tracklet_id",track,"identity_id",identity,"aggregation_method","single","input_count",1,"used_count",1,"contributions",Collections.singletonList(values("sample_id",sample)),"processed_at",frame.get("occurred_at"),"expires_at",expiry));}
    private static Map<String,Object> with(Map<String,Object> value,String key,Object item){Map<String,Object> result=parse(json(value));result.put(key,item);return result;}
    private static String id(){return UUID.randomUUID().toString();}
    private static void check(boolean condition,String message){if(!condition){throw new AssertionError(message);}}
    private static void fails(int status,Runnable action){try{action.run();throw new AssertionError("Expected "+status);}catch(BusinessException expected){if(expected.getStatus()!=status){throw new AssertionError("Expected "+status+", got "+expected.getStatus(),expected);}}}
}
