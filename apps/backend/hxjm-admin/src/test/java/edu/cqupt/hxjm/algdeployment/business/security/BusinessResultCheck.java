package edu.cqupt.hxjm.algdeployment.business.security;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.service.ResultRegistrationService;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

/** Validate actual result boundaries without starting models, Spring or a database. */
public final class BusinessResultCheck {
    private static Map<String,Object> frame() {
        return parse("{\"result_id\":\"10000000-0000-4000-8000-000000000001\",\"producer_result_key\":\"frame:one\","
                + "\"frame_id\":\"20000000-0000-4000-8000-000000000001\",\"frame_seq\":1,\"occurred_at\":\"2026-10-26T10:00:00Z\","
                + "\"source_width\":1920,\"source_height\":1080,\"time_quality\":\"ingest_estimated\",\"targets\":[]}");
    }
    private static Map<String,Object> target() {
        return parse("{\"target_index\":0,\"local_track_id\":0,\"object_type\":\"person\",\"class_code\":\"person\","
                + "\"bbox\":[0.1,0.2,0.5,0.9],\"confidence\":0.9,\"is_prediction\":false}");
    }
    private static void rejects(Map<String,Object> frame,boolean tracking) {
        try { ResultRegistrationService.validateFrame(frame,tracking); throw new AssertionError("Invalid frame accepted"); }
        catch (BusinessException expected) { if (!"INVALID_ARGUMENT".equals(expected.getCode())) { throw expected; } }
    }
    public static void main(String[] args) {
        ResultRegistrationService.validateFrame(frame(),false);
        Map<String,Object> frame=frame(); List<Object> targets=new ArrayList<>(); frame.put("targets",targets);
        Map<String,Object> person=target(); targets.add(person);
        ResultRegistrationService.validateFrame(frame,true);
        person.put("is_prediction",true); person.put("confidence",null);
        ResultRegistrationService.validateFrame(frame,true);
        person.put("is_prediction",false); rejects(frame,true);
        person.put("confidence",0.9); person.put("bbox",java.util.Arrays.asList(0.8,0.2,0.1,0.9)); rejects(frame,true);
        person.put("bbox",java.util.Arrays.asList(0.1,0.2,0.5,0.9)); targets.add(target()); rejects(frame,true);
        targets.remove(1); rejects(frame,false);
        frame.put("media_asset_id","30000000-0000-4000-8000-000000000001"); rejects(frame,true);
        frame.remove("media_asset_id"); frame.put("time_quality","camera_guess"); rejects(frame,true);
        frame=frame(); List<Object> many=new ArrayList<>();
        for (int i=0;i<503;i++) { Map<String,Object> item=target(); item.put("target_index",i); item.put("local_track_id",i); many.add(item); }
        frame.put("targets",many); ResultRegistrationService.validateFrame(frame,true);
        System.out.println("BusinessResultCheck passed: zero targets, predictions, all 503 targets and invalid references/boxes.");
    }
}
