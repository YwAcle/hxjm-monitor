package edu.cqupt.hxjm.algdeployment.business.service;

import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Base64;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessCanonical;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessStore;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;
import static edu.cqupt.hxjm.algdeployment.business.service.RecordingService.instant;
import static edu.cqupt.hxjm.algdeployment.business.service.RecordingService.one;

@Service
@ConditionalOnProperty(prefix = "hxjm.business", name = "enabled", havingValue = "true")
public class HistoryService {
    private final BusinessStore store;
    private final RecordingService recordings;
    public HistoryService(BusinessStore store, RecordingService recordings) { this.store = store; this.recordings = recordings; }

    public Map<String, Object> assets(BusinessActor actor, Map<String, Object> body) {
        fields(body, "source_ids", "asset_ids", "start_at", "end_at", "asset_types", "cursor", "page_size", "trace_id");
        List<Map<String, Object>> rows = new ArrayList<>();
        List<String> sources = new ArrayList<>();
        OffsetDateTime start = null, end = null;
        if (body.containsKey("asset_ids")) {
            if (body.containsKey("source_ids") || body.containsKey("start_at") || body.containsKey("end_at")) { throw BusinessException.invalid("资产标识与来源时间查询二选一"); }
            for (String id : identifiers(body.get("asset_ids"), 100)) { rows.add(recordings.asset(actor, id)); }
        } else {
            sources = identifiers(required(body, "source_ids"), 100);
            for (String source : sources) { actor.requireSource(source); }
            start = time(body, "start_at"); end = time(body, "end_at"); interval(start, end);
            for (String source : sources) {
                rows.addAll(store.jdbc().queryForList("SELECT *,start_ts+duration_ms*interval '1 millisecond' AS end_at FROM public.media_asset WHERE source_id=?::uuid AND state IS NOT NULL AND expires_at>now() AND start_ts<? AND start_ts+duration_ms*interval '1 millisecond'>? ORDER BY start_ts,id", source, end, start));
            }
        }
        if (body.containsKey("asset_types")) {
            Set<String> types = new LinkedHashSet<>();
            for (Object item : list(body.get("asset_types"))) {
                if (!(item instanceof String)) { throw BusinessException.invalid("asset_types须为字符串数组"); }
                types.add((String) item);
            }
            rows.removeIf(row -> !types.contains(row.get("asset_type")));
        }
        rows.sort(Comparator.comparing((Map<String, Object> row) -> instant(row.get("start_ts"))).thenComparing(row -> row.get("id").toString()));
        List<Map<String, Object>> items = new ArrayList<>();
        for (Map<String, Object> row : rows) { items.add(assetItem(row)); }
        Map<String, Object> response = page(items, body);
        response.put("coverage", start == null ? emptyCoverage() : recordingCoverage(rows, sources, start, end));
        return response;
    }

    public Map<String, Object> resolve(BusinessActor actor, Map<String, Object> body) {
        fields(body, "request_id", "trace_id", "purpose", "source_id", "stream_session_id", "asset_id", "start_at", "end_at");
        text(body, "request_id");
        String purpose = text(body, "purpose", 16);
        if ("file".equals(purpose)) {
            String id = uuid(body, "asset_id");
            Map<String, Object> asset = recordings.asset(actor, id);
            recordings.content(actor, id);
            return values("items", Collections.singletonList(accessItem(asset, null)), "coverage", emptyCoverage());
        }
        if (!"playback".equals(purpose)) { throw BusinessException.invalid("本阶段媒体解析接收playback或file用途"); }
        OffsetDateTime start = time(body, "start_at"), end = time(body, "end_at"); interval(start, end);
        List<Map<String, Object>> rows;
        String source;
        if (body.containsKey("asset_id")) {
            if (body.containsKey("source_id")) { throw BusinessException.invalid("回放按来源或资产二选一定位"); }
            Map<String, Object> asset = recordings.asset(actor, uuid(body, "asset_id"));
            if (!"recording".equals(asset.get("asset_type"))) { throw BusinessException.invalid("回放用途须引用录像资产"); }
            source = asset.get("source_id").toString();
            rows = new ArrayList<>();
            if (instant(asset.get("start_ts")).isBefore(end) && assetEnd(asset).isAfter(start)) { rows.add(asset); }
        } else {
            source = uuid(body, "source_id"); actor.requireSource(source);
            List<Object> args = new ArrayList<>(Arrays.asList(source, end, start));
            String sql = "SELECT * FROM public.media_asset WHERE source_id=?::uuid AND asset_type='recording' AND state IS NOT NULL AND expires_at>now() AND start_ts<? AND start_ts+duration_ms*interval '1 millisecond'>?";
            if (body.containsKey("stream_session_id")) { sql += " AND stream_session_id=?::uuid"; args.add(uuid(body, "stream_session_id")); }
            rows = store.jdbc().queryForList(sql + " ORDER BY start_ts,id", args.toArray());
        }
        List<Map<String, Object>> available = new ArrayList<>(), items = new ArrayList<>();
        for (Map<String, Object> asset : rows) {
            if (!"available".equals(asset.get("state"))) { continue; }
            try { recordings.content(actor, asset.get("id").toString()); available.add(asset); items.add(accessItem(asset, start)); }
            catch (BusinessException exception) { if (exception.getStatus() != 503) { throw exception; } }
        }
        return values("items", items, "coverage", recordingCoverage(available, Collections.singletonList(source), start, end));
    }

    public Map<String, Object> results(BusinessActor actor, Map<String, Object> body) {
        fields(body, "result_ids", "source_id", "stream_session_id", "start_at", "end_at", "result_type", "schema_version", "result_set_id", "cursor", "page_size", "trace_id");
        JdbcTemplate jdbc = store.jdbc();
        List<Map<String, Object>> items = new ArrayList<>();
        String source = null, session = null, explicitSet = null, queryType = null;
        String schemaVersion = body.get("schema_version") == null ? null : text(body, "schema_version", 32);
        OffsetDateTime start = null, end = null;
        if (body.containsKey("result_ids")) {
            if (body.containsKey("source_id") || body.containsKey("start_at") || body.containsKey("end_at") || body.containsKey("result_set_id") || body.containsKey("stream_session_id")) { throw BusinessException.invalid("成果标识与来源时间查询二选一"); }
            for (String id : identifiers(body.get("result_ids"), 100)) {
                List<Map<String, Object>> frame = jdbc.queryForList(frameSelect() + " WHERE af.id=?::uuid", id);
                if (!frame.isEmpty()) { items.add(frameItem(actor, frame.get(0))); }
                else {
                    Map<String, Object> result = one(jdbc.queryForList(otherSelect() + " WHERE ar.id=?::uuid", id), "成果不存在");
                    items.add(otherItem(actor, result));
                }
            }
        } else {
            source = uuid(body, "source_id"); actor.requireSource(source);
            start = time(body, "start_at"); end = time(body, "end_at"); interval(start, end);
            String type = text(body, "result_type", 64); queryType = type;
            session = body.get("stream_session_id") == null ? null : uuid(body, "stream_session_id");
            explicitSet = body.get("result_set_id") == null ? null : uuid(body, "result_set_id");
            if (explicitSet != null) {
                Map<String, Object> selected = one(jdbc.queryForList("SELECT source_id,expires_at FROM public.result_set WHERE id=?::uuid", explicitSet), "成果集不存在");
                if (!source.equals(String.valueOf(selected.get("source_id")))) { throw BusinessException.forbidden(); }
                if (!instant(selected.get("expires_at")).isAfter(OffsetDateTime.now())) { throw BusinessException.expired("成果集已到期"); }
            }
            Map<String, Object> anchor = anchor(body);
            int limit = pageSize(body) + 1;
            List<Object> arguments = new ArrayList<>(Arrays.asList(source, start, end));
            String where = " WHERE rs.source_id=?::uuid AND f.occurred_at>=? AND f.occurred_at<? AND af.expires_at>now() AND f.expires_at>now() AND rs.expires_at>now()";
            if (session != null) { where += " AND f.stream_session_id=?::uuid"; arguments.add(session); }
            if (explicitSet != null) { where += " AND rs.id=?::uuid"; arguments.add(explicitSet); }
            else { where += " AND EXISTS (SELECT 1 FROM public.result_selection sel WHERE sel.result_set_id=rs.id AND sel.range_start<=f.occurred_at AND sel.range_end>f.occurred_at AND sel.expires_at>now())"; }
            if ("detection.frame".equals(type)) {
                if (schemaVersion != null) { where += " AND af.schema_version=?"; arguments.add(schemaVersion); }
                if (anchor != null) {
                    where += " AND (f.occurred_at,f.frame_seq,af.id)>(?,?,?::uuid)";
                    arguments.add(time(anchor, "time")); arguments.add(integer(anchor, "sequence", 0, Long.MAX_VALUE)); arguments.add(uuid(anchor, "id"));
                }
                arguments.add(limit);
                for (Map<String, Object> row : jdbc.queryForList(frameSelect() + where + " ORDER BY f.occurred_at,f.frame_seq,af.id LIMIT ?", arguments.toArray())) { items.add(frameItem(actor, row)); }
            } else {
                arguments = new ArrayList<>(Arrays.asList(source, type, end, start, start));
                where = " WHERE rs.source_id=?::uuid AND ar.result_type=? AND ar.start_at<? AND (ar.end_at>? OR (ar.end_at IS NULL AND ar.start_at>=?)) AND ar.expires_at>now() AND rs.expires_at>now()";
                if (schemaVersion != null) { where += " AND ar.schema_version=?"; arguments.add(schemaVersion); }
                if (session != null) { where += " AND rs.stream_session_id=?::uuid"; arguments.add(session); }
                if (explicitSet != null) { where += " AND rs.id=?::uuid"; arguments.add(explicitSet); }
                else { where += " AND EXISTS (SELECT 1 FROM public.result_selection sel WHERE sel.result_set_id=rs.id AND sel.range_start<=ar.start_at AND sel.range_end>ar.start_at AND sel.expires_at>now())"; }
                if (anchor != null) { where += " AND (ar.start_at,ar.id)>(?,?::uuid)"; arguments.add(time(anchor, "time")); arguments.add(uuid(anchor, "id")); }
                arguments.add(limit);
                for (Map<String, Object> row : jdbc.queryForList(otherSelect() + where + " ORDER BY ar.start_at,ar.id LIMIT ?", arguments.toArray())) { items.add(otherItem(actor, row)); }
            }
        }
        if (body.get("result_type") != null) { String wanted = text(body, "result_type", 64); items.removeIf(item -> !wanted.equals(item.get("result_type"))); }
        if (schemaVersion != null) { items.removeIf(item -> !schemaVersion.equals(item.get("schema_version"))); }
        items.sort(Comparator.comparing((Map<String, Object> row) -> instant(row.containsKey("occurred_at") ? row.get("occurred_at") : row.get("start_at"))).thenComparing(row -> ((Number) row.getOrDefault("frame_seq", 0L)).longValue()).thenComparing(row -> row.get("result_id").toString()));
        Map<String, Object> response = page(items, body);
        if (source == null) { response.put("coverage", emptyCoverage()); response.put("recordings", Collections.emptyList()); }
        else {
            response.put("coverage", resultCoverage(source, session, explicitSet, queryType, schemaVersion, start, end));
            String mediaSql = "SELECT * FROM public.media_asset WHERE source_id=?::uuid AND asset_type='recording' AND state IS NOT NULL AND expires_at>now() AND start_ts<? AND start_ts+duration_ms*interval '1 millisecond'>?";
            List<Object> mediaArgs = new ArrayList<>(Arrays.asList(source, end, start));
            if (session != null) { mediaSql += " AND stream_session_id=?::uuid"; mediaArgs.add(session); }
            List<Map<String, Object>> media = store.jdbc().queryForList(mediaSql + " ORDER BY start_ts,id", mediaArgs.toArray());
            List<Map<String, Object>> recordings = new ArrayList<>();
            for (Map<String, Object> row : media) { recordings.add(assetItem(row)); }
            response.put("recordings", recordings);
        }
        return response;
    }

    private String frameSelect() {
        return "SELECT af.id AS result_id,af.result_set_id,af.schema_version,af.expires_at AS result_expiry,rs.run_id,rs.source_id,rs.stream_session_id,rs.input_asset_id,rs.expires_at AS set_expiry,f.id AS frame_id,f.frame_seq,f.occurred_at,f.stream_pts_ms,f.time_quality,f.media_asset_id,f.media_pts_ms,f.width AS source_width,f.height AS source_height,f.expires_at AS frame_expiry FROM public.analysis_frame af JOIN public.result_set rs ON rs.id=af.result_set_id JOIN public.input_frame f ON f.id=af.input_frame_id";
    }
    private String otherSelect() {
        return "SELECT ar.*,ar.id AS result_id,ar.expires_at AS result_expiry,rs.run_id,rs.source_id,rs.stream_session_id,rs.input_asset_id,rs.expires_at AS set_expiry FROM public.algorithm_result ar JOIN public.result_set rs ON rs.id=ar.result_set_id";
    }
    private Map<String, Object> frameItem(BusinessActor actor, Map<String, Object> row) {
        authorizeResult(actor, row);
        if (!instant(row.get("frame_expiry")).isAfter(OffsetDateTime.now())) { throw BusinessException.expired("输入帧已到期"); }
        Map<String, Object> item = values("result_type", "detection.frame");
        for (String name : Arrays.asList("result_id", "result_set_id", "run_id", "source_id", "stream_session_id", "input_asset_id", "schema_version", "frame_id", "frame_seq", "occurred_at", "stream_pts_ms", "time_quality", "media_asset_id", "media_pts_ms", "source_width", "source_height")) { item.put(name, output(row.get(name))); }
        List<Map<String, Object>> targets = new ArrayList<>();
        for (Map<String, Object> target : store.jdbc().queryForList("SELECT * FROM public.detection_observation WHERE analysis_frame_id=?::uuid ORDER BY target_index", row.get("result_id").toString())) {
            targets.add(values("observation_id", target.get("id").toString(), "target_index", target.get("target_index"), "tracklet_id", output(target.get("tracklet_id")), "object_type", target.get("object_type"), "class_code", target.get("class_code"), "bbox", Arrays.asList(target.get("bbox_left"), target.get("bbox_top"), target.get("bbox_right"), target.get("bbox_bottom")), "confidence", target.get("confidence"), "is_prediction", "predicted".equals(target.get("observation_kind"))));
        }
        item.put("targets", targets);
        return item;
    }
    private Map<String, Object> otherItem(BusinessActor actor, Map<String, Object> row) {
        authorizeResult(actor, row);
        Map<String, Object> item = values();
        for (String name : Arrays.asList("result_id", "result_set_id", "run_id", "source_id", "stream_session_id", "input_asset_id", "result_type", "schema_version", "start_at", "end_at", "payload_asset_id")) { item.put(name, output(row.get(name))); }
        item.put("payload", parse(row.get("payload_json").toString()));
        return item;
    }
    private void authorizeResult(BusinessActor actor, Map<String, Object> row) {
        if (row.get("source_id") == null) { throw BusinessException.forbidden(); }
        actor.requireSource(row.get("source_id").toString());
        if (!instant(row.get("result_expiry")).isAfter(OffsetDateTime.now()) || !instant(row.get("set_expiry")).isAfter(OffsetDateTime.now())) { throw BusinessException.expired("成果已到期"); }
    }
    private Map<String, Object> resultCoverage(String source, String session, String set, String type, String schemaVersion, OffsetDateTime start, OffsetDateTime end) {
        List<Object> args = new ArrayList<>(Arrays.asList(source, end, start, type));
        String sql = set == null
                ? "SELECT pc.*,GREATEST(pc.start_at,sel.range_start) AS covered_start,LEAST(pc.end_at,sel.range_end) AS covered_end FROM public.processing_coverage pc JOIN public.result_selection sel ON sel.result_set_id=pc.result_set_id AND sel.range_start<pc.end_at AND sel.range_end>pc.start_at AND sel.expires_at>now()"
                : "SELECT pc.*,pc.start_at AS covered_start,pc.end_at AS covered_end FROM public.processing_coverage pc";
        sql += " WHERE pc.source_id=?::uuid AND pc.stage IN ('analysis','registration') AND pc.start_at<? AND pc.end_at>? AND pc.expires_at>now() AND pc.frame_manifest_json->>'result_type'=? AND pc.frame_manifest_json->>'schema_version' IS NOT NULL";
        if (schemaVersion != null) { sql += " AND pc.frame_manifest_json->>'schema_version'=?"; args.add(schemaVersion); }
        if (session != null) { sql += " AND pc.stream_session_id=?::uuid"; args.add(session); }
        if (set != null) { sql += " AND pc.result_set_id=?::uuid"; args.add(set); }
        List<Map<String, Object>> completed = new ArrayList<>(), gaps = new ArrayList<>();
        List<Map<String, Object>> rows = store.jdbc().queryForList(sql + " ORDER BY pc.start_at,pc.id", args.toArray());
        for (String stage : Arrays.asList("analysis", "registration")) {
            List<OffsetDateTime[]> complete = new ArrayList<>();
            for (Map<String, Object> row : rows) {
                if (!stage.equals(row.get("stage"))) { continue; }
                OffsetDateTime left = maximum(start, instant(row.get("covered_start"))), right = minimum(end, instant(row.get("covered_end")));
                if (!right.isAfter(left)) { continue; }
                if ("complete".equals(row.get("status")) && Boolean.TRUE.equals(row.get("closed"))) {
                    complete.add(new OffsetDateTime[]{left, right}); completed.add(range(source, stage, left, right, null));
                } else if ("gap".equals(row.get("status")) || "unavailable".equals(row.get("status"))) {
                    complete.add(new OffsetDateTime[]{left, right});
                    gaps.add(range(source, stage, left, right, row.get("reason_code") == null ? "PENDING_INPUT" : row.get("reason_code").toString()));
                }
            }
            for (OffsetDateTime[] missing : complement(complete, start, end)) { gaps.add(range(source, stage, missing[0], missing[1], "registration".equals(stage) ? "RESULTS_PENDING" : "ANALYSIS_PENDING")); }
        }
        return values("schema_version", "1", "completed", completed, "gaps", gaps);
    }
    private Map<String, Object> recordingCoverage(List<Map<String, Object>> rows, List<String> sources, OffsetDateTime start, OffsetDateTime end) {
        List<Map<String, Object>> complete = new ArrayList<>(), gaps = new ArrayList<>();
        for (String source : sources) {
            List<OffsetDateTime[]> ranges = new ArrayList<>();
            for (Map<String, Object> row : rows) {
                if (!source.equals(String.valueOf(row.get("source_id"))) || !"recording".equals(row.get("asset_type")) || !"available".equals(row.get("state"))) { continue; }
                OffsetDateTime left = maximum(start, instant(row.get("start_ts"))), right = minimum(end, assetEnd(row));
                if (!right.isAfter(left)) { continue; }
                ranges.add(new OffsetDateTime[]{left, right}); complete.add(range(source, "recording", left, right, null));
            }
            for (OffsetDateTime[] missing : complement(ranges, start, end)) { gaps.add(range(source, "recording", missing[0], missing[1], "RECORDING_UNAVAILABLE")); }
        }
        return values("schema_version", "1", "completed", complete, "gaps", gaps);
    }
    public static List<OffsetDateTime[]> complement(List<OffsetDateTime[]> ranges, OffsetDateTime start, OffsetDateTime end) {
        List<OffsetDateTime[]> gaps = new ArrayList<>();
        ranges.sort(Comparator.comparing(item -> item[0]));
        OffsetDateTime current = start;
        for (OffsetDateTime[] item : ranges) {
            OffsetDateTime left = maximum(start, item[0]), right = minimum(end, item[1]);
            if (!right.isAfter(left)) { continue; }
            if (left.isAfter(current)) { gaps.add(new OffsetDateTime[]{current, left}); }
            current = maximum(current, right);
        }
        if (current.isBefore(end)) { gaps.add(new OffsetDateTime[]{current, end}); }
        return gaps;
    }
    private Map<String, Object> assetItem(Map<String, Object> row) {
        return values("asset_id", row.get("id").toString(), "source_id", output(row.get("source_id")), "stream_session_id", output(row.get("stream_session_id")), "asset_type", row.get("asset_type"), "state", row.get("state"), "start_at", instant(row.get("start_ts")).toString(), "end_at", assetEnd(row).toString(), "expires_at", output(row.get("expires_at")));
    }
    private Map<String, Object> accessItem(Map<String, Object> row, OffsetDateTime requested) {
        Map<String, Object> item = assetItem(row);
        item.put("access_url", "/api/v1/business/assets/" + row.get("id") + "/content");
        item.put("protocol", "http");
        item.put("offset_ms", requested == null ? null : Math.max(0, java.time.Duration.between(instant(row.get("start_ts")), requested).toMillis()));
        return item;
    }
    private Map<String, Object> page(List<Map<String, Object>> items, Map<String, Object> body) {
        int size = pageSize(body);
        String signature = signature(body);
        int offset = 0;
        Map<String, Object> cursor = anchor(body);
        if (cursor != null) {
            OffsetDateTime time = time(cursor, "time");
            long sequence = integer(cursor, "sequence", 0, Long.MAX_VALUE);
            String id = uuid(cursor, "id");
            while (offset < items.size() && compareAnchor(items.get(offset), time, sequence, id) <= 0) { offset++; }
        }
        int last = offset + Math.min(items.size() - offset, size);
        boolean more = last < items.size();
        Map<String, Object> tail = more ? items.get(last - 1) : null;
        String next = more ? Base64.getUrlEncoder().withoutPadding().encodeToString(json(values("query", signature,
                "time", itemTime(tail).toString(), "sequence", tail.getOrDefault("frame_seq", 0L),
                "id", tail.get(tail.containsKey("result_id") ? "result_id" : "asset_id"))).getBytes(StandardCharsets.UTF_8)) : null;
        return values("items", new ArrayList<>(items.subList(offset, last)), "next_cursor", next, "has_more", more);
    }
    private static int pageSize(Map<String, Object> body) { return body.get("page_size") == null ? 50 : (int) integer(body, "page_size", 1, 200); }
    private static String signature(Map<String, Object> body) { Map<String, Object> filter = new java.util.LinkedHashMap<>(body); filter.remove("cursor"); filter.remove("trace_id"); return BusinessCanonical.digest(filter); }
    private static Map<String, Object> anchor(Map<String, Object> body) {
        if (body.get("cursor") == null) { return null; }
        try {
            Map<String, Object> cursor = parse(new String(Base64.getUrlDecoder().decode(text(body, "cursor", 1024)), StandardCharsets.UTF_8));
            if (!signature(body).equals(cursor.get("query"))) { throw new IllegalArgumentException(); }
            time(cursor, "time"); integer(cursor, "sequence", 0, Long.MAX_VALUE); uuid(cursor, "id");
            return cursor;
        } catch (IllegalArgumentException invalid) { throw BusinessException.invalid("分页游标与查询范围不匹配"); }
    }
    private static OffsetDateTime itemTime(Map<String, Object> row) { return instant(row.get(row.containsKey("occurred_at") ? "occurred_at" : "start_at")); }
    private static int compareAnchor(Map<String, Object> row, OffsetDateTime time, long sequence, String id) {
        int compare = itemTime(row).compareTo(time);
        if (compare == 0) { compare = Long.compare(((Number) row.getOrDefault("frame_seq", 0L)).longValue(), sequence); }
        if (compare == 0) { compare = row.get(row.containsKey("result_id") ? "result_id" : "asset_id").toString().compareTo(id); }
        return compare;
    }
    private static List<String> identifiers(Object value, int maximum) {
        List<Object> array = list(value); Set<String> result = new LinkedHashSet<>();
        if (array.isEmpty() || array.size() > maximum) { throw BusinessException.invalid("标识数组大小超出范围"); }
        for (Object id : array) { if (!result.add(uuid(id, "id"))) { throw BusinessException.invalid("标识不能重复"); } }
        return new ArrayList<>(result);
    }
    private static Map<String, Object> emptyCoverage() { return values("schema_version", "1", "completed", Collections.emptyList(), "gaps", Collections.emptyList()); }
    private static Map<String, Object> range(String source, String stage, OffsetDateTime start, OffsetDateTime end, String reason) { Map<String, Object> value = values("source_id", source, "stage", stage, "start_at", start.toString(), "end_at", end.toString()); if (reason != null) { value.put("reason_code", reason); } return value; }
    private static Object output(Object value) { if (value instanceof java.sql.Timestamp || value instanceof OffsetDateTime) { return instant(value).toString(); } return value instanceof java.util.UUID ? value.toString() : value; }
    private static OffsetDateTime assetEnd(Map<String, Object> row) { return instant(row.get("start_ts")).plus(java.time.Duration.ofMillis(((Number) row.get("duration_ms")).longValue())); }
    private static OffsetDateTime maximum(OffsetDateTime a, OffsetDateTime b) { return a.isAfter(b) ? a : b; }
    private static OffsetDateTime minimum(OffsetDateTime a, OffsetDateTime b) { return a.isBefore(b) ? a : b; }
    private static void interval(OffsetDateTime start, OffsetDateTime end) { if (!end.isAfter(start)) { throw BusinessException.invalid("查询时间范围须非空"); } }
}
