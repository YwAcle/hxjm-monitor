package edu.cqupt.hxjm.algdeployment.business.api;

import java.io.IOException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.servlet.ModelAndView;
import org.springframework.web.servlet.handler.AbstractHandlerExceptionResolver;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessValues;

/** Mapping errors have no controller, so package-scoped controller advice cannot handle them. */
@Component
@ConditionalOnProperty(prefix = "hxjm.business", name = "enabled", havingValue = "true")
public class BusinessDispatchExceptionResolver extends AbstractHandlerExceptionResolver {
    public BusinessDispatchExceptionResolver() {
        setOrder(Ordered.HIGHEST_PRECEDENCE);
    }

    @Override
    protected ModelAndView doResolveException(HttpServletRequest request, HttpServletResponse response,
                                               Object handler, Exception exception) {
        String path = request.getRequestURI().substring(request.getContextPath().length());
        if (!(path.equals("/api/v1/business") || path.startsWith("/api/v1/business/"))) {
            return null;
        }
        BusinessException failure;
        if (exception instanceof HttpRequestMethodNotSupportedException) {
            failure = new BusinessException("METHOD_NOT_ALLOWED", "请求方法不支持", 405, false);
            String[] supported = ((HttpRequestMethodNotSupportedException) exception).getSupportedMethods();
            if (supported != null) { response.setHeader("Allow", String.join(", ", supported)); }
        } else if (exception instanceof HttpMediaTypeNotSupportedException) {
            failure = new BusinessException("UNSUPPORTED_MEDIA_TYPE", "请求媒体类型不支持", 415, false);
        } else {
            return null;
        }
        response.setStatus(failure.getStatus());
        response.setCharacterEncoding("UTF-8");
        response.setContentType("application/json");
        try {
            response.getWriter().write(BusinessValues.json(BusinessResponses.failure(failure, request)));
        } catch (IOException disconnected) {
            logger.warn("Could not write business dispatch error response");
        }
        return new ModelAndView();
    }
}
