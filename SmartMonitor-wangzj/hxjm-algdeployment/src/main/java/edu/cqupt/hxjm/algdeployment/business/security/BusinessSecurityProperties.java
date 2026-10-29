package edu.cqupt.hxjm.algdeployment.business.security;

import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** Only new business endpoints use these grants; empty configuration denies access. */
@Component
@ConfigurationProperties(prefix = "hxjm.business.security")
@ConditionalOnProperty(prefix = "hxjm.business", name = "enabled", havingValue = "true")
public class BusinessSecurityProperties {
    private Map<String, ServiceIdentity> services = new LinkedHashMap<>();
    private Map<Long, Grant> users = new LinkedHashMap<>();

    public Map<String, ServiceIdentity> getServices() { return services; }
    public void setServices(Map<String, ServiceIdentity> services) { this.services = services; }
    public Map<Long, Grant> getUsers() { return users; }
    public void setUsers(Map<Long, Grant> users) { this.users = users; }

    public static class Grant {
        private Set<String> operations = new LinkedHashSet<>();
        private Set<String> sourceIds = new LinkedHashSet<>();

        public Set<String> getOperations() { return operations; }
        public void setOperations(Set<String> operations) { this.operations = operations; }
        public Set<String> getSourceIds() { return sourceIds; }
        public void setSourceIds(Set<String> sourceIds) { this.sourceIds = sourceIds; }
    }

    public static class ServiceIdentity extends Grant {
        private String token;
        public String getToken() { return token; }
        public void setToken(String token) { this.token = token; }
    }
}
