package edu.cqupt.hxjm.framework.manager;

import java.util.TimerTask;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import edu.cqupt.hxjm.common.utils.Threads;
import edu.cqupt.hxjm.common.utils.spring.SpringUtils;

/**
 * 异步任务管理器
 * 
 * @author ruoyi
 */
public class AsyncManager
{
    /**
     * 操作延迟10毫秒
     */
    private final int OPERATE_DELAY_TIME = 10;

    /**
     * 异步操作任务调度线程池
     */
    private ScheduledExecutorService executor;

    /**
     * 单例模式
     */
    private AsyncManager(){}

    private static AsyncManager me = new AsyncManager();

    public static AsyncManager me()
    {
        return me;
    }

    private ScheduledExecutorService getExecutor()
    {
        if (executor != null)
        {
            return executor;
        }
        try
        {
            executor = SpringUtils.getBean("scheduledExecutorService");
        }
        catch (Throwable ignored)
        {
            return null;
        }
        return executor;
    }

    /**
     * 执行任务
     * 
     * @param task 任务
     */
    public void execute(TimerTask task)
    {
        ScheduledExecutorService executor = getExecutor();
        if (executor == null)
        {
            return;
        }
        executor.schedule(task, OPERATE_DELAY_TIME, TimeUnit.MILLISECONDS);
    }

    /**
     * 停止任务线程池
     */
    public void shutdown()
    {
        ScheduledExecutorService executor = this.executor;
        if (executor == null)
        {
            executor = getExecutor();
        }
        if (executor == null)
        {
            return;
        }
        Threads.shutdownAndAwaitTermination(executor);
    }
}
