package edu.cqupt.hxjm.algdeployment.capability.service;

import java.util.*;
import lombok.Data;
import org.springframework.stereotype.Component;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Data
@Component
@ConfigurationProperties(prefix="hxjm.business.cleanup")
public class CleanupProperties {
    private boolean enabled;
    private String serviceId="hxjm-pipeline";
    // Verified source UUID -> pre-calibrated external route. Pixels are never navigation coordinates.
    private Map<String,String> routes=new LinkedHashMap<>();
}
