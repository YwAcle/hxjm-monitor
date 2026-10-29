package edu.cqupt.hxjm.algdeployment.business.security;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashSet;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashSet;
import org.springframework.beans.factory.annotation.Autowired;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessStore;
import java.util.Map;
import java.util.Set;
import javax.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.common.core.domain.model.LoginUser;

@Component
@ConditionalOnProperty(prefix = "hxjm.business", name = "enabled", havingValue = "true")
public class BusinessAuthentication implements InitializingBean {
    public static final String SERVICE_ID_HEADER = "X-HXJM-Service-Id";
    public static final String SERVICE_TOKEN_HEADER = "X-HXJM-Service-Token";
    private final BusinessSecurityProperties properties;
    private final BusinessStore store;
    private static final Set<String> SHARED_OPERATIONS = Collections.unmodifiableSet(new LinkedHashSet<>(Arrays.asList(
            "sources.query", "assets.query", "media.resolve", "results.query", "assets.upload",
            "identities.register", "identities.query", "tracklets.query", "activities.query", "events.query", "reports.query",
            "queries.create", "queries.get", "queries.select", "search.execute", "samples.query")));

    public BusinessAuthentication(BusinessSecurityProperties properties) {
        this(properties, null);
    }

    @Autowired
    public BusinessAuthentication(BusinessSecurityProperties properties, BusinessStore store) {
        this.properties = properties;
        this.store = store;
    }

    @Override
    public void afterPropertiesSet() {
        if (properties.getServices() == null || properties.getUsers() == null) {
            throw new IllegalArgumentException("Business security identity maps must not be null");
        }
        Set<String> tokens = new HashSet<>();
        for (Map.Entry<String, BusinessSecurityProperties.ServiceIdentity> entry : properties.getServices().entrySet()) {
            BusinessSecurityProperties.ServiceIdentity identity = entry.getValue();
            if (entry.getKey() == null || !entry.getKey().matches("[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}")
                    || identity == null || identity.getToken() == null || identity.getToken().trim().isEmpty()
                    || !tokens.add(identity.getToken())) {
                throw new IllegalArgumentException("Business service IDs and distinct nonempty tokens are required");
            }
            validateGrant(identity);
        }
        for (Map.Entry<Long, BusinessSecurityProperties.Grant> entry : properties.getUsers().entrySet()) {
            if (entry.getKey() == null || entry.getKey() <= 0) {
                throw new IllegalArgumentException("Business user IDs must be positive");
            }
            validateGrant(entry.getValue());
        }
    }

    private void validateGrant(BusinessSecurityProperties.Grant grant) {
        if (grant == null || grant.getOperations() == null || grant.getSourceIds() == null) {
            throw new IllegalArgumentException("Business grants require explicit operation and source sets");
        }
        for (String operation : grant.getOperations()) {
            if (operation == null || !operation.matches("[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*")) {
                throw new IllegalArgumentException("Business operations must be explicit operation names");
            }
        }
        for (String sourceId : grant.getSourceIds()) {
            try {
                BusinessActor.canonicalSource(sourceId);
            } catch (BusinessException exception) {
                throw new IllegalArgumentException("Business source grants require canonical nonzero UUIDs");
            }
        }
    }

    public BusinessActor authenticate(HttpServletRequest request, String operation) {
        String serviceId = request.getHeader(SERVICE_ID_HEADER);
        String token = request.getHeader(SERVICE_TOKEN_HEADER);
        BusinessActor actor;
        if (serviceId != null || token != null) {
            BusinessSecurityProperties.ServiceIdentity identity = properties.getServices().get(serviceId);
            if (identity == null || token == null || !sameToken(identity.getToken(), token)) {
                throw BusinessException.unauthenticated();
            }
            actor = new BusinessActor("service:" + serviceId, null, serviceId, identity);
        } else if (SHARED_OPERATIONS.contains(operation)) {
            BusinessSecurityProperties.Grant grant = new BusinessSecurityProperties.Grant();
            grant.setOperations(SHARED_OPERATIONS);
            grant.setSourceIds(new LinkedHashSet<>(store.jdbc().queryForList(
                    "SELECT id::text FROM public.camera ORDER BY id", String.class)));
            actor = new BusinessActor("shared:business", null, null, grant);
        } else {
            // JwtAuthenticationTokenFilter has already verified TokenService's JWT and Redis login.
            Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
            if (authentication == null || !authentication.isAuthenticated()
                    || !(authentication.getPrincipal() instanceof LoginUser)) {
                throw BusinessException.unauthenticated();
            }
            LoginUser login = (LoginUser) authentication.getPrincipal();
            if (login.getUserId() == null || login.getUserId() <= 0 || login.getUser() == null
                    || !"0".equals(login.getUser().getStatus()) || !"0".equals(login.getUser().getDelFlag())
                    || login.getExpireTime() == null || login.getExpireTime() <= System.currentTimeMillis()) {
                throw BusinessException.unauthenticated();
            }
            BusinessSecurityProperties.Grant grant = properties.getUsers().get(login.getUserId());
            if (grant == null) {
                throw BusinessException.forbidden();
            }
            actor = new BusinessActor("user:" + login.getUserId(), login.getUserId(), null, grant);
        }
        actor.requireOperation(operation);
        return actor;
    }

    public BusinessActor requireService(HttpServletRequest request, String operation) {
        BusinessActor actor = authenticate(request, operation);
        if (!actor.isService()) {
            throw BusinessException.forbidden();
        }
        return actor;
    }

    public BusinessActor requireUser(HttpServletRequest request, String operation) {
        BusinessActor actor = authenticate(request, operation);
        if (actor.getUserId() == null) {
            throw BusinessException.forbidden();
        }
        return actor;
    }

    private boolean sameToken(String expected, String supplied) {
        return expected != null && MessageDigest.isEqual(expected.getBytes(StandardCharsets.UTF_8),
                supplied.getBytes(StandardCharsets.UTF_8));
    }
}
