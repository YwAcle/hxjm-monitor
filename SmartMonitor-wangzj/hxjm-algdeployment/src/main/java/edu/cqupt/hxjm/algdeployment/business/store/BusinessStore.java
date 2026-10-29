package edu.cqupt.hxjm.algdeployment.business.store;

import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;

@Component
@ConditionalOnProperty(prefix = "hxjm.business", name = "enabled", havingValue = "true")
public class BusinessStore {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate transaction;

    public BusinessStore(@Qualifier("slaveDataSource") DataSource dataSource) {
        jdbc = new JdbcTemplate(dataSource);
        transaction = new TransactionTemplate(new DataSourceTransactionManager(dataSource));
    }

    public JdbcTemplate jdbc() { return jdbc; }

    public Map<String, Object> write(BusinessActor actor, String operation, Map<String, Object> body,
                                      OffsetDateTime expiresAt,
                                      Function<JdbcTemplate, Map<String, Object>> work) {
        actor.requireOperation(operation);
        String requestId = BusinessValues.text(body, "request_id", 128);
        Map<String, Object> immutable = new LinkedHashMap<>(body);
        immutable.remove("request_id");
        immutable.remove("trace_id");
        String digest = BusinessCanonical.digest(immutable);
        try {
            return transaction.execute(status -> {
                // A transaction-scoped lock serializes even the first insert; unique PK remains authoritative.
                jdbc.queryForObject("SELECT pg_advisory_xact_lock(hashtextextended(?,0)) IS NULL",
                        Boolean.class, actor.getActorKey() + "\n" + operation + "\n" + requestId);
                List<Map<String, Object>> existing = jdbc.queryForList(
                        "SELECT request_digest,state,response_json::text,expires_at>now() AS valid FROM public.request_deduplication "
                                + "WHERE actor_key=? AND operation=? AND request_id=? FOR UPDATE",
                        actor.getActorKey(), operation, requestId);
                if (!existing.isEmpty()) {
                    Map<String, Object> record = existing.get(0);
                    if (!digest.equals(record.get("request_digest"))) { throw BusinessException.conflict("相同请求标识对应不同内容"); }
                    if (!Boolean.TRUE.equals(record.get("valid"))) { throw BusinessException.expired("原请求已到期"); }
                    if (!"completed".equals(record.get("state")) || record.get("response_json") == null) {
                        throw BusinessException.conflict("请求尚未完成，须核对原请求状态");
                    }
                    Map<String, Object> response = BusinessValues.parse(record.get("response_json").toString());
                    response.put("duplicate", true);
                    return response;
                }
                if (expiresAt == null || !expiresAt.isAfter(OffsetDateTime.now())) {
                    throw BusinessException.expired("业务请求已到期");
                }
                jdbc.update("INSERT INTO public.request_deduplication(actor_key,operation,request_id,request_digest,expires_at) "
                                + "VALUES (?,?,?,?,?)", actor.getActorKey(), operation, requestId, digest, expiresAt);
                Map<String, Object> result = work.apply(jdbc);
                result.putIfAbsent("duplicate", false);
                jdbc.update("UPDATE public.request_deduplication SET state='completed',response_json=?::jsonb,updated_at=now() "
                                + "WHERE actor_key=? AND operation=? AND request_id=?",
                        BusinessValues.json(result), actor.getActorKey(), operation, requestId);
                return result;
            });
        } catch (DataIntegrityViolationException exception) { throw BusinessException.conflict("数据唯一性、关联或状态约束冲突"); }
        catch (TransientDataAccessException | DataAccessResourceFailureException exception) {
            throw BusinessException.unavailable("业务存储暂不可用，请保留原请求标识重试");
        }
    }

    public void event(JdbcTemplate connection, String eventType, String aggregateType, String id,
                      long revision, Map<String, Object> payload, OffsetDateTime expiresAt) {
        connection.update("INSERT INTO public.outbox_event(event_type,aggregate_type,aggregate_id,aggregate_revision,payload_json,expires_at) "
                        + "VALUES (?,?,?::uuid,?,?::jsonb,?) ON CONFLICT (event_type,aggregate_type,aggregate_id,aggregate_revision) DO NOTHING",
                eventType, aggregateType, id, revision, BusinessValues.json(payload), expiresAt);
    }
}
