package edu.cqupt.hxjm.algdeployment.business.security;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.lang.reflect.Proxy;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessDispatchExceptionResolver;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessExceptionAdvice;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessResponses;
import edu.cqupt.hxjm.common.core.domain.entity.SysUser;
import edu.cqupt.hxjm.common.core.domain.model.LoginUser;

/** Run main with the module test classpath; no application, database or Redis is started. */
public final class BusinessSecurityCheck {
    private static final String SOURCE = "10000000-0000-4000-8000-000000000001";
    private static final String OTHER_SOURCE = "10000000-0000-4000-8000-000000000002";
    private static final String OPERATION = "results.register";

    public static void main(String[] args) {
        try {
            sharedScope();
            serviceScope();
            userScope();
            configurationValidation();
            responseContract();
            dispatchContract();
            playbackTickets();
            System.out.println("BusinessSecurityCheck passed");
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private static void sharedScope() {
        javax.sql.DataSource ds = (javax.sql.DataSource) Proxy.newProxyInstance(
                BusinessSecurityCheck.class.getClassLoader(), new Class<?>[]{javax.sql.DataSource.class},
                (proxy, method, args) -> { throw new AssertionError("No database connection permitted"); });
        edu.cqupt.hxjm.algdeployment.business.store.BusinessStore store =
                new edu.cqupt.hxjm.algdeployment.business.store.BusinessStore(ds) {
            @Override public org.springframework.jdbc.core.JdbcTemplate jdbc() {
                return new org.springframework.jdbc.core.JdbcTemplate() {
                    @Override public <T> java.util.List<T> queryForList(String sql, Class<T> type) {
                        check("SELECT id::text FROM public.camera ORDER BY id".equals(sql), "shared source directory");
                        return Collections.singletonList(type.cast(SOURCE));
                    }
                };
            }
        };
        BusinessAuthentication auth = new BusinessAuthentication(configured(), store);
        SecurityContextHolder.clearContext();
        for (String operation : Arrays.asList("sources.query", "results.query", "assets.query", "media.resolve",
                "assets.upload", "identities.register", "identities.query", "tracklets.query", "queries.create", "queries.get",
                "queries.select", "search.execute", "samples.query", "activities.query", "events.query", "reports.query")) {
            BusinessActor actor = auth.authenticate(request("Authorization", "Bearer obsolete"), operation);
            check(actor.isShared() && actor.getUserId() == null && !actor.isService(), "shared actor without fabricated user");
            actor.requireSource(SOURCE);
            fails(403, () -> actor.requireSource(OTHER_SOURCE));
            fails(403, () -> actor.requireOperation("results.register"));
        }
        for (String operation : Arrays.asList("results.register", "streams.open", "assets.register", "features.register",
                "activities.close", "events.register", "reports.register", "tasks.submit", "instances.configure")) {
            fails(401, () -> auth.authenticate(request(), operation));
            fails(401, () -> auth.requireService(request(), operation));
        }
        fails(401, () -> auth.authenticate(service("wrong"), "media.resolve"));
        fails(403, () -> auth.requireService(request(), "media.resolve"));
        fails(403, () -> auth.requireUser(request(), "media.resolve"));
    }

    private static void playbackTickets() {
        java.util.concurrent.atomic.AtomicLong now = new java.util.concurrent.atomic.AtomicLong(1000000L);
        java.time.Clock clock = new java.time.Clock() {
            public java.time.ZoneId getZone() { return java.time.ZoneOffset.UTC; }
            public java.time.Clock withZone(java.time.ZoneId zone) { return this; }
            public java.time.Instant instant() { return java.time.Instant.ofEpochMilli(now.get()); }
        };
        PlaybackTickets tickets = new PlaybackTickets(clock);
        BusinessSecurityProperties.Grant grant = grant();
        grant.getOperations().add("media.resolve");
        BusinessActor actor = new BusinessActor("user:1", 1L, null, grant);
        String asset = "20000000-0000-4000-8000-000000000001";
        java.time.OffsetDateTime expiry = clock.instant().plusSeconds(60).atOffset(java.time.ZoneOffset.UTC);
        Map<String, Object> response = tickets.issue(actor, asset, expiry);
        String token = response.get("url").toString().split("ticket=")[1];
        check(actor == tickets.require(token, asset), "ticket preserves limited actor grant");
        check(expiry.equals(java.time.OffsetDateTime.parse(response.get("expires_at").toString())), "ticket cannot outlive asset");
        fails(401, () -> tickets.require(token, "20000000-0000-4000-8000-000000000002"));
        fails(401, () -> tickets.require(token + "x", asset));
        fails(401, () -> tickets.require(null, asset));
        now.addAndGet(60000);
        fails(401, () -> tickets.require(token, asset));
        fails(410, () -> tickets.issue(actor, asset, expiry));
        Map<String, Object> longLived = tickets.issue(actor, asset, expiry.plusDays(1));
        check(java.time.OffsetDateTime.parse(longLived.get("expires_at").toString()).toInstant().toEpochMilli() == now.get() + 300000,
                "ticket maximum lifetime is five minutes");
        System.out.println("Playback ticket scope and expiry passed");
    }

    private static void serviceScope() {
        BusinessSecurityProperties properties = configured();
        BusinessAuthentication auth = new BusinessAuthentication(properties);
        auth.afterPropertiesSet();
        SecurityContextHolder.clearContext();
        fails(401, () -> auth.authenticate(request(), OPERATION));
        fails(401, () -> auth.authenticate(request("Authorization", "Bearer unverified"), OPERATION));
        fails(401, () -> auth.authenticate(request("X-HXJM-Service-Id", "tracker"), OPERATION));
        fails(401, () -> auth.authenticate(request("X-HXJM-Service-Token", "test-secret"), OPERATION));
        fails(401, () -> auth.authenticate(service("wrong"), OPERATION));
        BusinessActor actor = auth.requireService(service("test-secret"), OPERATION);
        check(actor.isService() && "service:tracker".equals(actor.getActorKey()), "stable service actor");
        check(actor.getUserId() == null && "tracker".equals(actor.getServiceId()), "service identity");
        actor.requireSource(SOURCE);
        fails(403, () -> actor.requireOperation("streams.open"));
        fails(403, () -> actor.requireSource(OTHER_SOURCE));
        fails(400, () -> actor.requireSource("10000000-0-4000-8000-1"));
        fails(400, () -> actor.requireSource("00000000-0000-0000-0000-000000000000"));
        check(actor.authorizedSources(null).equals(Collections.singleton(SOURCE)), "implicit source scope");
        check(actor.authorizedSources(Collections.emptySet()).isEmpty(), "empty scope remains empty");
        fails(403, () -> actor.authorizedSources(Arrays.asList(SOURCE, OTHER_SOURCE)));
        properties.getServices().get("tracker").getSourceIds().add(OTHER_SOURCE);
        fails(403, () -> actor.requireSource(OTHER_SOURCE));
        try {
            actor.getSourceIds().add(OTHER_SOURCE);
            throw new AssertionError("actor scope must be immutable");
        } catch (UnsupportedOperationException expected) { }
        fails(403, () -> auth.requireUser(service("test-secret"), OPERATION));
    }

    private static void userScope() {
        BusinessSecurityProperties properties = configured();
        BusinessAuthentication auth = new BusinessAuthentication(properties);
        auth.afterPropertiesSet();
        SecurityContextHolder.getContext().setAuthentication(new AnonymousAuthenticationToken("test", "anonymousUser",
                Collections.singleton(new SimpleGrantedAuthority("ROLE_ANONYMOUS"))));
        fails(401, () -> auth.authenticate(request(), OPERATION));
        LoginUser login = login(1L);
        authenticate(login);
        // A platform administrator is still denied until explicitly granted a new business operation.
        fails(403, () -> auth.authenticate(request(), OPERATION));
        properties.getUsers().put(1L, grant());
        BusinessActor actor = auth.requireUser(request(), OPERATION);
        check(!actor.isService() && "user:1".equals(actor.getActorKey()), "stable user actor");
        check(Long.valueOf(1L).equals(actor.getUserId()), "user ID");
        actor.requireSource(SOURCE);
        fails(403, () -> auth.requireService(request(), OPERATION));
        fails(401, () -> auth.authenticate(request("X-HXJM-Service-Id", "tracker"), OPERATION));
        fails(401, () -> auth.authenticate(service("wrong"), OPERATION));
        login.setExpireTime(System.currentTimeMillis() - 1);
        fails(401, () -> auth.authenticate(request(), OPERATION));
        login.setExpireTime(System.currentTimeMillis() + 60000);
        login.getUser().setStatus("1");
        fails(401, () -> auth.authenticate(request(), OPERATION));
        login.getUser().setStatus("0");
        login.getUser().setDelFlag("2");
        fails(401, () -> auth.authenticate(request(), OPERATION));
        login.getUser().setDelFlag("0");
        SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken(login, null));
        fails(401, () -> auth.authenticate(request(), OPERATION));
        SecurityContextHolder.clearContext();
    }

    private static void configurationValidation() {
        new BusinessAuthentication(new BusinessSecurityProperties()).afterPropertiesSet();
        BusinessSecurityProperties properties = configured();
        properties.getServices().get("tracker").getOperations().add("*");
        invalidConfiguration(properties);
        properties = configured();
        properties.getServices().get("tracker").getSourceIds().add("not-a-uuid");
        invalidConfiguration(properties);
        properties = configured();
        properties.getServices().get("tracker").setToken(" ");
        invalidConfiguration(properties);
        properties = configured();
        properties.getServices().put("another", properties.getServices().get("tracker"));
        invalidConfiguration(properties);
    }

    private static void responseContract() {
        BusinessExceptionAdvice advice = new BusinessExceptionAdvice();
        ResponseEntity<Map<String, Object>> response = advice.business(BusinessException.forbidden(), request("X-Trace-Id", "trace-1"));
        check(response.getStatusCodeValue() == 403, "actual error HTTP status");
        Map<?, ?> error = (Map<?, ?>) response.getBody().get("error");
        check("FORBIDDEN".equals(error.get("code")) && Boolean.FALSE.equals(error.get("retryable")), "typed error");
        check("trace-1".equals(response.getBody().get("trace_id")), "correlation trace");
        check(!response.getBody().containsKey("data"), "error has no success payload");
        ResponseEntity<Map<String, Object>> unavailable = advice.business(BusinessException.unavailable("存储暂不可用"), request());
        check(unavailable.getStatusCodeValue() == 503
                && Boolean.TRUE.equals(((Map<?, ?>) unavailable.getBody().get("error")).get("retryable")), "retryable dependency failure");
        HttpServletRequest invalidTrace = request("X-Trace-Id", "bad\ntrace");
        fails(400, () -> BusinessResponses.traceId(invalidTrace, null));
        ResponseEntity<Map<String, Object>> safe = advice.invalid(new IllegalArgumentException("private credential"), invalidTrace);
        check(!safe.getBody().toString().contains("private credential")
                && !safe.getBody().get("trace_id").toString().contains("\n"), "safe error response");
        HttpServletRequest request = request();
        String trace = BusinessResponses.traceId(request, null);
        check(trace.equals(BusinessResponses.success(Collections.singletonMap("saved", true), request, null).get("trace_id")), "stable trace per request");
        RestControllerAdvice scope = BusinessExceptionAdvice.class.getAnnotation(RestControllerAdvice.class);
        check(Arrays.equals(scope.basePackages(), new String[]{"edu.cqupt.hxjm.algdeployment.business.api"}), "old API isolation");
        check(BusinessExceptionAdvice.class.getAnnotation(Order.class).value() == Ordered.HIGHEST_PRECEDENCE, "scoped advice precedence");
    }

    private static BusinessSecurityProperties configured() {
        BusinessSecurityProperties properties = new BusinessSecurityProperties();
        BusinessSecurityProperties.ServiceIdentity service = new BusinessSecurityProperties.ServiceIdentity();
        service.setToken("test-secret");
        service.setOperations(grant().getOperations());
        service.setSourceIds(grant().getSourceIds());
        properties.getServices().put("tracker", service);
        return properties;
    }

    private static void dispatchContract() {
        BusinessDispatchExceptionResolver resolver = new BusinessDispatchExceptionResolver();
        Map<String, Object> captured = new HashMap<>();
        StringWriter body = new StringWriter();
        HttpServletResponse response = (HttpServletResponse) Proxy.newProxyInstance(
                BusinessSecurityCheck.class.getClassLoader(), new Class<?>[]{HttpServletResponse.class},
                (proxy, method, args) -> {
                    if ("getWriter".equals(method.getName())) { return new PrintWriter(body); }
                    if (method.getName().startsWith("set")) { captured.put(method.getName(), args[0]); return null; }
                    throw new AssertionError("Unexpected response method: " + method.getName());
                });
        HttpRequestMethodNotSupportedException method = new HttpRequestMethodNotSupportedException(
                "DELETE", new String[]{"GET", "POST"});
        check(resolver.resolveException(requestPath("", "/old/results"), response, null, method) == null,
                "old route mapping errors remain untouched");
        check(resolver.resolveException(requestPath("", "/api/v1/business-other/results"), response, null, method) == null,
                "prefix lookalike remains untouched");
        check(captured.isEmpty() && body.toString().isEmpty(), "old route response untouched");
        check(resolver.resolveException(requestPath("/app", "/api/v1/business/results"), response, null, method) != null,
                "business route mapping error handled without a controller");
        check(Integer.valueOf(405).equals(captured.get("setStatus")) && body.toString().contains("METHOD_NOT_ALLOWED"),
                "business 405 uses actual status and typed JSON");
        body.getBuffer().setLength(0);
        check(resolver.resolveException(request(), response, null, new HttpMediaTypeNotSupportedException("test")) != null,
                "business media error handled");
        check(Integer.valueOf(415).equals(captured.get("setStatus")) && body.toString().contains("UNSUPPORTED_MEDIA_TYPE"),
                "business 415 uses actual status and typed JSON");
        check(resolver.resolveException(request(), response, null, new IllegalArgumentException()) == null,
                "unrelated errors use controller advice");
    }

    private static BusinessSecurityProperties.Grant grant() {
        BusinessSecurityProperties.Grant grant = new BusinessSecurityProperties.Grant();
        grant.setOperations(new LinkedHashSet<>(Collections.singleton(OPERATION)));
        grant.setSourceIds(new LinkedHashSet<>(Collections.singleton(SOURCE)));
        return grant;
    }

    private static LoginUser login(Long id) {
        SysUser user = new SysUser();
        user.setUserId(id);
        user.setStatus("0");
        user.setDelFlag("0");
        LoginUser login = new LoginUser(id, null, user, Collections.singleton("*:*:*"));
        login.setExpireTime(System.currentTimeMillis() + 60000);
        return login;
    }

    private static void authenticate(LoginUser login) {
        SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken(
                login, null, Collections.emptyList()));
    }

    private static HttpServletRequest service(String token) {
        return request("X-HXJM-Service-Id", "tracker", "X-HXJM-Service-Token", token);
    }

    private static HttpServletRequest request(String... pairs) {
        return requestPath("", "/api/v1/business/results", pairs);
    }

    private static HttpServletRequest requestPath(String contextPath, String path, String... pairs) {
        Map<String, String> headers = new HashMap<>();
        Map<String, Object> attributes = new HashMap<>();
        for (int i = 0; i < pairs.length; i += 2) { headers.put(pairs[i], pairs[i + 1]); }
        return (HttpServletRequest) Proxy.newProxyInstance(BusinessSecurityCheck.class.getClassLoader(),
                new Class<?>[]{HttpServletRequest.class}, (proxy, method, args) -> {
                    if ("getRequestURI".equals(method.getName())) { return contextPath + path; }
                    if ("getContextPath".equals(method.getName())) { return contextPath; }
                    if ("getHeader".equals(method.getName())) { return headers.get(args[0]); }
                    if ("getAttribute".equals(method.getName())) { return attributes.get(args[0]); }
                    if ("setAttribute".equals(method.getName())) { attributes.put((String) args[0], args[1]); return null; }
                    throw new AssertionError("Unexpected request method: " + method.getName());
                });
    }

    private static void fails(int status, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected HTTP " + status);
        } catch (BusinessException exception) {
            check(exception.getStatus() == status, "expected HTTP " + status + " but was " + exception.getStatus());
        }
    }

    private static void invalidConfiguration(BusinessSecurityProperties properties) {
        try {
            new BusinessAuthentication(properties).afterPropertiesSet();
            throw new AssertionError("Invalid security configuration was accepted");
        } catch (IllegalArgumentException expected) { }
    }

    private static void check(boolean condition, String message) {
        if (!condition) { throw new AssertionError(message); }
    }
}
