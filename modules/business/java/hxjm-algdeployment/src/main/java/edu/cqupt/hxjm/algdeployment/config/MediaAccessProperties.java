package edu.cqupt.hxjm.algdeployment.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/** Public media access addresses; never starts algorithm or media processes. */
@Data
@Component
@ConfigurationProperties(prefix = "smartmonitor.ai")
public class MediaAccessProperties {
    private String mtxBaseUrl;
    private String publicHost;
    private Integer livePort;
}
