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
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import javax.servlet.http.HttpServletRequest;
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.api.RecordingController;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessAuthentication;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessSecurityProperties;
import edu.cqupt.hxjm.algdeployment.business.security.PlaybackTickets;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessStore;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.values;

/** Pure service checks: fixture files stay under hxjm-yh; no Spring server or database. */
public final class BusinessHistoryCheck {
    private static final String SOURCE = "10000000-0000-4000-8000-000000000001";
    private static final String SESSION = "20000000-0000-4000-8000-000000000001";
    private static final String STREAM = "30000000-0000-4000-8000-000000000001";
    private static final OffsetDateTime START = OffsetDateTime.now(ZoneOffset.UTC).minusMinutes(10).withNano(0);

    public static void main(String[] args) throws Exception {
        Path project = Paths.get(System.getProperty("hxjm.test.root", "/data/nfs_storage/hxjm")).toRealPath();
        if (!project.equals(Paths.get("/data/nfs_storage/hxjm").toRealPath())) { throw new AssertionError("Tests require the isolated yh fixture root"); }
        Path fixture = Files.createTempDirectory(project, ".test-business-history-");
        try {
            registeringAndReading(fixture);
            historyAndPagination(fixture);
            resultShapesAndScope(fixture);
            System.out.println("BusinessHistoryCheck passed");
        } finally {
            try (java.util.stream.Stream<Path> paths = Files.walk(fixture)) {
                paths.sorted(Comparator.reverseOrder()).forEach(path -> { try { Files.delete(path); } catch (Exception error) { throw new RuntimeException(error); } });
            }
        }
    }

    private static void registeringAndReading(Path fixture) throws Exception {
        FakeJdbc jdbc = new FakeJdbc();
        FakeStore store = new FakeStore(jdbc);
        RecordingService recordings = new RecordingService(store, fixture.toString());
        BusinessActor actor = actor();
        jdbc.session = values("source_id", SOURCE, "camera_stream_id", STREAM, "stream_name", "live/camera_1",
                "started_at", START, "ended_at", null, "expires_at", START.plusDays(7));
        String id = UUID.randomUUID().toString();
        Map<String, Object> request = values("request_id", "prepare", "asset_id", id, "producer_key", "recorder:segment-1",
                "asset_type", "recording", "source_id", SOURCE, "stream_session_id", SESSION,
                "storage_key", "recordings/segment.mp4", "state", "preparing", "start_at", START.toString(),
                "end_at", START.plusMinutes(1).toString(), "expires_at", START.plusMinutes(1).plusDays(7).toString(),
                "write_attempt_id", UUID.randomUUID().toString(), "content_type", "video/mp4");
        Map<String, Object> response = recordings.register(actor, request);
        check(Long.valueOf(1).equals(response.get("revision")), "preparing revision");
        check("live/camera_1".equals(jdbc.lastStream), "varchar stream preserves legacy path");
        fails(503, () -> recordings.content(actor, id));
        Path file = fixture.resolve("recordings/segment.mp4");
        Files.createDirectories(file.getParent());
        byte[] bytes = "isolated-recording".getBytes(StandardCharsets.UTF_8);
        Files.write(file, bytes);
        Map<String, Object> available = new LinkedHashMap<>(request);
        available.put("request_id", "ready"); available.put("state", "available");
        available.put("expected_revision", 1); available.put("byte_size", bytes.length); available.put("checksum_sha256", hash(bytes));
        Map<String, Object> frame = values("stream_session_id", SESSION, "occurred_at", START.plusSeconds(10),
                "expires_at", START.plusDays(7), "media_asset_id", null, "media_pts_ms", null);
        jdbc.frame = frame;
        String frameId = UUID.randomUUID().toString();
        available.put("frame_locations", Collections.singletonList(values("frame_id", frameId, "media_pts_ms", 10000)));
        response = recordings.register(actor, available);
        check(Long.valueOf(2).equals(response.get("revision")), "ready revision increments");
        check(id.equals(frame.get("media_asset_id")) && Long.valueOf(10000).equals(frame.get("media_pts_ms")), "sealed frame location");
        check(file.toRealPath().equals(recordings.content(actor, id)), "controlled file path");
        RecordingController controller = new RecordingController(new BusinessAuthentication(new BusinessSecurityProperties()) {
            @Override public BusinessActor authenticate(HttpServletRequest request, String operation) { actor.requireOperation(operation); return actor; }
        }, recordings, new PlaybackTickets());
        HttpServletRequest contentRequest = (HttpServletRequest) Proxy.newProxyInstance(HttpServletRequest.class.getClassLoader(),
                new Class<?>[]{HttpServletRequest.class}, (proxy, method, arguments) -> null);
        ResponseEntity<?> videoResponse = controller.content(id, contentRequest);
        check(videoResponse.getHeaders().getFirst(HttpHeaders.CONTENT_DISPOSITION) == null, "recording keeps streaming response");
        check("nosniff".equals(videoResponse.getHeaders().getFirst("X-Content-Type-Options")), "recording disables content sniffing");
        jdbc.assets.get(id).put("asset_type", "algorithm_output");
        ResponseEntity<?> fileResponse = controller.content(id, contentRequest);
        check(("attachment; filename=\"" + id + ".bin\"").equals(fileResponse.getHeaders().getFirst(HttpHeaders.CONTENT_DISPOSITION)), "algorithm output downloads with safe asset filename");
        check("nosniff".equals(fileResponse.getHeaders().getFirst("X-Content-Type-Options")), "algorithm output disables content sniffing");
        jdbc.assets.get(id).put("asset_type", "recording");
        jdbc.assets.get(id).put("content_type", "text/html");
        check(controller.content(id, contentRequest).getHeaders().getFirst(HttpHeaders.CONTENT_DISPOSITION).startsWith("attachment;"), "non-video recording MIME cannot execute inline");
        jdbc.assets.get(id).put("content_type", "video/mp4");
        check(jdbc.recordingCoverageWritten, "available recording coverage is persisted");
        FakeJdbc algorithmJdbc = new FakeJdbc(); algorithmJdbc.session = jdbc.session;
        Map<String, Object> algorithmRequest = new LinkedHashMap<>(available);
        algorithmRequest.put("asset_type", "algorithm_output"); algorithmRequest.remove("expected_revision"); algorithmRequest.remove("frame_locations");
        new RecordingService(new FakeStore(algorithmJdbc), fixture.toString()).register(actor, algorithmRequest);
        check(!algorithmJdbc.recordingCoverageWritten, "algorithm output registration does not publish recording coverage");
        Map<String, Object> unchanged = new LinkedHashMap<>(available);
        unchanged.put("request_id", "same-file"); unchanged.remove("frame_locations");
        check(Boolean.TRUE.equals(recordings.register(actor, unchanged).get("duplicate")), "same artifact different request reuses result");
        Map<String, Object> changed = new LinkedHashMap<>(unchanged); changed.put("checksum_sha256", String.join("", Collections.nCopies(64, "a")));
        fails(409, () -> recordings.register(actor, changed));
        jdbc.assets.get(id).put("valid", false);
        fails(410, () -> recordings.content(actor, id));
        jdbc.assets.get(id).put("valid", true);
        jdbc.assets.get(id).put("source_id", UUID.randomUUID().toString());
        fails(403, () -> recordings.content(actor, id));
        jdbc.assets.get(id).put("source_id", SOURCE);
        for (String key : Arrays.asList("../outside", "/absolute/file", "recordings/../file", "recordings\\file", "https://host/file")) { fails(400, () -> RecordingService.storageKey(key)); }
        Path outside = Files.createDirectories(fixture.resolve("outside-root"));
        Path root = Files.createDirectories(fixture.resolve("separate-root"));
        Files.write(outside.resolve("private"), bytes);
        Files.createSymbolicLink(root.resolve("escape"), outside);
        jdbc.assets.get(id).put("storage_key", "escape/private");
        RecordingService separate = new RecordingService(store, root.toString());
        fails(403, () -> separate.content(actor, id));
    }

    @SuppressWarnings("unchecked")
    private static void historyAndPagination(Path fixture) {
        FakeJdbc jdbc = new FakeJdbc(); FakeStore store = new FakeStore(jdbc);
        HistoryService history = new HistoryService(store, new RecordingService(store, fixture.toString()));
        for (int index = 0; index < 3; index++) { Map<String, Object> row = asset(index); jdbc.assets.put(row.get("id").toString(), row); }
        Map<String, Object> query = values("source_ids", Collections.singletonList(SOURCE), "start_at", START.toString(), "end_at", START.plusMinutes(3).toString(), "page_size", 2);
        Map<String, Object> first = history.assets(actor(), query);
        check(((List<?>) first.get("items")).size() == 2 && Boolean.TRUE.equals(first.get("has_more")), "first asset page");
        Map<String, Object> coverage = (Map<String, Object>) first.get("coverage");
        check(((List<?>) coverage.get("completed")).size() == 3 && ((List<?>) coverage.get("gaps")).isEmpty(), "all three adjacent recording segments cover request");
        Map<String, Object> next = new LinkedHashMap<>(query); next.put("cursor", first.get("next_cursor"));
        Map<String, Object> earlier = asset(-1); jdbc.assets.put(earlier.get("id").toString(), earlier);
        Map<String, Object> second = history.assets(actor(), next);
        check(((List<?>) second.get("items")).size() == 1 && Boolean.FALSE.equals(second.get("has_more")), "keyset avoids duplicate after earlier insertion");
        Map<String, Object> bad = new LinkedHashMap<>(next); bad.put("end_at", START.plusMinutes(4).toString());
        fails(400, () -> history.assets(actor(), bad));
        jdbc.assets.values().removeIf(row -> START.plusMinutes(1).equals(row.get("start_ts")));
        Map<String, Object> algorithmAsset = asset(1); algorithmAsset.put("asset_type", "algorithm_output"); jdbc.assets.put(algorithmAsset.get("id").toString(), algorithmAsset);
        Map<String, Object> recordingOnly = (Map<String, Object>) history.assets(actor(), query).get("coverage");
        check(((List<?>) recordingOnly.get("completed")).size() == 2 && ((List<?>) recordingOnly.get("gaps")).size() == 1, "algorithm file cannot fill a recording gap");
        fails(400, () -> history.resolve(actor(), values("request_id", "not-a-recording", "purpose", "playback", "asset_id", algorithmAsset.get("id"), "start_at", START.toString(), "end_at", START.plusMinutes(3).toString())));
        List<OffsetDateTime[]> ranges = new ArrayList<>();
        ranges.add(new OffsetDateTime[]{START, START.plusSeconds(20)});
        ranges.add(new OffsetDateTime[]{START.plusSeconds(10), START.plusSeconds(30)});
        ranges.add(new OffsetDateTime[]{START.plusSeconds(40), START.plusMinutes(1)});
        List<OffsetDateTime[]> gaps = HistoryService.complement(ranges, START, START.plusMinutes(1));
        check(gaps.size() == 1 && gaps.get(0)[0].equals(START.plusSeconds(30)) && gaps.get(0)[1].equals(START.plusSeconds(40)), "overlap and interior gap handled");
    }

    @SuppressWarnings("unchecked")
    private static void resultShapesAndScope(Path fixture) {
        FakeJdbc jdbc = new FakeJdbc(); FakeStore store = new FakeStore(jdbc);
        HistoryService history = new HistoryService(store, new RecordingService(store, fixture.toString()));
        String id = UUID.randomUUID().toString();
        jdbc.result = values("result_id", id, "result_set_id", UUID.randomUUID().toString(), "run_id", UUID.randomUUID().toString(),
                "schema_version", "1", "source_id", SOURCE, "stream_session_id", SESSION, "input_asset_id", null,
                "result_expiry", START.plusDays(7), "set_expiry", START.plusDays(7), "frame_expiry", START.plusDays(7),
                "frame_id", UUID.randomUUID().toString(), "frame_seq", 1L, "occurred_at", START.plusSeconds(1),
                "stream_pts_ms", null, "time_quality", "ingest_estimated", "media_asset_id", null, "media_pts_ms", null,
                "source_width", 1920, "source_height", 1080);
        Map<String, Object> query = values("result_ids", Collections.singletonList(id));
        Map<String, Object> response = history.results(actor(), query);
        Map<String, Object> item = ((List<Map<String, Object>>) response.get("items")).get(0);
        check(((List<?>) item.get("targets")).isEmpty(), "zero-target analyzed frame is returned");
        check(item.get("media_asset_id") == null && item.get("media_pts_ms") == null, "unsealed location remains unknown");
        jdbc.observations = Collections.singletonList(values("id", UUID.randomUUID().toString(), "target_index", 0,
                "tracklet_id", null, "object_type", "person", "class_code", "person", "confidence", null,
                "observation_kind", "predicted", "bbox_left", 0.1, "bbox_top", 0.2, "bbox_right", 0.6, "bbox_bottom", 0.8));
        response = history.results(actor(), query);
        item = ((List<Map<String, Object>>) response.get("items")).get(0);
        Map<String, Object> target = ((List<Map<String, Object>>) item.get("targets")).get(0);
        check(Boolean.TRUE.equals(target.get("is_prediction")) && target.get("confidence") == null, "prediction does not invent observed confidence");
        jdbc.result.put("source_id", UUID.randomUUID().toString());
        fails(403, () -> history.results(actor(), query));
        jdbc.result.put("source_id", SOURCE); jdbc.result.put("result_expiry", START.minusDays(1));
        fails(410, () -> history.results(actor(), query));
    }

    private static Map<String, Object> asset(int number) {
        return values("id", UUID.randomUUID().toString(), "source_id", SOURCE, "stream_session_id", SESSION,
                "asset_type", "recording", "state", "available", "start_ts", START.plusMinutes(number),
                "duration_ms", 60000L, "expires_at", START.plusDays(7), "valid", true);
    }
    private static String hash(byte[] value) throws Exception { StringBuilder hash = new StringBuilder(); for (byte item : MessageDigest.getInstance("SHA-256").digest(value)) { hash.append(String.format("%02x", item & 255)); } return hash.toString(); }
    private static void check(boolean value, String message) { if (!value) { throw new AssertionError(message); } }
    private static void fails(int status, Runnable operation) { try { operation.run(); throw new AssertionError("Expected " + status); } catch (BusinessException error) { check(error.getStatus() == status, "Expected " + status + " got " + error.getStatus()); } }

    private static BusinessActor actor() {
        BusinessSecurityProperties properties = new BusinessSecurityProperties();
        BusinessSecurityProperties.ServiceIdentity grant = new BusinessSecurityProperties.ServiceIdentity();
        grant.setToken("isolated-test-token"); grant.setOperations(new LinkedHashSet<>(Arrays.asList("assets.register", "assets.query", "media.resolve", "results.query")));
        grant.setSourceIds(new LinkedHashSet<>(Collections.singleton(SOURCE))); properties.getServices().put("test", grant);
        BusinessAuthentication auth = new BusinessAuthentication(properties); auth.afterPropertiesSet();
        HttpServletRequest request = (HttpServletRequest) Proxy.newProxyInstance(BusinessHistoryCheck.class.getClassLoader(), new Class<?>[]{HttpServletRequest.class}, (proxy, method, args) -> {
            if ("getHeader".equals(method.getName())) { return "X-HXJM-Service-Id".equals(args[0]) ? "test" : "X-HXJM-Service-Token".equals(args[0]) ? "isolated-test-token" : null; }
            throw new AssertionError("Unexpected request access");
        });
        return auth.authenticate(request, "assets.register");
    }

    private static final class FakeStore extends BusinessStore {
        private final FakeJdbc jdbc;
        FakeStore(FakeJdbc jdbc) { super((DataSource) Proxy.newProxyInstance(BusinessHistoryCheck.class.getClassLoader(), new Class<?>[]{DataSource.class}, (proxy, method, args) -> { throw new AssertionError("No database connection permitted"); })); this.jdbc = jdbc; }
        @Override public JdbcTemplate jdbc() { return jdbc; }
        @Override public Map<String, Object> write(BusinessActor actor, String operation, Map<String, Object> body, OffsetDateTime expiry, Function<JdbcTemplate, Map<String, Object>> work) { actor.requireOperation(operation); if (!expiry.isAfter(OffsetDateTime.now())) { throw BusinessException.expired("expired fixture"); } return work.apply(jdbc); }
        @Override public void event(JdbcTemplate jdbc, String type, String aggregate, String id, long revision, Map<String, Object> payload, OffsetDateTime expiry) { }
    }
    private static final class FakeJdbc extends JdbcTemplate {
        Map<String, Object> session, frame, result;
        Map<String, Map<String, Object>> assets = new LinkedHashMap<>();
        List<Map<String, Object>> observations = Collections.emptyList();
        String lastStream;
        boolean recordingCoverageWritten;
        @SuppressWarnings("unchecked")
        @Override public <T> T queryForObject(String sql, Class<T> type) { return queryForObject(sql, type, new Object[0]); }
        @Override public <T> T queryForObject(String sql, Class<T> type, Object... args) { if (sql.contains("pg_advisory")) { return (T) Boolean.TRUE; } if (sql.contains("pg_attribute")) { return (T) "character varying"; } throw new AssertionError("Unexpected SQL: " + sql); }
        @Override public List<Map<String, Object>> queryForList(String sql, Object... args) {
            if (sql.contains("FROM public.stream_session")) { return session == null ? Collections.emptyList() : Collections.singletonList(session); }
            if (sql.contains("FROM public.input_frame")) { return frame == null ? Collections.emptyList() : Collections.singletonList(frame); }
            if (sql.contains("FROM public.media_asset")) {
                if (sql.contains("WHERE id=?::uuid")) { Map<String, Object> row = assets.get(args[0].toString()); return row == null ? Collections.emptyList() : Collections.singletonList(row); }
                return new ArrayList<>(assets.values());
            }
            if (sql.contains("FROM public.analysis_frame")) { return result == null ? Collections.emptyList() : Collections.singletonList(result); }
            if (sql.contains("FROM public.detection_observation")) { return observations; }
            throw new AssertionError("Unexpected SQL: " + sql);
        }
        @Override public int update(String sql, Object... args) {
            if (sql.startsWith("INSERT INTO public.media_asset")) {
                lastStream = args[1].toString();
                Map<String, Object> row = values("id", args[0], "asset_type", args[2], "start_ts", args[3], "duration_ms", args[4],
                        "content_type", args[6], "source_id", args[7], "stream_session_id", args[8], "producer_key", args[9],
                        "storage_key", args[10], "byte_size", args[11], "checksum_sha256", args[12], "state", args[14], "revision", args[15], "expires_at", args[16], "valid", true);
                assets.put(args[0].toString(), row);
            } else if (sql.startsWith("UPDATE public.media_asset")) {
                Map<String, Object> row = assets.get(args[5].toString()); row.put("state", args[0]); if (args[1] != null) { row.put("byte_size", args[1]); } if (args[2] != null) { row.put("checksum_sha256", args[2]); } row.put("revision", args[4]);
            } else if (sql.startsWith("UPDATE public.input_frame")) { frame.put("media_asset_id", args[0]); frame.put("media_pts_ms", args[1]); }
            else if (sql.startsWith("INSERT INTO public.processing_coverage")) { recordingCoverageWritten = true; }
            else if (!sql.startsWith("UPDATE public.stream_session")) { throw new AssertionError("Unexpected SQL: " + sql); }
            return 1;
        }
    }
}
