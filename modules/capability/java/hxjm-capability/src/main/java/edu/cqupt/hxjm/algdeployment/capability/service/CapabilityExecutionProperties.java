package edu.cqupt.hxjm.algdeployment.capability.service;

import java.util.LinkedHashMap;
import java.util.Map;
import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/** Trusted server configuration; never populated by capability registration. */
@Data
@Component
@ConfigurationProperties(prefix="hxjm.business.execution")
public class CapabilityExecutionProperties {
    private boolean enabled;
    private String namespace;
    private Map<String,Map<String,Operation>> services = new LinkedHashMap<>();
    @Data
    public static class Operation {
        private String url;
        private String adapter = "http";
        private String deviceOperation;
        private boolean exclusive = true;
        private String method = "POST";
        private String version = "1";
        private String credentialRef;
        private String requiredOperation;
        private String requestMode = "payload";
        private String responseMode = "business";
        private int connectTimeoutMs = 2000;
        private int responseTimeoutMs = 5000;
        private int maxResponseBytes = 1048576;
    }
}
