package edu.cqupt.hxjm.algdeployment.business.service;

import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessStore;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessValues;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

@Service
@ConditionalOnProperty(prefix = "hxjm.business", name = "enabled", havingValue = "true")
public class SourceStreamService {
    private final BusinessStore store;

    public SourceStreamService(BusinessStore store) { this.store = store; }

    public Map<String, Object> sources(BusinessActor actor, List<String> requested, String after, int size) {
        if (size < 1 || size > 200) { throw BusinessException.invalid("page_size须为1至200"); }
        Set<String> allowed = actor.authorizedSources(requested);
        if (after != null) { uuid(after, "cursor"); }
        if (allowed.isEmpty()) { return values("items", Collections.emptyList(), "next_cursor", null, "has_more", false); }
        List<Object> arguments = new ArrayList<>(allowed);
        String sql = "SELECT id::text AS source_id,camera_code, name AS display_name,management_device_id::text,channel_code,source_kind,enabled "
                + "FROM public.camera WHERE id IN (" + placeholders(allowed.size()) + ")";
        if (after != null) { sql += " AND id>?::uuid"; arguments.add(after); }
        sql += " ORDER BY id LIMIT ?";
        arguments.add(size + 1);
        List<Map<String, Object>> items = store.jdbc().queryForList(sql, arguments.toArray());
        boolean more = items.size() > size;
        if (more) { items.remove(items.size() - 1); }
        for (Map<String, Object> item : items) {
            List<Map<String, Object>> streams = store.jdbc().queryForList(
                    "SELECT id::text AS stream_id,stream_name,task_type,is_active FROM public.camera_stream WHERE camera_id=?::uuid ORDER BY id",
                    item.get("source_id"));
            item.put("streams", streams);
            item.put("stream_id", streams.size() == 1 ? streams.get(0).get("stream_id") : null);
            item.put("stream_name", streams.size() == 1 ? streams.get(0).get("stream_name") : null);
        }
        return values("items", items, "next_cursor", more ? items.get(items.size() - 1).get("source_id") : null, "has_more", more);
    }

    public Map<String, Object> register(BusinessActor actor, Map<String, Object> body) {
        fields(body, "request_id", "trace_id", "source_id", "camera_code", "display_name", "management_device_id", "channel_code", "source_kind", "timezone");
        String sourceId = uuid(body, "source_id");
        if (java.util.UUID.fromString(sourceId).version()!=4) { throw BusinessException.invalid("新来源标识须为UUIDv4"); }
        actor.requireSource(sourceId);
        String code = text(body, "camera_code", 128);
        String name = text(body, "display_name", 128);
        String kind = body.containsKey("source_kind") ? text(body, "source_kind", 24) : "camera";
        if (!java.util.Arrays.asList("camera", "device_video", "imported_video").contains(kind)) { throw BusinessException.invalid("source_kind无效"); }
        String timezone = body.containsKey("timezone") ? text(body, "timezone", 64) : "Asia/Shanghai";
        if(!ZoneId.getAvailableZoneIds().contains(timezone)){throw BusinessException.invalid("timezone须为IANA时区");}
        String channel = body.containsKey("channel_code") ? text(body, "channel_code", 64) : null;
        Long deviceId = null;
        if (body.containsKey("management_device_id")) {
            String value = text(body, "management_device_id", 19);
            try { deviceId = Long.valueOf(value); if (deviceId <= 0 || !deviceId.toString().equals(value)) { throw new NumberFormatException(); } }
            catch (NumberFormatException exception) { throw BusinessException.invalid("management_device_id须为正十进制字符串"); }
        }
        if ((channel == null) != (deviceId == null)) { throw BusinessException.invalid("设备映射与通道必须同时提供"); }
        final Long managementId = deviceId;
        return store.write(actor, "sources.register", body, OffsetDateTime.now().plusDays(7), jdbc -> {
            List<Map<String, Object>> existing = jdbc.queryForList("SELECT id FROM public.camera WHERE id=?::uuid FOR UPDATE", sourceId);
            if (!existing.isEmpty()) { throw BusinessException.conflict("来源已存在；本接口不修改现有来源"); }
            jdbc.update("INSERT INTO public.camera(id,camera_code,name,management_device_id,channel_code,source_kind,timezone) VALUES (?::uuid,?,?,?,?,?,?)",
                    sourceId, code, name, managementId, channel, kind, timezone);
            return values("source_id", sourceId, "camera_code", code, "display_name", name, "enabled", true);
        });
    }

    public Map<String, Object> sessions(BusinessActor actor, String source, String after, int size) {
        source = uuid(source, "source_id");
        actor.requireSource(source);
        if (size < 1 || size > 200) { throw BusinessException.invalid("page_size须为1至200"); }
        List<Object> parameters = new ArrayList<>(); parameters.add(source);
        String sql = "SELECT id::text AS stream_session_id,source_id::text,camera_stream_id::text,session_key,started_at,ended_at,time_origin_at,"
                + "time_basis,source_timezone,source_width,source_height,state,expires_at FROM public.stream_session WHERE source_id=?::uuid AND expires_at>now()";
        if (after != null) { uuid(after, "cursor"); sql += " AND id>?::uuid"; parameters.add(after); }
        sql += " ORDER BY id LIMIT ?"; parameters.add(size + 1);
        List<Map<String, Object>> items = store.jdbc().queryForList(sql, parameters.toArray());
        boolean more = items.size() > size;
        if (more) { items.remove(items.size() - 1); }
        for (Map<String,Object> item : items) {
            for (String key : java.util.Arrays.asList("started_at","ended_at","time_origin_at","expires_at")) {
                if (item.get(key) instanceof java.sql.Timestamp) {
                    item.put(key,iso(((java.sql.Timestamp)item.get(key)).toInstant().atOffset(java.time.ZoneOffset.UTC)));
                }
            }
        }
        return values("items", items, "next_cursor", more ? items.get(items.size() - 1).get("stream_session_id") : null, "has_more", more);
    }

    public Map<String, Object> open(BusinessActor actor, Map<String, Object> body) {
        fields(body, "request_id", "trace_id", "source_id", "stream_session_id", "session_key", "camera_stream_id", "started_at", "time_origin_at", "time_basis", "source_timezone", "source_width", "source_height");
        String source = uuid(body, "source_id"); actor.requireSource(source);
        String session = uuid(body, "stream_session_id");
        if (java.util.UUID.fromString(session).version()!=4) { throw BusinessException.invalid("新输入会话标识须为UUIDv4"); }
        String key = text(body, "session_key", 128);
        String stream = body.containsKey("camera_stream_id") ? uuid(body, "camera_stream_id") : null;
        OffsetDateTime start = time(body, "started_at");
        OffsetDateTime origin = time(body, "time_origin_at");
        String basis = text(body, "time_basis", 24);
        if (!"source_clock".equals(basis) && !"ingest_clock".equals(basis)) { throw BusinessException.invalid("time_basis无效"); }
        String timezone = text(body, "source_timezone", 64);
        if(!ZoneId.getAvailableZoneIds().contains(timezone)){throw BusinessException.invalid("source_timezone须为IANA时区");}
        int width = (int) integer(body, "source_width", 1, Integer.MAX_VALUE);
        int height = (int) integer(body, "source_height", 1, Integer.MAX_VALUE);
        OffsetDateTime expires = start.plusDays(7);
        return store.write(actor, "streams.open", body, expires, jdbc -> {
            List<Map<String, Object>> camera = jdbc.queryForList("SELECT enabled FROM public.camera WHERE id=?::uuid FOR UPDATE", source);
            if (camera.isEmpty()) { throw BusinessException.notFound("来源不存在"); }
            if (!Boolean.TRUE.equals(camera.get(0).get("enabled"))) { throw BusinessException.conflict("来源已禁用"); }
            String selectedStream=stream;
            if (selectedStream==null) {
                List<String> mappings=jdbc.queryForList("SELECT id::text FROM public.camera_stream WHERE camera_id=?::uuid AND is_active=true ORDER BY id",String.class,source);
                if (mappings.isEmpty()) { throw BusinessException.invalid("来源缺少已启用的流目录映射"); }
                if (mappings.size()>1) { throw BusinessException.invalid("来源存在多个流目录，必须明确camera_stream_id"); }
                selectedStream=mappings.get(0);
            } else if (jdbc.queryForList("SELECT id FROM public.camera_stream WHERE id=?::uuid AND camera_id=?::uuid AND is_active=true", selectedStream, source).isEmpty()) {
                throw BusinessException.invalid("流目录不存在、已停用或不属于此来源");
            }
            if (!jdbc.queryForList("SELECT id FROM public.stream_session WHERE id=?::uuid OR (source_id=?::uuid AND session_key=?)", session, source, key).isEmpty()) {
                throw BusinessException.conflict("会话标识或生产键已存在，请重试原请求");
            }
            jdbc.update("INSERT INTO public.stream_session(id,source_id,camera_stream_id,session_key,started_at,time_origin_at,time_basis,source_timezone,source_width,source_height,expires_at) "
                            + "VALUES (?::uuid,?::uuid,?::uuid,?,?,?,?,?,?,?,?)", session, source, selectedStream, key, start, origin, basis, timezone, width, height, expires);
            Map<String, Object> response = values("source_id", source, "stream_session_id", session, "state", "open", "started_at", iso(start));
            store.event(jdbc, "streams.opened", "stream_session", session, 1, response, expires);
            return response;
        });
    }

    public Map<String, Object> close(BusinessActor actor, Map<String, Object> body) {
        fields(body, "request_id", "trace_id", "stream_session_id", "expected_state", "state", "occurred_at", "ended_at", "reason_code");
        String session = uuid(body, "stream_session_id");
        String expected = text(body, "expected_state", 16);
        String state = text(body, "state", 16);
        if (!"open".equals(expected) || (!"closed".equals(state) && !"interrupted".equals(state))) { throw BusinessException.invalid("只允许open结束为closed或interrupted"); }
        OffsetDateTime ended = time(body, "ended_at");
        OffsetDateTime occurred = time(body, "occurred_at");
        String reason = body.containsKey("reason_code") ? text(body, "reason_code", 64) : null;
        if ("interrupted".equals(state) && reason == null) { throw BusinessException.invalid("中断必须提供reason_code"); }
        // Authorize before deduplication so a later permission change cannot reveal a cached response.
        List<Map<String, Object>> refs = store.jdbc().queryForList("SELECT source_id::text FROM public.stream_session WHERE id=?::uuid", session);
        if (refs.isEmpty()) { throw BusinessException.notFound("输入会话不存在"); }
        actor.requireSource((String) refs.get(0).get("source_id"));
        return store.write(actor, "streams.close", body, ended.plusDays(7), jdbc -> {
            Map<String, Object> record = jdbc.queryForMap("SELECT source_id::text,state,started_at,expires_at>now() AS valid FROM public.stream_session WHERE id=?::uuid FOR UPDATE", session);
            actor.requireSource((String) record.get("source_id"));
            if (!Boolean.TRUE.equals(record.get("valid"))) { throw BusinessException.expired("输入会话已到期"); }
            if (!expected.equals(record.get("state"))) { throw BusinessException.conflict("会话状态已改变"); }
            OffsetDateTime start = ((java.sql.Timestamp) record.get("started_at")).toInstant().atOffset(java.time.ZoneOffset.UTC);
            if (ended.isBefore(start) || occurred.isBefore(ended)) { throw BusinessException.invalid("结束时间须不早于开始，发生时间须不早于结束"); }
            jdbc.update("UPDATE public.stream_session SET state=?,ended_at=?,expires_at=? WHERE id=?::uuid", state, ended, ended.plusDays(7), session);
            Map<String, Object> response = values("stream_session_id", session, "state", state, "ended_at", iso(ended));
            Map<String, Object> event = values("source_id", record.get("source_id"), "stream_session_id", session, "state", state, "ended_at", iso(ended), "occurred_at", iso(occurred), "reason_code", reason);
            store.event(jdbc, "streams.ended", "stream_session", session, 2, event, ended.plusDays(7));
            return response;
        });
    }

    private static String placeholders(int size) { return String.join(",", Collections.nCopies(size, "?::uuid")); }
}
