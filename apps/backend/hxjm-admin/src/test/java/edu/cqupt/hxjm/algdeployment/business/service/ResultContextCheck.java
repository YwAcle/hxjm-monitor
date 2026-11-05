package edu.cqupt.hxjm.algdeployment.business.service;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Collections;
import java.util.Map;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessSchemas;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

/** Pure public-contract regression; no database, service, model or fixture directory. */
public final class ResultContextCheck {
    public static void main(String[] args) throws Exception {
        Map<String,Object> schema=parse(new String(Files.readAllBytes(Paths.get(args[0])),StandardCharsets.UTF_8));
        String id="10000000-0000-4000-8000-000000000001";
        Map<String,Object> task=ResultContext.of(id,"business.events.query","service:test","once",id,id,
            Collections.emptyList(),"business.events.page","1","response",null,"2026-11-05T00:00:00Z",null);
        BusinessSchemas.validate(schema,task);
        if(task.get("occurred_at")!=null||!list(task.get("evidence_refs")).isEmpty()){
            throw new AssertionError("Query output must not fabricate observation time or evidence");
        }
        Map<String,Object> video=ResultContext.of(id,"person.tracking","service:test","continuous",id,id,
            Collections.singletonList(id),"detection.frame","1","frame:1","2026-11-05T00:00:00Z",
            "2026-11-05T00:00:01Z",id);
        BusinessSchemas.validate(schema,video);
        if(!"asset".equals(map(list(video.get("evidence_refs")).get(0)).get("kind"))){
            throw new AssertionError("Asset reference must remain typed");
        }
        System.out.println("ResultContextCheck passed: once/continuous share the authoritative schema");
    }
}
