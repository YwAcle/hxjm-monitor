package edu.cqupt.hxjm.framework.aspectj;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Pointcut;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import edu.cqupt.hxjm.common.enums.DataSourceType;
import edu.cqupt.hxjm.framework.datasource.DynamicDataSourceContextHolder;

@Aspect
@Order(3)
@Component
public class DefaultMasterDataSourceAspect
{
    @Pointcut("within(edu.cqupt.hxjm..*)"
            + " && !within(edu.cqupt.hxjm.algdeployment..*)"
            + " && !within(edu.cqupt.hxjm.framework..*)"
            + " && !within(edu.cqupt.hxjm.common..*)")
    public void defaultMasterPointCut()
    {

    }

    @Around("defaultMasterPointCut()")
    public Object around(ProceedingJoinPoint point) throws Throwable
    {
        String previous = DynamicDataSourceContextHolder.getDataSourceType();
        DynamicDataSourceContextHolder.setDataSourceType(DataSourceType.MASTER.name());
        try
        {
            return point.proceed();
        }
        finally
        {
            if (previous == null || previous.trim().isEmpty())
            {
                DynamicDataSourceContextHolder.clearDataSourceType();
            }
            else
            {
                DynamicDataSourceContextHolder.setDataSourceType(previous);
            }
        }
    }
}
