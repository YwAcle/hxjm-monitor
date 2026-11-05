package edu.cqupt.hxjm.devices;
import java.util.*;
import org.springframework.stereotype.Component;
/** Spring discovers adapters; adding a device does not change the Capability executor. */
@Component
public class DeviceAdapters implements AutoCloseable {
    private final Map<String,DeviceAdapter> adapters=new LinkedHashMap<>();
    public DeviceAdapters(List<DeviceAdapter> configured){for(DeviceAdapter adapter:configured){if(adapters.put(adapter.code(),adapter)!=null){throw new IllegalArgumentException("Duplicate device adapter");}}}
    public DeviceAdapter get(String code){DeviceAdapter adapter=adapters.get(code);if(adapter==null){throw new IllegalArgumentException("Unknown device adapter: "+code);}return adapter;}
    public List<Map<String,Object>> describe(){List<Map<String,Object>> rows=new ArrayList<>();for(DeviceAdapter adapter:adapters.values()){rows.add(adapter.describe());}return rows;}
    public void close(){for(DeviceAdapter adapter:adapters.values()){adapter.close();}}
}
