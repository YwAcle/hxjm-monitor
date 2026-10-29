package edu.cqupt.hxjm.algdeployment.business.api;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import javax.servlet.http.HttpServletRequest;

public final class BusinessResponses {
    private static final String TRACE_ATTRIBUTE = BusinessResponses.class.getName() + ".traceId";

    private BusinessResponses() { }

    public static String traceId(HttpServletRequest request, String candidate) {
        Object existing = request.getAttribute(TRACE_ATTRIBUTE);
        if (existing instanceof String) {
            return (String) existing;
        }
        String value = candidate != null ? candidate : request.getHeader("X-Trace-Id");
        if (value != null && (value.length() < 1 || value.length() > 128
                || value.chars().anyMatch(character -> character < 32 || character > 126))) {
            throw BusinessException.invalid("trace_id须为1至128个可打印ASCII字符");
        }
        value = value == null ? UUID.randomUUID().toString() : value;
        request.setAttribute(TRACE_ATTRIBUTE, value);
        return value;
    }

    public static Map<String, Object> success(Map<String, ?> data, HttpServletRequest request,
                                               String traceId) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.putAll(data);
        response.put("trace_id", traceId(request, traceId));
        return response;
    }

    static Map<String, Object> failure(BusinessException exception, HttpServletRequest request) {
        String trace;
        try {
            trace = traceId(request, null);
        } catch (BusinessException invalidTrace) {
            trace = UUID.randomUUID().toString();
            request.setAttribute(TRACE_ATTRIBUTE, trace);
        }
        Map<String, Object> error = new LinkedHashMap<>();
        error.put("code", exception.getCode());
        error.put("message", exception.getMessage());
        error.put("retryable", exception.isRetryable());
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("error", error);
        response.put("trace_id", trace);
        return response;
    }
}
