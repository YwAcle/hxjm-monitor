package edu.cqupt.hxjm.algdeployment.business.security;

import java.time.OffsetDateTime;
import java.util.*;
import edu.cqupt.hxjm.algdeployment.business.service.*;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

/** Uses the existing disposable identity fixture; no production connection. */
public final class BusinessDiscoveryDatabaseCheck {
    public static void verify(BusinessDataAccess data,IdentityBusinessService identities,ActivityBusinessService activities,BusinessActor user,BusinessActor service,String registered,String temporary,String event,String report,Map<String,Object> first,Map<String,Object> second){
        BusinessDiscoveryService discovery=new BusinessDiscoveryService(data,activities);
        String name="同名测试",other=UUID.randomUUID().toString();
        data.store().jdbc().update("UPDATE public.identity SET display_name=? WHERE id=?::uuid",name,registered);
        identities.register(user,values("request_id",UUID.randomUUID().toString(),"identity_id",other,"object_type","person","display_name",name));
        Map<String,Object> directory=values("identity_kind","registered","display_name",name,"limit",1);
        Map<String,Object> page=identities.query(user,directory);check(list(page.get("items")).size()==1&&Boolean.TRUE.equals(page.get("has_more")),"homonym first page");
        Map<String,Object> next=new LinkedHashMap<>(directory);next.put("cursor",page.get("next_cursor"));Map<String,Object> last=identities.query(user,next);
        check(!Boolean.TRUE.equals(last.get("has_more"))&&!map(list(page.get("items")).get(0)).get("identity_id").equals(map(list(last.get("items")).get(0)).get("identity_id")),"homonym next page");
        Map<String,Object> bad=new LinkedHashMap<>(next);bad.put("display_name","其他姓名");fails(400,()->identities.query(user,bad));
        Map<String,Object> badLimit=new LinkedHashMap<>(next);badLimit.put("limit",2);fails(400,()->identities.query(user,badLimit));
        fails(400,()->identities.query(user,values("cursor","!bad")));
        check(list(identities.query(user,values("display_name",name,"source_ids",Collections.singletonList(first.get("source_id")))).get("items")).size()==1,"appearance filter excludes registration without tracks");
        OffsetDateTime at=OffsetDateTime.parse(first.get("occurred_at").toString());
        Map<String,Object> window=values("identity_ids",Collections.singletonList(registered),"start_at",iso(at.minusSeconds(10)),"end_at",iso(at.plusSeconds(10)),"limit",1);
        Map<String,Object> tracks=discovery.tracklets(user,window);check(list(tracks.get("items")).size()==1&&Boolean.TRUE.equals(tracks.get("has_more")),"registered alias returns cross-camera tracks");
        Map<String,Object> continuation=new LinkedHashMap<>(window);continuation.put("cursor",tracks.get("next_cursor"));check(list(discovery.tracklets(user,continuation).get("items")).size()==1,"track keyset pagination");
        Map<String,Object> temp=new LinkedHashMap<>(window);temp.put("identity_ids",Collections.singletonList(temporary));temp.put("limit",20);check(list(discovery.tracklets(user,temp).get("items")).size()==2,"temporary alias same tracks");
        String duplicate=UUID.randomUUID().toString();
        data.store().jdbc().update("INSERT INTO public.tracklet(id,stream_id,start_ts,end_ts,cls_name,source_id,stream_session_id,canonical_tracklet_id,first_observed_at,last_observed_at,expires_at) SELECT ?::uuid,stream_id,start_ts,end_ts,cls_name,source_id,stream_session_id,id,first_observed_at,last_observed_at,expires_at FROM public.tracklet WHERE id=?::uuid",duplicate,first.get("tracklet_id"));
        data.store().jdbc().update("INSERT INTO public.track_identity_assignment(tracklet_id,identity_id,valid_from,basis_type,expires_at) SELECT ?::uuid,identity_id,valid_from,basis_type,expires_at FROM public.track_identity_assignment WHERE tracklet_id=?::uuid AND valid_to IS NULL",duplicate,first.get("tracklet_id"));
        check(list(discovery.tracklets(user,temp).get("items")).size()==2,"canonical duplicate is one track");
        data.store().jdbc().update("DELETE FROM public.track_identity_assignment WHERE tracklet_id=?::uuid",duplicate);
        data.store().jdbc().update("DELETE FROM public.tracklet WHERE id=?::uuid",duplicate);
        Map<String,Object> boundary=new LinkedHashMap<>(temp);boundary.put("end_at",iso(at));check(list(discovery.tracklets(user,boundary).get("items")).isEmpty(),"end-exclusive track window");
        Map<String,Object> eventWindow=values("mode","range","start_at",iso(at),"end_at",iso(at.plusSeconds(1)));check(!list(discovery.events(user,eventWindow).get("items")).isEmpty(),"instant event at lower boundary");
        eventWindow.put("start_at",iso(at.minusSeconds(1)));eventWindow.put("end_at",iso(at));check(list(discovery.events(user,eventWindow).get("items")).isEmpty(),"instant event excluded at upper boundary");
        check(!list(discovery.events(user,values("mode","latest","limit",1)).get("items")).isEmpty(),"latest without time filter");
        fails(400,()->discovery.events(user,values("mode","latest","start_at",iso(at),"end_at",iso(at.plusSeconds(1)))));
        fails(400,()->discovery.events(user,values("mode","range","cursor",tracks.get("next_cursor"),"start_at",iso(at),"end_at",iso(at.plusSeconds(1)))));
        String normal=UUID.randomUUID().toString();
        data.store().jdbc().update("INSERT INTO public.business_event(id,event_type,event_key,source_id,start_at,end_at,state,end_reason,conclusion_json,expires_at) VALUES (?::uuid,'normal.visit',?,?::uuid,?,?,'closed','normal','{}'::jsonb,?)",normal,normal,first.get("source_id"),at,at,at.plusDays(7));
        Map<String,Object> eventPage=discovery.events(user,values("mode","latest","limit",1));
        check(Boolean.TRUE.equals(eventPage.get("has_more")),"all event types are paged");
        Map<String,Object> older=discovery.events(user,values("mode","latest","limit",1,"cursor",eventPage.get("next_cursor")));
        check(!map(list(older.get("items")).get(0)).get("event_id").equals(map(list(eventPage.get("items")).get(0)).get("event_id")),"event same-time ID tie-breaker");
        Map<String,Object> reportWindow=values("start_at",iso(at.minusSeconds(10)),"end_at",iso(at.plusSeconds(10)),"identity_ids",Collections.singletonList(registered));
        data.store().jdbc().update("INSERT INTO public.report_evidence_link(report_id,evidence_id,report_revision,ordinal) SELECT r.id,e.id,r.revision,row_number() OVER (ORDER BY e.id)-1 FROM public.llm_report r JOIN public.evidence_reference e ON e.activity_id=r.subject_id WHERE r.id=?::uuid",report);
        List<Object> reports=list(discovery.reports(user,reportWindow).get("items"));check(reports.stream().anyMatch(v->report.equals(map(v).get("report_id"))),"reports discovered via activity identity");
        check(reports.stream().anyMatch(v->"event".equals(map(v).get("subject_kind"))),"event participant identity joins reports");
        Map<String,Object> saved=map(reports.stream().filter(v->report.equals(map(v).get("report_id"))).findFirst().get());check(((Number)saved.get("revision")).intValue()==2&&saved.containsKey("evidence"),"current report revision and evidence");
        check(!list(saved.get("evidence")).isEmpty()&&map(list(saved.get("evidence")).get(0)).containsKey("source_id"),"report evidence details are returned");
        Map<String,Object> reportPage=new LinkedHashMap<>(reportWindow);reportPage.put("limit",1);Map<String,Object> firstReport=discovery.reports(user,reportPage);check(Boolean.TRUE.equals(firstReport.get("has_more")),"report pagination");reportPage.put("cursor",firstReport.get("next_cursor"));check(!list(discovery.reports(user,reportPage).get("items")).isEmpty(),"report next page");
        BusinessSecurityProperties.Grant grant=new BusinessSecurityProperties.Grant();grant.setSourceIds(new HashSet<>(Collections.singletonList(first.get("source_id").toString())));BusinessActor restricted=new BusinessActor("service:restricted",null,"restricted",grant);
        check(list(discovery.reports(restricted,reportWindow).get("items")).stream().noneMatch(v->report.equals(map(v).get("report_id"))),"multi-source report authorization");
        data.store().jdbc().update("UPDATE public.business_event SET expires_at=now()-interval '1 second' WHERE id=?::uuid",event);
        check(list(discovery.events(user,values("mode","latest")).get("items")).stream().noneMatch(v->event.equals(map(v).get("event_id"))),"expired event hidden");
        data.store().jdbc().update("UPDATE public.business_event SET expires_at=now()+interval '6 days' WHERE id=?::uuid",event);
        BusinessAuthentication auth=new BusinessAuthentication(new BusinessSecurityProperties(),data.store());
        edu.cqupt.hxjm.algdeployment.business.api.IdentityBusinessController controller=new edu.cqupt.hxjm.algdeployment.business.api.IdentityBusinessController(auth,new SampleFeatureService(data),identities,activities,new BusinessSearchService(data),discovery);
        Map<String,Object> attributes=new HashMap<>();
        javax.servlet.http.HttpServletRequest request=(javax.servlet.http.HttpServletRequest)java.lang.reflect.Proxy.newProxyInstance(BusinessDiscoveryDatabaseCheck.class.getClassLoader(),new Class<?>[]{javax.servlet.http.HttpServletRequest.class},(proxy,method,args)->{
            if("getAttribute".equals(method.getName()))return attributes.get(args[0]);
            if("setAttribute".equals(method.getName())){attributes.put((String)args[0],args[1]);return null;}
            if("getHeader".equals(method.getName()))return null;
            return null;
        });
        check(controller.queryIdentities(request,json(directory)).containsKey("trace_id"),"HTTP identity entry without credentials");
        check(controller.tracklets(request,json(temp)).containsKey("trace_id"),"HTTP track entry without credentials");
        check(controller.events(request,json(values("mode","latest"))).containsKey("trace_id"),"HTTP event entry without credentials");
        check(controller.discoverReports(request,json(reportWindow)).containsKey("trace_id"),"HTTP report entry without credentials");
        fails(401,()->auth.requireService(request,"events.register"));
        String privateQuery=UUID.randomUUID().toString(),privateReport=UUID.randomUUID().toString();
        data.store().jdbc().update("INSERT INTO public.query_request(id,owner_user_id,query_kind,start_at,end_at,scope_json,expires_at) VALUES (?::uuid,999,'time_range',?,?,?::jsonb,?)",privateQuery,at,at.plusSeconds(1),json(values("source_ids",Collections.singletonList(first.get("source_id")))),at.plusDays(7));
        data.store().jdbc().update("INSERT INTO public.llm_report(id,subject_kind,subject_id,query_id,report_type,completeness,coverage_json,processed_at,revision,expires_at,report_json) VALUES (?::uuid,'query',?::uuid,?::uuid,'synthetic','partial','{}'::jsonb,now(),1,?,'{}'::jsonb)",privateReport,privateQuery,privateQuery,at.plusDays(7));
        check(list(controller.discoverReports(request,json(reportWindow)).get("items")).stream().noneMatch(v->privateReport.equals(map(v).get("report_id"))),"private query reports hidden from shared HTTP");
        System.out.println("BusinessDiscoveryDatabaseCheck passed: homonyms, aliases, pagination, time boundaries, events, report relations and source authorization.");
    }
    private static void check(boolean value,String message){if(!value){throw new AssertionError(message);}}
    private static void fails(int status,Runnable call){try{call.run();throw new AssertionError("Expected "+status);}catch(BusinessException error){check(error.getStatus()==status,error.getMessage());}}
}
