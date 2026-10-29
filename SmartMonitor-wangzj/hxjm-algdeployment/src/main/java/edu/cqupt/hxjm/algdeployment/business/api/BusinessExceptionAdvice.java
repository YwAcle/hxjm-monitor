package edu.cqupt.hxjm.algdeployment.business.api;

import java.util.Map;
import javax.servlet.http.HttpServletRequest;
import javax.validation.ConstraintViolationException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.annotation.Order;
import org.springframework.http.ResponseEntity;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@Order(Ordered.HIGHEST_PRECEDENCE)
@RestControllerAdvice(basePackages = "edu.cqupt.hxjm.algdeployment.business.api")
@ConditionalOnProperty(prefix = "hxjm.business", name = "enabled", havingValue = "true")
public class BusinessExceptionAdvice {
    private static final Logger LOGGER = LoggerFactory.getLogger(BusinessExceptionAdvice.class);

    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<Map<String, Object>> business(BusinessException exception,
                                                        HttpServletRequest request) {
        return ResponseEntity.status(exception.getStatus()).body(BusinessResponses.failure(exception, request));
    }

    @ExceptionHandler({HttpMessageNotReadableException.class, MethodArgumentNotValidException.class,
            MissingServletRequestParameterException.class, MethodArgumentTypeMismatchException.class,
            ConstraintViolationException.class})
    public ResponseEntity<Map<String, Object>> invalid(Exception exception, HttpServletRequest request) {
        return business(BusinessException.invalid("请求字段或JSON格式不正确"), request);
    }

    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    public ResponseEntity<Map<String, Object>> method(Exception exception, HttpServletRequest request) {
        return business(new BusinessException("METHOD_NOT_ALLOWED", "请求方法不支持", 405, false), request);
    }

    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    public ResponseEntity<Map<String, Object>> media(Exception exception, HttpServletRequest request) {
        return business(new BusinessException("UNSUPPORTED_MEDIA_TYPE", "请求媒体类型不支持", 415, false), request);
    }

    @ExceptionHandler({DataAccessResourceFailureException.class, TransientDataAccessException.class})
    public ResponseEntity<Map<String, Object>> dependency(Exception exception, HttpServletRequest request) {
        return business(BusinessException.unavailable("业务存储暂不可用"), request);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, Object>> unexpected(Exception exception, HttpServletRequest request) {
        BusinessException failure = new BusinessException("INTERNAL_ERROR", "请求处理失败", 500, false);
        Map<String, Object> response = BusinessResponses.failure(failure, request);
        // Exception messages may contain database parameters or storage credentials.
        LOGGER.error("Business request failed trace_id={} exception_type={}", response.get("trace_id"),
                exception.getClass().getName());
        return ResponseEntity.status(500).body(response);
    }
}
