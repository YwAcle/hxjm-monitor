package edu.cqupt.hxjm.devices;
import java.util.Map;
@org.springframework.stereotype.Component
public class M20MockAdapter extends M20RouteAdapter {
    @Override public String code(){return "m20_mock";}
    @Override public void validate(String endpoint,String operation){if(!"mock://local".equals(endpoint)){throw new IllegalArgumentException("Mock endpoint must be mock://local");}if(!java.util.Arrays.asList("route.start","device.status","route.stop").contains(operation)){throw new IllegalArgumentException("Unsupported mock operation");}}
    @Override public Map<String,Object> submit(String run,String endpoint,String operation,Map<String,Object> payload){validate(endpoint,operation);return submitOperation(run,endpoint,operation,payload,true);}
}
