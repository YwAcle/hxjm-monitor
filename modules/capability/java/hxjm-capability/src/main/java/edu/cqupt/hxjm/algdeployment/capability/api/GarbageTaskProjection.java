package edu.cqupt.hxjm.algdeployment.capability.api;
import org.springframework.stereotype.Component;
import org.springframework.context.event.EventListener;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import edu.cqupt.hxjm.algdeployment.business.service.GarbageBusinessService;
import edu.cqupt.hxjm.algdeployment.capability.service.TaskExecutionChanged;
/** Business projection belongs at the integration boundary, never in the device executor. */
@Component
@ConditionalOnProperty(prefix="hxjm.business",name="enabled",havingValue="true")
public class GarbageTaskProjection {
    private final GarbageBusinessService business;
    public GarbageTaskProjection(GarbageBusinessService business){this.business=business;}
    @EventListener public void changed(TaskExecutionChanged event){business.refreshCleanup(event.taskId);}
}
