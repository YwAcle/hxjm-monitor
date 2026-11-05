package edu.cqupt.hxjm.algdeployment.business.service;

import java.util.Collections;
import java.util.List;
import java.util.Map;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.values;

/** Public metadata only; authority: contracts/capability-v1/result-context.schema.json. */
public final class ResultContext {
    private ResultContext() {}

    public static Map<String,Object> of(Object result, Object capability, Object producer,
            String mode, Object task, Object run, List<?> sources, Object type, Object version,
            Object producerKey, Object occurredAt, Object registeredAt, Object asset) {
        return values("contract_version","1","result_id",String.valueOf(result),
            "capability_code",capability,"producer_id",producer,"production_mode",mode,
            "task_id",String.valueOf(task),"run_id",String.valueOf(run),"source_ids",sources,
            "result_type",type,"schema_version",version,"producer_result_key",producerKey,
            "occurred_at",occurredAt,"registered_at",registeredAt,
            "evidence_refs",asset==null?Collections.emptyList():Collections.singletonList(
                values("kind","asset","id",String.valueOf(asset))));
    }
}
