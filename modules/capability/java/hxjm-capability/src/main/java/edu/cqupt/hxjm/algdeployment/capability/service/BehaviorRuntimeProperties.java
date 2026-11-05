package edu.cqupt.hxjm.algdeployment.capability.service;
import lombok.Data;
import org.springframework.stereotype.Component;
import org.springframework.boot.context.properties.ConfigurationProperties;
@Data
@Component
@ConfigurationProperties(prefix="hxjm.business.behavior")
public class BehaviorRuntimeProperties {
    private String url;
    private String token;
}
