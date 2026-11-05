package edu.cqupt.hxjm.algdeployment.business.api;

import java.util.Map;
import javax.servlet.http.HttpServletRequest;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessAuthentication;
import edu.cqupt.hxjm.algdeployment.business.service.SampleFeatureService;
import edu.cqupt.hxjm.algdeployment.business.service.IdentityBusinessService;
import edu.cqupt.hxjm.algdeployment.business.service.ActivityBusinessService;
import edu.cqupt.hxjm.algdeployment.business.service.BusinessSearchService;
import edu.cqupt.hxjm.algdeployment.business.service.BusinessDiscoveryService;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

@RestController
@RequestMapping("/api/v1/business")
@ConditionalOnProperty(prefix="hxjm.business",name="enabled",havingValue="true")
public class IdentityBusinessController {
    private final BusinessAuthentication auth;
    private final SampleFeatureService features;
    private final IdentityBusinessService identities;
    private final ActivityBusinessService activities;
    private final BusinessSearchService search;
    private final BusinessDiscoveryService discovery;
    public IdentityBusinessController(BusinessAuthentication auth,SampleFeatureService features,IdentityBusinessService identities,ActivityBusinessService activities,BusinessSearchService search,BusinessDiscoveryService discovery){this.auth=auth;this.features=features;this.identities=identities;this.activities=activities;this.search=search;this.discovery=discovery;}
    @PostMapping("/samples/register")
    public Map<String,Object> sample(HttpServletRequest r,@RequestBody String raw){return ok(features.sample(auth.requireService(r,"samples.register"),body(r,raw)),r);}
    @PostMapping("/samples/query")
    public Map<String,Object> samples(HttpServletRequest r,@RequestBody String raw){return ok(features.samples(auth.authenticate(r,"samples.query"),body(r,raw)),r);}
    @GetMapping("/samples/pending")
    public Map<String,Object> pendingSamples(HttpServletRequest r,@RequestParam(value="purpose",defaultValue="enrollment") String purpose,@RequestParam(value="feature_space_id",required=false) String space,@RequestParam(value="limit",defaultValue="20") int limit){return ok(features.pending(auth.requireService(r,"samples.process"),purpose,space,limit),r);}
    @PostMapping("/feature-spaces/register")
    public Map<String,Object> space(HttpServletRequest r,@RequestBody String raw){return ok(features.space(auth.requireService(r,"feature_spaces.register"),body(r,raw)),r);}
    @PostMapping("/features/register")
    public Map<String,Object> feature(HttpServletRequest r,@RequestBody String raw){return ok(features.feature(auth.requireService(r,"features.register"),body(r,raw)),r);}
    @PostMapping("/identities/register")
    public Map<String,Object> registerIdentity(HttpServletRequest r,@RequestBody String raw){return ok(identities.register(auth.authenticate(r,"identities.register"),body(r,raw)),r);}
    @PostMapping("/identities/associate")
    public Map<String,Object> associate(HttpServletRequest r,@RequestBody String raw){return ok(identities.associate(auth.requireService(r,"identities.associate"),body(r,raw)),r);}
    @GetMapping("/identities/{id}")
    public Map<String,Object> identity(HttpServletRequest r,@PathVariable("id") String id){return ok(identities.get(auth.authenticate(r,"identities.query"),id),r);}
    @PostMapping("/identities/query")
    public Map<String,Object> queryIdentities(HttpServletRequest r,@RequestBody String raw){return ok(identities.query(auth.authenticate(r,"identities.query"),body(r,raw)),r);}
    @PostMapping("/tracklets/query")
    public Map<String,Object> tracklets(HttpServletRequest r,@RequestBody String raw){return ok(discovery.tracklets(auth.authenticate(r,"tracklets.query"),body(r,raw)),r);}
    @PostMapping("/events/query")
    public Map<String,Object> events(HttpServletRequest r,@RequestBody String raw){return ok(discovery.events(auth.authenticate(r,"events.query"),body(r,raw)),r);}
    @PostMapping("/reports/search")
    public Map<String,Object> discoverReports(HttpServletRequest r,@RequestBody String raw){return ok(discovery.reports(auth.authenticate(r,"reports.query"),body(r,raw)),r);}
    @PostMapping("/activities/query")
    public Map<String,Object> activities(HttpServletRequest r,@RequestBody String raw){return ok(activities.activities(auth.authenticate(r,"activities.query"),body(r,raw)),r);}
    @GetMapping("/activities/{id}")
    public Map<String,Object> activity(HttpServletRequest r,@PathVariable("id") String id){return ok(activities.getActivity(auth.authenticate(r,"activities.query"),id),r);}
    @PostMapping("/activities/close")
    public Map<String,Object> close(HttpServletRequest r,@RequestBody String raw){return ok(activities.close(auth.requireService(r,"activities.close"),body(r,raw)),r);}
    @PostMapping("/events/register")
    public Map<String,Object> event(HttpServletRequest r,@RequestBody String raw){return ok(activities.event(auth.requireService(r,"events.register"),body(r,raw)),r);}
    @GetMapping("/events/{id}")
    public Map<String,Object> getEvent(HttpServletRequest r,@PathVariable("id") String id){return ok(activities.getEvent(auth.authenticate(r,"events.query"),id),r);}
    @PostMapping("/reports/register")
    public Map<String,Object> report(HttpServletRequest r,@RequestBody String raw){return ok(activities.report(auth.requireService(r,"reports.register"),body(r,raw)),r);}
    @GetMapping("/reports/{id}")
    public Map<String,Object> getReport(HttpServletRequest r,@PathVariable("id") String id){return ok(activities.getReport(auth.authenticate(r,"reports.query"),id),r);}
    @PostMapping("/reports/query")
    public Map<String,Object> reports(HttpServletRequest r,@RequestBody String raw){return ok(activities.reports(auth.authenticate(r,"reports.query"),body(r,raw)),r);}
    @PostMapping("/queries")
    public Map<String,Object> query(HttpServletRequest r,@RequestBody String raw){return ok(search.create(auth.authenticate(r,"queries.create"),body(r,raw)),r);}
    @GetMapping("/queries/{id}")
    public Map<String,Object> getQuery(HttpServletRequest r,@PathVariable("id") String id){return ok(search.get(auth.authenticate(r,"queries.get"),id),r);}
    @GetMapping("/queries/pending")
    public Map<String,Object> pending(HttpServletRequest r,@RequestParam(value="limit",defaultValue="20") int limit){return ok(search.pending(auth.requireService(r,"queries.process"),limit),r);}
    @PostMapping("/queries/candidates")
    public Map<String,Object> candidates(HttpServletRequest r,@RequestBody String raw){return ok(search.candidates(auth.requireService(r,"queries.candidates"),body(r,raw)),r);}
    @PostMapping("/queries/select")
    public Map<String,Object> select(HttpServletRequest r,@RequestBody String raw){return ok(search.select(auth.authenticate(r,"queries.select"),body(r,raw)),r);}
    @PostMapping("/search")
    public Map<String,Object> search(HttpServletRequest r,@RequestBody String raw){return ok(search.search(auth.authenticate(r,"search.execute"),body(r,raw)),r);}
    private static Map<String,Object> body(HttpServletRequest r,String raw){Map<String,Object> body=parse(raw);BusinessResponses.traceId(r,body.get("trace_id")==null?null:text(body,"trace_id",128));return body;}
    private static Map<String,Object> ok(Map<String,Object> value,HttpServletRequest r){return BusinessResponses.success(value,r,null);}
}
