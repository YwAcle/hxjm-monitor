package edu.cqupt.hxjm.algdeployment.business.security;

import java.security.SecureRandom;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;

/** Short-lived, single-asset grants let native video issue HTTP Range requests. */
@Component
@ConditionalOnProperty(prefix = "hxjm.business", name = "enabled", havingValue = "true")
public class PlaybackTickets {
    private final Map<String, Ticket> tickets = new ConcurrentHashMap<>();
    private final SecureRandom random = new SecureRandom();
    private final Clock clock;
    private static final int LIMIT = 10000;
    private static final long LIFETIME_MS = 300000;

    public PlaybackTickets() { this(Clock.systemUTC()); }
    PlaybackTickets(Clock clock) { this.clock = clock; }

    public synchronized Map<String, Object> issue(BusinessActor actor, String assetId, OffsetDateTime assetExpiry) {
        actor.requireOperation("media.resolve");
        long now = clock.millis();
        tickets.entrySet().removeIf(entry -> entry.getValue().expiresAt <= now);
        if (tickets.size() >= LIMIT) { throw BusinessException.unavailable("播放凭证暂时已满，请稍后重试"); }
        long expiresAt = assetExpiry == null ? now + LIFETIME_MS : Math.min(now + LIFETIME_MS, assetExpiry.toInstant().toEpochMilli());
        if (expiresAt <= now) { throw BusinessException.expired("资产已到期"); }
        byte[] bytes = new byte[32];
        String token;
        do {
            random.nextBytes(bytes);
            token = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        } while (tickets.putIfAbsent(token, new Ticket(actor, assetId, expiresAt)) != null);
        return edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.values(
                "url", "/api/v1/business/assets/" + assetId + "/content?ticket=" + token,
                "expires_at", OffsetDateTime.ofInstant(java.time.Instant.ofEpochMilli(expiresAt), ZoneOffset.UTC).toString());
    }

    public BusinessActor require(String token, String assetId) {
        Ticket ticket = token == null ? null : tickets.get(token);
        if (ticket == null || !ticket.assetId.equals(assetId)) { throw BusinessException.unauthenticated(); }
        if (ticket.expiresAt <= clock.millis()) {
            tickets.remove(token, ticket);
            throw BusinessException.unauthenticated();
        }
        return ticket.actor;
    }

    private static final class Ticket {
        final BusinessActor actor;
        final String assetId;
        final long expiresAt;
        Ticket(BusinessActor actor, String assetId, long expiresAt) {
            this.actor = actor; this.assetId = assetId; this.expiresAt = expiresAt;
        }
    }
}
