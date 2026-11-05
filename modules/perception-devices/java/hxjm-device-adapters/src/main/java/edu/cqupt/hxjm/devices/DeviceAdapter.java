package edu.cqupt.hxjm.devices;
import java.util.Map;
/** Protocol differences stay here; payload includes task/run references supplied by Capability. */
public interface DeviceAdapter extends AutoCloseable {
    String code();
    Map<String,Object> describe();
    void validate(String endpoint,String operation);
    Map<String,Object> submit(String run,String endpoint,String operation,Map<String,Object> payload);
    Map<String,Object> poll(String run);
    void release(String run);
    void close();
}
