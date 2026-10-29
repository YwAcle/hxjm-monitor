package edu.cqupt.hxjm.algdeployment.business.api;

/** Errors for the new business API; existing AjaxResult endpoints keep their contract. */
public class BusinessException extends RuntimeException {
    private final String code;
    private final int status;
    private final boolean retryable;

    public BusinessException(String code, String message, int status, boolean retryable) {
        super(message);
        this.code = code;
        this.status = status;
        this.retryable = retryable;
    }

    public String getCode() { return code; }
    public int getStatus() { return status; }
    public boolean isRetryable() { return retryable; }

    public static BusinessException invalid(String message) {
        return new BusinessException("INVALID_ARGUMENT", message, 400, false);
    }
    public static BusinessException unauthenticated() {
        return new BusinessException("UNAUTHENTICATED", "身份缺失或已失效", 401, false);
    }
    public static BusinessException forbidden() {
        return new BusinessException("FORBIDDEN", "无权执行该操作或访问指定来源", 403, false);
    }
    public static BusinessException notFound(String message) {
        return new BusinessException("NOT_FOUND", message, 404, false);
    }
    public static BusinessException conflict(String message) {
        return new BusinessException("CONFLICT", message, 409, false);
    }
    public static BusinessException expired(String message) {
        return new BusinessException("EXPIRED", message, 410, false);
    }
    public static BusinessException unavailable(String message) {
        return new BusinessException("DEPENDENCY_UNAVAILABLE", message, 503, true);
    }
}
