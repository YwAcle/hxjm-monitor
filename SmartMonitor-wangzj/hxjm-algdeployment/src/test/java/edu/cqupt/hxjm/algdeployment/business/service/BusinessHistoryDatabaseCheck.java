package edu.cqupt.hxjm.algdeployment.business.service;

import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import javax.servlet.http.HttpServletRequest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessAuthentication;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessSecurityProperties;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessStore;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

/** Opt-in integration checks for the disposable stage-one database only. */
public final class BusinessHistoryDatabaseCheck {
    @SuppressWarnings("unchecked")
    public static void main(String[] args) throws Exception {
        String url = System.getenv("HXJM_TEST_JDBC_URL");
        if (!"1".equals(System.getenv("HXJM_ISOLATED_TEST")) || url == null
                || !url.matches("jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/hxjm_stage1_[a-z0-9_]+")) {
            throw new IllegalArgumentException("Explicit loopback hxjm_stage1_* test database and opt-in are required");
        }
        Path project = Paths.get("/data/nfs_storage/hxjm").toRealPath();
        Path root = Files.createTempDirectory(project, ".test-business-history-db-");
        try {
            BusinessStore store = new BusinessStore(new DriverManagerDataSource(url, System.getenv("HXJM_TEST_DB_USER"), System.getenv("HXJM_TEST_DB_PASSWORD")));
            JdbcTemplate jdbc = store.jdbc();
            RecordingService recordings = new RecordingService(store, root.toString());
            HistoryService history = new HistoryService(store, recordings);
            OffsetDateTime start = OffsetDateTime.now(ZoneOffset.UTC).minusMinutes(10).withNano(0), expiry = start.plusDays(7).plusMinutes(3);
            String source = id(), stream = id(), session = id(), task = id(), run = id(), set = id(), suffix = id();
            String capability = "history_" + suffix.replace("-", "");
            BusinessActor actor = actor(source);
            jdbc.update("INSERT INTO public.camera(id,camera_code,name) VALUES (?::uuid,?,?)", source, suffix, "isolated history fixture");
            jdbc.update("INSERT INTO public.camera_stream(id,camera_id,stream_name,task_type) VALUES (?::uuid,?::uuid,?,'track')", stream, source, "live/history-" + suffix);
            jdbc.update("INSERT INTO public.stream_session(id,source_id,camera_stream_id,session_key,started_at,time_origin_at,time_basis,source_timezone,source_width,source_height,expires_at) VALUES (?::uuid,?::uuid,?::uuid,?,?,?,'ingest_clock','Asia/Shanghai',1920,1080,?)", session, source, stream, suffix, start, start, expiry);
            jdbc.update("INSERT INTO public.capability_definition(capability_code,display_name,object_types,input_kinds) VALUES (?,?,'{person}','{live_video}')", capability, "isolated history");
            jdbc.update("INSERT INTO public.business_task(task_id,task_kind,actor_key,capability_code,input_digest,expires_at) VALUES (?::uuid,'tracking',?,?,?,?)", task, actor.getActorKey(), capability, zeros(), expiry);
            jdbc.update("INSERT INTO public.task_attempt(run_id,task_id,generation,implementation_code,implementation_version,expires_at) VALUES (?::uuid,?::uuid,1,'fixture','1',?)", run, task, expiry);
            jdbc.update("INSERT INTO public.result_set(id,run_id,source_id,stream_session_id,capability_code,set_key,generation,expires_at) VALUES (?::uuid,?::uuid,?::uuid,?::uuid,?,?,1,?)", set, run, source, session, capability, suffix, expiry);
            jdbc.update("INSERT INTO public.result_selection(source_id,capability_code,range_start,range_end,result_set_id,generation,expires_at) VALUES (?::uuid,?,?,?,?::uuid,1,?)", source, capability, start, start.plusMinutes(3), set, expiry);
            List<String> frames = new ArrayList<>(), results = new ArrayList<>();
            for (int index = 0; index < 3; index++) {
                String frame = id(), result = id(); frames.add(frame); results.add(result);
                OffsetDateTime occurred = start.plusMinutes(index).plusSeconds(1);
                jdbc.update("INSERT INTO public.input_frame(id,stream_session_id,frame_seq,occurred_at,time_quality,width,height,expires_at) VALUES (?::uuid,?::uuid,?,?,'ingest_estimated',1920,1080,?)", frame, session, index + 1, occurred, occurred.plusDays(7));
                jdbc.update("INSERT INTO public.analysis_frame(id,result_set_id,input_frame_id,producer_result_key,target_count,payload_digest,expires_at) VALUES (?::uuid,?::uuid,?::uuid,?,?,?,?)", result, set, frame, "frame:" + frame, index == 1 ? 1 : 0, zeros(), occurred.plusDays(7));
                if (index == 1) { jdbc.update("INSERT INTO public.detection_observation(analysis_frame_id,target_index,object_type,class_code,observation_kind,bbox_left,bbox_top,bbox_right,bbox_bottom,expires_at) VALUES (?::uuid,0,'person','person','predicted',0.1,0.1,0.5,0.8,?)", result, occurred.plusDays(7)); }
            }
            jdbc.update("INSERT INTO public.processing_coverage(source_id,stream_session_id,result_set_id,run_id,stage,coverage_key,closed,start_at,end_at,status,analyzed_frame_count,saved_frame_count,frame_manifest_json,expires_at) VALUES (?::uuid,?::uuid,?::uuid,?::uuid,'registration',?,true,?,?,'complete',3,3,?::jsonb,?)", source, session, set, run, suffix, start, start.plusMinutes(3), json(values("result_type", "detection.frame", "schema_version", "1")), expiry);
            jdbc.update("INSERT INTO public.processing_coverage(source_id,stream_session_id,result_set_id,run_id,stage,coverage_key,closed,start_at,end_at,status,frame_manifest_json,expires_at) VALUES (?::uuid,?::uuid,?::uuid,?::uuid,'analysis',?,true,?,?,'complete',?::jsonb,?)", source, session, set, run, "other-type:" + suffix, start, start.plusMinutes(3), json(values("result_type", "pose.frame", "schema_version", "1")), expiry);
            List<Map<String, Object>> registered = new ArrayList<>();
            byte[] bytes = "isolated-recording-data".getBytes(StandardCharsets.UTF_8);
            for (int index = 0; index < 3; index++) {
                String asset = id(), key = "recordings/" + asset + ".mp4";
                Map<String, Object> prepare = values("request_id", "prepare-" + asset, "asset_id", asset, "producer_key", "fixture:" + asset,
                        "asset_type", "recording", "source_id", source, "stream_session_id", session, "storage_key", key,
                        "state", "preparing", "start_at", start.plusMinutes(index).toString(), "end_at", start.plusMinutes(index + 1).toString(),
                        "expires_at", start.plusMinutes(index + 1).plusDays(7).toString(), "write_attempt_id", id(), "content_type", "video/mp4");
                recordings.register(actor, prepare);
                check(Boolean.TRUE.equals(recordings.register(actor, prepare).get("duplicate")), "preparing replay");
                Map<String, Object> ready = new LinkedHashMap<>(prepare); ready.put("request_id", "ready-" + asset); ready.put("state", "available"); ready.put("expected_revision", 1);
                ready.put("byte_size", bytes.length); ready.put("checksum_sha256", hash(bytes));
                ready.put("frame_locations", Collections.singletonList(values("frame_id", frames.get(index), "media_pts_ms", 1000)));
                Path file = root.resolve(key); Files.createDirectories(file.getParent()); Files.write(file, bytes);
                if (index < 2) { recordings.register(actor, ready); check(Boolean.TRUE.equals(recordings.register(actor, ready).get("duplicate")), "ready replay"); }
                registered.add(ready);
            }
            Map<String, Object> mediaRequest = values("request_id", "resolve-" + suffix, "purpose", "playback", "source_id", source, "start_at", start.toString(), "end_at", start.plusMinutes(3).toString());
            Map<String, Object> media = history.resolve(actor, mediaRequest);
            check(((List<?>) media.get("items")).size() == 2, "preparing third segment cannot play");
            check(!((List<?>) map(media.get("coverage")).get("gaps")).isEmpty(), "preparing segment is a recording gap");
            recordings.register(actor, registered.get(2));
            media = history.resolve(actor, mediaRequest);
            check(((List<?>) media.get("items")).size() == 3 && ((List<?>) map(media.get("coverage")).get("gaps")).isEmpty(), "all intersecting segments returned");
            Map<String, Object> query = values("source_id", source, "start_at", start.toString(), "end_at", start.plusMinutes(3).toString(), "result_type", "detection.frame", "page_size", 2);
            Map<String, Object> first = history.results(actor, query);
            List<Map<String, Object>> firstItems = (List<Map<String, Object>>) first.get("items");
            check(firstItems.size() == 2 && Boolean.TRUE.equals(first.get("has_more")), "frame SQL page");
            check(((List<?>) firstItems.get(0).get("targets")).isEmpty(), "zero target frame");
            check(Boolean.TRUE.equals(map(((List<?>) firstItems.get(1).get("targets")).get(0)).get("is_prediction")), "predicted observation");
            check(((List<?>) first.get("recordings")).size() == 3, "frame query includes every intersecting recording");
            List<?> completed = (List<?>) map(first.get("coverage")).get("completed");
            check(completed.size() == 1 && "registration".equals(map(completed.get(0)).get("stage")), "another result type cannot fill analysis coverage");
            Map<String, Object> otherVersion = new LinkedHashMap<>(query); otherVersion.put("schema_version", "2");
            Map<String, Object> versionResults = history.results(actor, otherVersion);
            check(((List<?>) versionResults.get("items")).isEmpty() && ((List<?>) map(versionResults.get("coverage")).get("completed")).isEmpty(), "another schema version cannot fill requested results or coverage");
            Map<String, Object> next = new LinkedHashMap<>(query); next.put("cursor", first.get("next_cursor"));
            check(((List<?>) history.results(actor, next).get("items")).size() == 1, "second frame page");
            Map<String, Object> changed = new LinkedHashMap<>(next); changed.put("end_at", start.plusMinutes(4).toString()); fails(400, () -> history.results(actor, changed));
            String otherSession = id(), otherAsset = id();
            jdbc.update("INSERT INTO public.stream_session(id,source_id,camera_stream_id,session_key,started_at,time_origin_at,time_basis,source_timezone,source_width,source_height,expires_at) VALUES (?::uuid,?::uuid,?::uuid,?,?,?,'ingest_clock','Asia/Shanghai',1920,1080,?)", otherSession, source, stream, "other:" + suffix, start, start, expiry);
            Map<String, Object> otherRecording = new LinkedHashMap<>(registered.get(0));
            otherRecording.put("request_id", "other-session-" + suffix); otherRecording.put("asset_id", otherAsset); otherRecording.put("producer_key", "fixture:" + otherAsset);
            otherRecording.put("stream_session_id", otherSession); otherRecording.put("storage_key", "recordings/" + otherAsset + ".mp4"); otherRecording.put("state", "preparing");
            for (String field : Arrays.asList("expected_revision", "byte_size", "checksum_sha256", "frame_locations")) { otherRecording.remove(field); }
            recordings.register(actor, otherRecording);
            check(((List<?>) history.results(actor, query).get("recordings")).size() == 4, "source query includes intersecting sessions");
            Map<String, Object> sessionQuery = new LinkedHashMap<>(query); sessionQuery.put("stream_session_id", session);
            check(((List<?>) history.results(actor, sessionQuery).get("recordings")).size() == 3, "session query keeps recordings in that input session");
            Map<String, Object> conflict = new LinkedHashMap<>(registered.get(0)); conflict.put("request_id", "bad-location-" + suffix); conflict.put("expected_revision", 2);
            conflict.put("frame_locations", Collections.singletonList(values("frame_id", frames.get(1), "media_pts_ms", 1000)));
            fails(409, () -> recordings.register(actor, conflict));
            check(jdbc.queryForObject("SELECT revision FROM public.media_asset WHERE id=?::uuid", Long.class, registered.get(0).get("asset_id")) == 2L, "location conflict rolls back asset revision");
            jdbc.update("UPDATE public.analysis_frame SET expires_at=now()-interval '1 second' WHERE id=?::uuid", results.get(0));
            fails(410, () -> history.results(actor, values("result_ids", Collections.singletonList(results.get(0)))));
            jdbc.update("UPDATE public.media_asset SET expires_at=now()-interval '1 second' WHERE id=?::uuid", registered.get(0).get("asset_id"));
            fails(410, () -> recordings.content(actor, registered.get(0).get("asset_id").toString()));
            checkAutomaticAlignment(store, recordings, root);
            System.out.println("BusinessHistoryDatabaseCheck passed: recording transitions, replay, frame positioning, bidirectional media alignment, ranges, paging, expiry, rollback");
        } finally {
            try (java.util.stream.Stream<Path> paths = Files.walk(root)) { paths.sorted(Comparator.reverseOrder()).forEach(path -> { try { Files.delete(path); } catch (Exception error) { throw new RuntimeException(error); } }); }
        }
    }

    private static void checkAutomaticAlignment(BusinessStore store, RecordingService recordings, Path root) throws Exception {
        JdbcTemplate jdbc = store.jdbc();
        OffsetDateTime started = OffsetDateTime.now(ZoneOffset.UTC).minusMinutes(5).withNano(0);
        OffsetDateTime origin = started.minusSeconds(5), end = started.plusSeconds(1), expiry = end.plusDays(7);
        String source = id(), stream = id(), session = id(), asset = id(), firstFrame = id(), boundaryFrame = id();
        BusinessActor actor = actor(source);
        jdbc.update("INSERT INTO public.camera(id,camera_code,name) VALUES (?::uuid,?,?)", source, source, "isolated automatic alignment fixture");
        jdbc.update("INSERT INTO public.camera_stream(id,camera_id,stream_name,task_type) VALUES (?::uuid,?::uuid,?,'track')", stream, source, "live/alignment-" + source);
        jdbc.update("INSERT INTO public.stream_session(id,source_id,camera_stream_id,session_key,started_at,time_origin_at,time_basis,source_timezone,source_width,source_height,expires_at) VALUES (?::uuid,?::uuid,?::uuid,?,?,?,'ingest_clock','UTC',1920,1080,?)", session, source, stream, "alignment:" + session, started, origin, expiry);
        jdbc.update("INSERT INTO public.input_frame(id,stream_session_id,frame_seq,occurred_at,stream_pts_ms,time_quality,width,height,expires_at) VALUES (?::uuid,?::uuid,1,?,5040,'ingest_estimated',1920,1080,?)", firstFrame, session, origin.plusNanos(5040L * 1000000), expiry);
        jdbc.update("INSERT INTO public.input_frame(id,stream_session_id,frame_seq,occurred_at,stream_pts_ms,time_quality,width,height,expires_at) VALUES (?::uuid,?::uuid,2,?,6000,'ingest_estimated',1920,1080,?)", boundaryFrame, session, end, expiry);
        byte[] bytes = "isolated-nonzero-pts-recording".getBytes(StandardCharsets.UTF_8);
        String key = "recordings/" + source + "/" + session + "/" + asset + ".mp4";
        Path file = root.resolve(key); Files.createDirectories(file.getParent()); Files.write(file, bytes);
        Map<String, Object> ready = values("request_id", "alignment:" + asset, "asset_id", asset, "producer_key", "fixture:" + asset,
                "asset_type", "recording", "source_id", source, "stream_session_id", session, "storage_key", key,
                "state", "available", "start_at", started.toString(), "end_at", end.toString(), "expires_at", expiry.toString(),
                "content_type", "video/mp4", "byte_size", bytes.length, "checksum_sha256", hash(bytes),
                "recording_alignment", values("schema_version", "1", "stream_start_pts_ms", 5000, "stream_end_pts_ms", 6000, "media_start_pts_ms", 0));
        recordings.register(actor, ready);
        checkFrameLocation(jdbc, firstFrame, asset, 40);
        check(jdbc.queryForObject("SELECT media_asset_id IS NULL FROM public.input_frame WHERE id=?::uuid", Boolean.class, boundaryFrame), "exclusive recording end is not assigned to the previous segment");
        check(Boolean.TRUE.equals(recordings.register(actor, ready).get("duplicate")), "automatic alignment registration replay");
        checkFrameLocation(jdbc, firstFrame, asset, 40);

        String lateFrame = id();
        new TransactionTemplate(new DataSourceTransactionManager(jdbc.getDataSource())).execute(status -> {
            jdbc.queryForList("SELECT id FROM public.stream_session WHERE id=?::uuid FOR UPDATE", session);
            jdbc.update("INSERT INTO public.input_frame(id,stream_session_id,frame_seq,occurred_at,stream_pts_ms,time_quality,width,height,expires_at) VALUES (?::uuid,?::uuid,3,?,5120,'ingest_estimated',1920,1080,?)", lateFrame, session, origin.plusNanos(5120L * 1000000), expiry);
            Map<String, Object> frame = jdbc.queryForMap("SELECT * FROM public.input_frame WHERE id=?::uuid FOR UPDATE", lateFrame);
            RecordingService.alignFrame(jdbc, frame);
            return null;
        });
        checkFrameLocation(jdbc, lateFrame, asset, 120);
        check(jdbc.queryForObject("SELECT started_at<>time_origin_at FROM public.stream_session WHERE id=?::uuid", Boolean.class, session), "media alignment uses a distinct PTS zero origin");
    }

    private static void checkFrameLocation(JdbcTemplate jdbc, String frame, String asset, long offset) {
        Map<String, Object> location = jdbc.queryForMap("SELECT media_asset_id,media_pts_ms FROM public.input_frame WHERE id=?::uuid", frame);
        check(asset.equals(String.valueOf(location.get("media_asset_id")))
                && location.get("media_pts_ms") instanceof Number
                && ((Number) location.get("media_pts_ms")).longValue() == offset, "frame persisted with the correct recording and media offset");
    }

    private static String id() { return UUID.randomUUID().toString(); }
    private static String zeros() { return String.join("", Collections.nCopies(64, "0")); }
    private static String hash(byte[] bytes) throws Exception { StringBuilder result = new StringBuilder(); for (byte value : MessageDigest.getInstance("SHA-256").digest(bytes)) { result.append(String.format("%02x", value & 255)); } return result.toString(); }
    private static void check(boolean value, String message) { if (!value) { throw new AssertionError(message); } }
    private static void fails(int status, Runnable operation) { try { operation.run(); throw new AssertionError("Expected " + status); } catch (BusinessException error) { check(error.getStatus() == status, "Expected " + status + ", got " + error.getStatus()); } }
    private static BusinessActor actor(String source) {
        BusinessSecurityProperties properties = new BusinessSecurityProperties(); BusinessSecurityProperties.ServiceIdentity grant = new BusinessSecurityProperties.ServiceIdentity();
        grant.setToken("isolated-fixture"); grant.setSourceIds(Collections.singleton(source)); grant.setOperations(new LinkedHashSet<>(Arrays.asList("assets.register", "assets.query", "media.resolve", "results.query"))); properties.getServices().put("history", grant);
        BusinessAuthentication authentication = new BusinessAuthentication(properties); authentication.afterPropertiesSet();
        HttpServletRequest request = (HttpServletRequest) Proxy.newProxyInstance(BusinessHistoryDatabaseCheck.class.getClassLoader(), new Class<?>[]{HttpServletRequest.class}, (proxy, method, args) -> { if ("getHeader".equals(method.getName())) { return BusinessAuthentication.SERVICE_ID_HEADER.equals(args[0]) ? "history" : "isolated-fixture"; } throw new AssertionError(method.getName()); });
        return authentication.requireService(request, "assets.register");
    }
}
