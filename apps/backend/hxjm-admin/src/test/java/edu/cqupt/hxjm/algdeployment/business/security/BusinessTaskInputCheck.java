package edu.cqupt.hxjm.algdeployment.business.security;

import java.time.OffsetDateTime;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.service.BusinessTaskInputs;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.values;

/** The extracted Business boundary preserves scope, state and expiry validation. */
public final class BusinessTaskInputCheck {
    public static void main(String[] args) {
        String source=UUID.randomUUID().toString(), session=UUID.randomUUID().toString();
        BusinessSecurityProperties.Grant grant=new BusinessSecurityProperties.Grant();
        grant.setSourceIds(new LinkedHashSet<>(Collections.singleton(source)));
        BusinessActor actor=new BusinessActor("service:test",null,"test",grant);
        final Map<String,Object> row=values("state","open","expires_at",OffsetDateTime.now().plusHours(1));
        JdbcTemplate jdbc=new JdbcTemplate(){
            @Override public List<Map<String,Object>> queryForList(String sql,Object... params) {
                if(!source.equals(params[1])){throw new AssertionError("Source binding lost");}
                return Collections.singletonList(row);
            }
        };
        BusinessTaskInputs inputs=new BusinessTaskInputs(null,null);
        Map<String,Object> input=values("kind","live_video","source_id",source,"stream_session_id",session);
        BusinessTaskInputs.Scope scope=inputs.resolve(jdbc,actor,input,"continuous",true);
        if(!scope.sources.equals(Collections.singleton(source))||!scope.expires.equals(row.get("expires_at"))) {
            throw new AssertionError("Business scope/expiry changed");
        }
        fails(400,()->inputs.resolve(jdbc,actor,input,"once",true));
        Map<String,Object> foreign=new LinkedHashMap<>(input);foreign.put("source_id",UUID.randomUUID().toString());
        fails(403,()->inputs.resolve(jdbc,actor,foreign,"continuous",true));
        row.put("state","closed");fails(409,()->inputs.resolve(jdbc,actor,input,"continuous",true));
        inputs.resolve(jdbc,actor,input,"continuous",false);
        row.put("expires_at",OffsetDateTime.now().minusMinutes(1));
        fails(410,()->inputs.resolve(jdbc,actor,input,"continuous",false));
        System.out.println("BusinessTaskInputCheck passed: scope, mode, authorization, state, expiry");
    }
    private static void fails(int status,Runnable work){
        try{work.run();throw new AssertionError("Expected failure "+status);}
        catch(BusinessException failure){if(failure.getStatus()!=status){throw new AssertionError(failure.getStatus());}}
    }
}
