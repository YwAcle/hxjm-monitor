package edu.cqupt.hxjm.algdeployment.business.security;

import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;

public final class BusinessActor {
    private final String actorKey;
    private final Long userId;
    private final String serviceId;
    private final Set<String> operations;
    private final Set<String> sourceIds;

    BusinessActor(String actorKey, Long userId, String serviceId,
                  BusinessSecurityProperties.Grant grant) {
        this.actorKey = actorKey;
        this.userId = userId;
        this.serviceId = serviceId;
        this.operations = Collections.unmodifiableSet(new LinkedHashSet<>(grant.getOperations()));
        this.sourceIds = Collections.unmodifiableSet(new LinkedHashSet<>(grant.getSourceIds()));
    }

    public String getActorKey() { return actorKey; }
    public Long getUserId() { return userId; }
    public String getServiceId() { return serviceId; }
    public boolean isShared() { return "shared:business".equals(actorKey); }
    public boolean isService() { return serviceId != null; }
    public boolean allows(String operation) { return operations.contains(operation); }
    public Set<String> getSourceIds() { return sourceIds; }

    public void requireOperation(String operation) {
        if (operation == null || !operations.contains(operation)) {
            throw BusinessException.forbidden();
        }
    }

    public void requireSource(String sourceId) {
        if (!sourceIds.contains(canonicalSource(sourceId))) {
            throw BusinessException.forbidden();
        }
    }

    public Set<String> authorizedSources(Collection<String> requested) {
        if (requested == null) {
            return sourceIds;
        }
        Set<String> result = new LinkedHashSet<>();
        for (String sourceId : requested) {
            requireSource(sourceId);
            result.add(sourceId);
        }
        return Collections.unmodifiableSet(result);
    }

    static String canonicalSource(String value) {
        try {
            if (value == null || value.length() != 36 || !UUID.fromString(value).toString().equals(value)
                    || UUID.fromString(value).equals(new UUID(0L, 0L))) {
                throw BusinessException.invalid("source_id须为规范UUID");
            }
            return value;
        } catch (IllegalArgumentException exception) {
            throw BusinessException.invalid("source_id须为规范UUID");
        }
    }
}
