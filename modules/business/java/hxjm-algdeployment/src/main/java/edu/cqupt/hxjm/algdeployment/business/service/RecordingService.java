package edu.cqupt.hxjm.algdeployment.business.service;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessStore;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

@Service
@ConditionalOnProperty(prefix = "hxjm.business", name = "enabled", havingValue = "true")
public class RecordingService {
    private final BusinessStore store;
    private final Path root;

    public RecordingService(BusinessStore store,
            @Value("${hxjm.business.storage-root:/data/nfs_storage/hxjm}") String storageRoot) {
        this.store = store;
        this.root = Paths.get(storageRoot).toAbsolutePath().normalize();
    }

    public Map<String, Object> register(BusinessActor actor, Map<String, Object> body) {
        fields(body, "request_id", "trace_id", "asset_id", "producer_key", "asset_type", "source_id",
                "stream_session_id", "storage_key", "state", "start_at", "end_at", "content_type",
                "byte_size", "checksum_sha256", "write_attempt_id", "expected_revision", "frame_locations", "recording_alignment", "expires_at");
        String id = uuid(body, "asset_id"), source = uuid(body, "source_id"), session = uuid(body, "stream_session_id");
        actor.requireSource(source);
        String producer = text(body, "producer_key"), type = text(body, "asset_type", 32);
        if (!"recording".equals(type) && !"algorithm_output".equals(type)) {
            throw BusinessException.invalid("本阶段接收recording或algorithm_output资产");
        }
        String key = storageKey(text(body, "storage_key", 4096));
        String state = text(body, "state", 24);
        if (!Arrays.asList("preparing", "available", "unavailable", "missing").contains(state)) {
            throw BusinessException.invalid("资产状态不允许由生产服务设置");
        }
        String contentType = text(body, "content_type", 128);
        OffsetDateTime start = time(body, "start_at"), end = time(body, "end_at"), expiry = time(body, "expires_at");
        if (!end.isAfter(start) || !expiry.equals(end.plusDays(7))) {
            throw BusinessException.invalid("视频资产区间须非空，期限须为结束后七天");
        }
        long duration;
        try { duration = Duration.between(start, end).toMillis(); }
        catch (ArithmeticException tooLarge) { throw BusinessException.invalid("录像区间过长"); }
        if (duration <= 0 || !start.plus(Duration.ofMillis(duration)).equals(end)) {
            throw BusinessException.invalid("录像区间须能精确表示为毫秒");
        }
        Long size = body.get("byte_size") == null ? null : integer(body, "byte_size", 0, Long.MAX_VALUE);
        String checksum = body.get("checksum_sha256") == null ? null : text(body, "checksum_sha256", 64);
        if (checksum != null && !checksum.matches("[0-9a-f]{64}")) { throw BusinessException.invalid("SHA256格式错误"); }
        String attempt = body.get("write_attempt_id") == null ? null : uuid(body, "write_attempt_id");
        if ("preparing".equals(state) && attempt == null) { throw BusinessException.invalid("准备资产须有写入尝试标识"); }
        if ("available".equals(state) && (size == null || checksum == null)) {
            throw BusinessException.invalid("可用资产须有大小及校验摘要");
        }
        List<Object> locations = body.get("frame_locations") == null ? Collections.emptyList() : list(body.get("frame_locations"));
        if (!locations.isEmpty() && !"available".equals(state)) { throw BusinessException.invalid("仅可用资产可补齐帧定位"); }
        Map<String, Object> alignment = body.get("recording_alignment") == null ? null : alignment(map(body.get("recording_alignment")), duration);
        if (alignment != null && (!"recording".equals(type) || !"available".equals(state))) {
            throw BusinessException.invalid("仅可用录像可登记媒体时钟对齐");
        }
        return store.write(actor, "assets.register", body, expiry, jdbc -> {
            jdbc.queryForObject("SELECT pg_advisory_xact_lock(hashtextextended(?,0)) IS NULL", Boolean.class, "asset:" + producer);
            Map<String, Object> input = one(jdbc.queryForList("SELECT ss.id,ss.source_id,ss.camera_stream_id,ss.expires_at,ss.started_at,ss.ended_at,cs.stream_name FROM public.stream_session ss LEFT JOIN public.camera_stream cs ON cs.id=ss.camera_stream_id WHERE ss.id=?::uuid FOR UPDATE OF ss", session), "输入会话不存在");
            if (!source.equals(input.get("source_id").toString())) { throw BusinessException.conflict("录像来源与输入会话不一致"); }
            if (input.get("camera_stream_id") == null) { throw BusinessException.conflict("输入会话未绑定流目录，不能写入旧资产流字段"); }
            if (!instant(input.get("expires_at")).isAfter(OffsetDateTime.now())) { throw BusinessException.expired("输入会话已到期"); }
            if (start.isBefore(instant(input.get("started_at")))) { throw BusinessException.invalid("资产早于输入会话"); }
            if (input.get("ended_at") != null && end.isAfter(instant(input.get("ended_at")))) { throw BusinessException.invalid("资产超出已结束输入会话"); }
            List<Map<String, Object>> found = jdbc.queryForList("SELECT *,meta->'recording_alignment' AS recording_alignment,jsonb_typeof(meta) AS meta_type,expires_at>now() AS valid FROM public.media_asset WHERE id=?::uuid OR producer_key=? OR storage_key=? FOR UPDATE", id, producer, key);
            Map<String, Object> old = found.isEmpty() ? null : found.get(0);
            if (found.size() > 1 || old != null && (!id.equals(old.get("id").toString()) || !producer.equals(old.get("producer_key")) || !key.equals(old.get("storage_key")))) {
                throw BusinessException.conflict("资产标识、生产键或文件定位已被其他资产占用");
            }
            if (old != null && !Boolean.TRUE.equals(old.get("valid"))) { throw BusinessException.expired("资产已到期"); }
            if (old != null && (!source.equals(Objects.toString(old.get("source_id"), null)) || !session.equals(Objects.toString(old.get("stream_session_id"), null))
                    || !type.equals(old.get("asset_type")) || !start.equals(instant(old.get("start_ts")))
                    || ((Number) old.get("duration_ms")).longValue() != duration || !expiry.equals(instant(old.get("expires_at")))
                    || !contentType.equals(old.get("content_type")))) {
                throw BusinessException.conflict("同一资产不能变更来源、时间、用途或期限");
            }
            if (old != null && old.get("checksum_sha256") != null && ((size != null && !Objects.equals(size, number(old.get("byte_size")))) || (checksum != null && !checksum.equals(old.get("checksum_sha256").toString().trim())))) {
                throw BusinessException.conflict("同一资产对应不同文件内容");
            }
            if (old != null && Arrays.asList("delete_pending", "deleted").contains(old.get("state"))) { throw BusinessException.expired("资产正在清理"); }
            Map<String, Object> previousAlignment = old == null ? null : storedAlignment(old);
            if (alignment != null && old != null && old.get("meta_type") != null && !"object".equals(old.get("meta_type"))) {
                throw BusinessException.conflict("已有媒体元数据不是对象，不能合并录像对齐信息");
            }
            if (alignment != null && previousAlignment != null && !alignment.equals(previousAlignment)) {
                throw BusinessException.conflict("同一录像不能变更媒体时钟对齐");
            }
            Map<String, Object> effectiveAlignment = alignment == null ? previousAlignment : alignment;
            boolean duplicate = old != null && state.equals(old.get("state")) && Objects.equals(size, number(old.get("byte_size")))
                    && Objects.equals(checksum, old.get("checksum_sha256") == null ? null : old.get("checksum_sha256").toString().trim()) && locations.isEmpty()
                    && (alignment == null || previousAlignment != null);
            if (duplicate) { return assetResponse(old, true); }
            if (old != null && (!body.containsKey("expected_revision") || integer(body, "expected_revision", 1, Long.MAX_VALUE) != ((Number) old.get("revision")).longValue())) {
                throw BusinessException.conflict("资产修订号不匹配");
            }
            if (old == null && body.containsKey("expected_revision")) { throw BusinessException.invalid("新资产不填写expected_revision"); }
            if (old != null && "preparing".equals(state) && !"preparing".equals(old.get("state"))) { throw BusinessException.conflict("已完成资产不能恢复准备状态"); }
            if ("available".equals(state)) { verifyFile(key, size, checksum); }
            long revision = old == null ? 1 : ((Number) old.get("revision")).longValue() + 1;
            if (old == null) {
                String streamType = jdbc.queryForObject("SELECT atttypid::regtype::text FROM pg_attribute WHERE attrelid='public.media_asset'::regclass AND attname='stream_id'", String.class);
                Object stream = "uuid".equals(streamType) ? UUID.fromString(input.get("camera_stream_id").toString()) : input.get("stream_name").toString();
                jdbc.update("INSERT INTO public.media_asset(id,stream_id,asset_type,start_ts,duration_ms,play_url,oss_key,content_type,source_id,stream_session_id,producer_key,storage_key,byte_size,checksum_sha256,write_attempt_id,state,revision,expires_at) VALUES (?::uuid,?,?,?,?,NULL,?,?,?::uuid,?::uuid,?,?,?,?,?::uuid,?,?,?)",
                        id, stream, type, start, duration, key, contentType, source, session, producer, key, size, checksum, attempt, state, revision, expiry);
            } else {
                jdbc.update("UPDATE public.media_asset SET state=?,byte_size=COALESCE(?,byte_size),checksum_sha256=COALESCE(?,checksum_sha256),write_attempt_id=COALESCE(?::uuid,write_attempt_id),revision=? WHERE id=?::uuid", state, size, checksum, attempt, revision, id);
            }
            if (alignment != null) {
                // Both registration paths hold the input-session row before inspecting frames/assets.
                for (Map<String, Object> other : jdbc.queryForList("SELECT id,meta->'recording_alignment' AS recording_alignment,duration_ms FROM public.media_asset WHERE stream_session_id=?::uuid AND id<>?::uuid AND meta->'recording_alignment'->>'schema_version'='1'", session, id)) {
                    Map<String, Object> range = storedAlignment(other);
                    if (integer(range, "stream_start_pts_ms", 0, Long.MAX_VALUE) < integer(alignment, "stream_end_pts_ms", 1, Long.MAX_VALUE)
                            && integer(range, "stream_end_pts_ms", 1, Long.MAX_VALUE) > integer(alignment, "stream_start_pts_ms", 0, Long.MAX_VALUE)) {
                        throw BusinessException.conflict("同一输入会话的录像媒体范围重叠");
                    }
                }
                jdbc.update("UPDATE public.media_asset SET meta=COALESCE(meta,'{}'::jsonb)||jsonb_build_object('recording_alignment',?::jsonb) WHERE id=?::uuid", json(alignment), id);
            }
            if ("available".equals(state) && effectiveAlignment != null) {
                long first = integer(effectiveAlignment, "stream_start_pts_ms", 0, Long.MAX_VALUE);
                long last = integer(effectiveAlignment, "stream_end_pts_ms", 1, Long.MAX_VALUE);
                for (Map<String, Object> frame : jdbc.queryForList("SELECT * FROM public.input_frame WHERE stream_session_id=?::uuid AND stream_pts_ms>=? AND stream_pts_ms<? AND expires_at>now() ORDER BY id FOR UPDATE", session, first, last)) {
                    locateFrame(jdbc, frame, frame.get("id").toString(), id, session, start, end, ((Number) frame.get("stream_pts_ms")).longValue() - first);
                }
            }
            for (Object value : locations) {
                Map<String, Object> location = map(value);
                fields(location, "frame_id", "media_pts_ms");
                String frame = uuid(location, "frame_id");
                long offset = integer(location, "media_pts_ms", 0, duration - 1);
                Map<String, Object> existing = one(jdbc.queryForList("SELECT stream_session_id,occurred_at,stream_pts_ms,media_asset_id,media_pts_ms,expires_at FROM public.input_frame WHERE id=?::uuid FOR UPDATE", frame), "输入帧不存在");
                if (effectiveAlignment != null && existing.get("stream_pts_ms") != null) {
                    long pts = ((Number) existing.get("stream_pts_ms")).longValue();
                    long first = integer(effectiveAlignment, "stream_start_pts_ms", 0, Long.MAX_VALUE);
                    if (pts < first || pts >= integer(effectiveAlignment, "stream_end_pts_ms", 1, Long.MAX_VALUE) || offset != pts - first) {
                        throw BusinessException.conflict("显式帧定位与录像媒体时钟不一致");
                    }
                }
                locateFrame(jdbc, existing, frame, id, session, start, end, offset);
            }
            if ("available".equals(state)) {
                jdbc.update("UPDATE public.stream_session SET expires_at=GREATEST(expires_at,?) WHERE id=?::uuid AND state='open'", end.plusDays(7), session);
            }
            if ("recording".equals(type)) {
                jdbc.update("INSERT INTO public.processing_coverage(source_id,stream_session_id,stage,coverage_key,closed,start_at,end_at,status,reason_code,expires_at) VALUES (?::uuid,?::uuid,'recording',?,?,?,?,?,?,?) ON CONFLICT(source_id,stage,coverage_key) DO UPDATE SET closed=EXCLUDED.closed,status=EXCLUDED.status,reason_code=EXCLUDED.reason_code,revision=processing_coverage.revision+1",
                        source, session, "asset:" + id, !"preparing".equals(state), start, end,
                        "available".equals(state) ? "complete" : "preparing".equals(state) ? "partial" : "unavailable",
                        "available".equals(state) ? null : "preparing".equals(state) ? "RECORDING_PENDING" : "STORAGE_UNAVAILABLE", expiry);
            }
            store.event(jdbc, "asset." + state, "media_asset", id, revision, values("asset_id", id, "source_id", source), expiry);
            return values("asset_id", id, "producer_key", producer, "state", state, "revision", revision, "expires_at", expiry.toString(), "duplicate", false);
        });
    }

    public Path content(BusinessActor actor, String assetId) {
        Map<String, Object> asset = asset(actor, assetId);
        if (!"available".equals(asset.get("state"))) { throw BusinessException.unavailable("文件尚未就绪或暂不可读"); }
        return readable(storageKey(Objects.toString(asset.get("storage_key"), "")));
    }

    public Map<String, Object> asset(BusinessActor actor, String assetId) {
        String id = uuid(assetId, "asset_id");
        Map<String, Object> asset = one(store.jdbc().queryForList("SELECT *,meta->>'owner_actor_key' AS owner_actor_key,(expires_at IS NULL OR expires_at>now()) AS valid FROM public.media_asset WHERE id=?::uuid AND state IS NOT NULL", id), "资产不存在");
        if (asset.get("source_id") != null) {
            actor.requireSource(asset.get("source_id").toString());
        } else if ("query_image".equals(asset.get("asset_type"))) {
            if (!actor.getActorKey().equals(asset.get("owner_actor_key")) && !(actor.isService() && actor.allows("assets.process"))) {
                throw BusinessException.forbidden();
            }
        } else if ("enrollment_image".equals(asset.get("asset_type"))) {
            actor.requireOperation("identities.query");
        } else {
            throw BusinessException.forbidden();
        }
        if (!Boolean.TRUE.equals(asset.get("valid"))) { throw BusinessException.expired("资产已到期"); }
        return asset;
    }

    private static Map<String, Object> alignment(Map<String, Object> value, long duration) {
        fields(value, "schema_version", "stream_start_pts_ms", "stream_end_pts_ms", "media_start_pts_ms");
        if (!"1".equals(text(value, "schema_version", 32))) { throw BusinessException.invalid("录像对齐结构版本无效"); }
        long first = integer(value, "stream_start_pts_ms", 0, Long.MAX_VALUE);
        long last = integer(value, "stream_end_pts_ms", 1, Long.MAX_VALUE);
        if (last <= first || last - first != duration || integer(value, "media_start_pts_ms", 0, 0) != 0) {
            throw BusinessException.invalid("录像媒体范围须与文件时长一致，文件起点须为零");
        }
        return values("schema_version", "1", "stream_start_pts_ms", first, "stream_end_pts_ms", last, "media_start_pts_ms", 0L);
    }

    private static Map<String, Object> storedAlignment(Map<String, Object> asset) {
        Object raw = asset.get("recording_alignment");
        return raw == null ? null : alignment(raw instanceof Map ? map(raw) : parse(raw.toString()), ((Number) asset.get("duration_ms")).longValue());
    }

    private static void locateFrame(JdbcTemplate jdbc, Map<String, Object> frame, String frameId,
            String assetId, String session, OffsetDateTime start, OffsetDateTime end, long offset) {
        OffsetDateTime occurred = instant(frame.get("occurred_at"));
        if (!session.equals(frame.get("stream_session_id").toString()) || occurred.isBefore(start) || !occurred.isBefore(end)) {
            throw BusinessException.conflict("帧不属于该录像会话或时间范围");
        }
        if (!instant(frame.get("expires_at")).isAfter(OffsetDateTime.now())) { throw BusinessException.expired("输入帧已到期"); }
        if (frame.get("media_asset_id") != null && (!assetId.equals(frame.get("media_asset_id").toString()) || !Objects.equals(number(frame.get("media_pts_ms")), offset))) {
            throw BusinessException.conflict("帧已有不同录像定位");
        }
        jdbc.update("UPDATE public.input_frame SET media_asset_id=?::uuid,media_pts_ms=? WHERE id=?::uuid", assetId, offset, frameId);
        frame.put("media_asset_id", assetId); frame.put("media_pts_ms", offset);
    }

    static void alignFrame(JdbcTemplate jdbc, Map<String, Object> frame) {
        if (frame.get("stream_pts_ms") == null) { return; }
        long pts = ((Number) frame.get("stream_pts_ms")).longValue();
        List<Map<String, Object>> assets = jdbc.queryForList("SELECT id,start_ts,duration_ms,meta->'recording_alignment' AS recording_alignment FROM public.media_asset WHERE stream_session_id=?::uuid AND asset_type='recording' AND state='available' AND expires_at>now() AND meta->'recording_alignment'->>'schema_version'='1' AND jsonb_typeof(meta->'recording_alignment'->'stream_start_pts_ms')='number' AND jsonb_typeof(meta->'recording_alignment'->'stream_end_pts_ms')='number' AND meta->'recording_alignment'->'stream_start_pts_ms'<=to_jsonb(?::bigint) AND meta->'recording_alignment'->'stream_end_pts_ms'>to_jsonb(?::bigint)", frame.get("stream_session_id"), pts, pts);
        if (assets.size() > 1) { throw BusinessException.conflict("输入帧对应多段重叠录像"); }
        if (assets.isEmpty()) { return; }
        Map<String, Object> asset = assets.get(0), range = storedAlignment(asset);
        OffsetDateTime start = instant(asset.get("start_ts"));
        locateFrame(jdbc, frame, frame.get("id").toString(), asset.get("id").toString(), frame.get("stream_session_id").toString(),
                start, start.plus(Duration.ofMillis(((Number) asset.get("duration_ms")).longValue())), pts - integer(range, "stream_start_pts_ms", 0, Long.MAX_VALUE));
    }

    public static String storageKey(String key) {
        Path path;
        try { path = Paths.get(key); } catch (RuntimeException exception) { throw BusinessException.invalid("文件定位格式错误"); }
        if (key.isEmpty() || path.isAbsolute() || key.indexOf('\\') >= 0 || key.contains(":") || key.contains("?")) { throw BusinessException.invalid("文件定位须为受控根目录下的相对路径"); }
        for (Path part : path) { if ("..".equals(part.toString()) || ".".equals(part.toString())) { throw BusinessException.invalid("文件定位不允许相对越界"); } }
        if (!path.normalize().toString().equals(key)) { throw BusinessException.invalid("文件定位须使用规范相对路径"); }
        return key;
    }

    private Path readable(String key) {
        try {
            Path realRoot = root.toRealPath(), path = realRoot.resolve(key).toRealPath();
            if (!path.startsWith(realRoot)) { throw BusinessException.forbidden(); }
            if (!Files.isRegularFile(path) || !Files.isReadable(path)) { throw BusinessException.unavailable("资产文件暂不可读"); }
            return path;
        } catch (IOException exception) { throw BusinessException.unavailable("资产存储暂不可访问"); }
    }

    private void verifyFile(String key, long expectedSize, String expectedHash) {
        Path path = readable(key);
        try {
            if (Files.size(path) != expectedSize) { throw BusinessException.conflict("文件大小与登记不一致"); }
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream stream = Files.newInputStream(path)) {
                byte[] buffer = new byte[65536];
                int count;
                while ((count = stream.read(buffer)) != -1) { digest.update(buffer, 0, count); }
            }
            StringBuilder hash = new StringBuilder();
            for (byte item : digest.digest()) { hash.append(String.format("%02x", item & 255)); }
            if (!expectedHash.equals(hash.toString())) { throw BusinessException.conflict("文件摘要与登记不一致"); }
        } catch (IOException exception) { throw BusinessException.unavailable("资产文件校验暂不可用"); }
        catch (NoSuchAlgorithmException exception) { throw new IllegalStateException(exception); }
    }

    private Map<String, Object> assetResponse(Map<String, Object> asset, boolean duplicate) {
        return values("asset_id", asset.get("id").toString(), "producer_key", asset.get("producer_key"),
                "state", asset.get("state"), "revision", asset.get("revision"), "expires_at", instant(asset.get("expires_at")).toString(), "duplicate", duplicate);
    }

    public static OffsetDateTime instant(Object value) {
        if (value instanceof OffsetDateTime) { return ((OffsetDateTime) value).withOffsetSameInstant(ZoneOffset.UTC); }
        if (value instanceof Timestamp) { return ((Timestamp) value).toInstant().atOffset(ZoneOffset.UTC); }
        return OffsetDateTime.parse(value.toString()).withOffsetSameInstant(ZoneOffset.UTC);
    }
    private static Long number(Object value) { return value == null ? null : ((Number) value).longValue(); }
    public static Map<String, Object> one(List<Map<String, Object>> rows, String missing) {
        if (rows.isEmpty()) { throw BusinessException.notFound(missing); }
        return rows.get(0);
    }
}
