package edu.cqupt.hxjm.algdeployment.business.service;

import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.stream.ImageInputStream;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessActor;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessStore;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

@Service
@ConditionalOnProperty(prefix = "hxjm.business", name = "enabled", havingValue = "true")
public class ImageAssetService {
    public static final int MAX_BYTES = 10 * 1024 * 1024;
    private final BusinessStore store;
    private final Path root;
    public ImageAssetService(BusinessStore store, @Value("${hxjm.business.storage-root:/data/nfs_storage/hxjm}") String root) {
        this.store = store; this.root = Paths.get(root).toAbsolutePath().normalize();
    }

    public Map<String, Object> upload(BusinessActor actor, Map<String, Object> body, byte[] bytes) {
        actor.requireOperation("assets.upload");
        fields(body, "request_id", "trace_id", "asset_id", "purpose", "source_id", "input_frame_id", "tracklet_id", "occurred_at");
        String id = uuid(body, "asset_id"), purpose = text(body, "purpose", 32);
        if (UUID.fromString(id).version() != 4) { throw BusinessException.invalid("新图片标识须为UUIDv4"); }
        if (!Arrays.asList("query", "enrollment", "history", "evidence").contains(purpose)) { throw BusinessException.invalid("图片用途无效"); }
        if (actor.isShared() && !Arrays.asList("query", "enrollment").contains(purpose)) { throw BusinessException.forbidden(); }
        if ("enrollment".equals(purpose)) { actor.requireOperation("identities.register"); }
        String source = body.get("source_id") == null ? null : uuid(body, "source_id");
        if (source != null) { actor.requireSource(source); }
        if (("history".equals(purpose) || "evidence".equals(purpose)) && source == null) {
            throw BusinessException.invalid("历史或证据图片须引用视频来源");
        }
        String frame = body.get("input_frame_id") == null ? null : uuid(body, "input_frame_id");
        String track = body.get("tracklet_id") == null ? null : uuid(body, "tracklet_id");
        if ("history".equals(purpose) && frame == null) { throw BusinessException.invalid("历史样本须引用原输入帧"); }
        Map<String, Object> image = inspect(bytes);
        String checksum = sha256(bytes);
        Map<String, Object> immutable = new java.util.LinkedHashMap<>(body);
        immutable.put("checksum_sha256", checksum);
        OffsetDateTime received = OffsetDateTime.now(ZoneOffset.UTC);
        OffsetDateTime occurred = body.get("occurred_at") == null ? received : time(body, "occurred_at");
        OffsetDateTime expiry = "enrollment".equals(purpose) ? null : occurred.plusDays(7);
        if ("query".equals(purpose) && occurred.isAfter(received)) { throw BusinessException.invalid("查询图片时间不能晚于接收时间"); }
        String type = "enrollment".equals(purpose) ? "enrollment_image" : "query".equals(purpose) ? "query_image" : "crop";
        String key = "images/" + purpose + "/" + id + image.get("extension");
        return store.write(actor, "assets.upload", immutable, expiry == null ? received.plusDays(7) : expiry, jdbc -> {
            jdbc.queryForObject("SELECT pg_advisory_xact_lock(hashtextextended(?,0)) IS NULL", Boolean.class, "asset-upload:" + id);
            List<Map<String, Object>> existing = jdbc.queryForList("SELECT id::text,asset_type,checksum_sha256,storage_key,source_id::text,start_ts,meta->>'owner_actor_key' AS owner_actor_key,meta->>'input_frame_id' AS input_frame_id,meta->>'tracklet_id' AS tracklet_id,expires_at FROM public.media_asset WHERE id=?::uuid", id);
            if (!existing.isEmpty()) {
                Map<String, Object> old = existing.get(0);
                if (!checksum.equals(String.valueOf(old.get("checksum_sha256")).trim()) || !type.equals(old.get("asset_type"))
                        || !key.equals(old.get("storage_key")) || !actor.getActorKey().equals(old.get("owner_actor_key"))
                        || !java.util.Objects.equals(source, old.get("source_id"))
                        || !java.util.Objects.equals(frame, old.get("input_frame_id"))
                        || !java.util.Objects.equals(track, old.get("tracklet_id"))
                        || body.get("occurred_at") != null && !occurred.equals(RecordingService.instant(old.get("start_ts")))) {
                    throw BusinessException.conflict("图片标识已对应其他内容、用途或主体");
                }
                if (old.get("expires_at") != null && !RecordingService.instant(old.get("expires_at")).isAfter(received)) { throw BusinessException.expired("图片已到期"); }
                return response(id, key, old.get("expires_at"), image, true);
            }
            String session = null, stream = null;
            if (frame != null) {
                Map<String, Object> original = RecordingService.one(jdbc.queryForList("SELECT ss.source_id::text,f.stream_session_id::text,f.occurred_at,f.expires_at,ss.camera_stream_id,cs.stream_name FROM public.input_frame f JOIN public.stream_session ss ON ss.id=f.stream_session_id LEFT JOIN public.camera_stream cs ON cs.id=ss.camera_stream_id WHERE f.id=?::uuid", frame), "输入帧不存在");
                if (!java.util.Objects.equals(source, original.get("source_id"))) { throw BusinessException.conflict("图片来源与原帧不一致"); }
                if (!RecordingService.instant(original.get("expires_at")).isAfter(received)) { throw BusinessException.expired("原帧已到期"); }
                if ("history".equals(purpose) && !occurred.equals(RecordingService.instant(original.get("occurred_at")))) { throw BusinessException.conflict("历史图片须沿用原帧发生时间"); }
                session = original.get("stream_session_id").toString();
                String streamType = jdbc.queryForObject("SELECT atttypid::regtype::text FROM pg_attribute WHERE attrelid='public.media_asset'::regclass AND attname='stream_id' AND NOT attisdropped", String.class);
                stream = "uuid".equals(streamType) ? original.get("camera_stream_id").toString() : original.get("stream_name").toString();
            }
            if (track != null && jdbc.queryForList("SELECT id FROM public.tracklet WHERE id=?::uuid AND source_id=?::uuid AND expires_at>now()", track, source).isEmpty()) {
                throw BusinessException.invalid("轨迹不存在、已到期或来源不符");
            }
            Map<String, Object> meta = values("schema_version", "1", "owner_actor_key", actor.getActorKey(), "purpose", purpose,
                    "image_width", image.get("image_width"), "image_height", image.get("image_height"), "input_frame_id", frame, "tracklet_id", track);
            writeFile(key, bytes, checksum);
            jdbc.update("INSERT INTO public.media_asset(id,stream_id,asset_type,start_ts,duration_ms,content_type,meta,source_id,stream_session_id,producer_key,storage_key,byte_size,checksum_sha256,state,expires_at) VALUES (?::uuid,?" + ("uuid".equals(jdbc.queryForObject("SELECT atttypid::regtype::text FROM pg_attribute WHERE attrelid='public.media_asset'::regclass AND attname='stream_id' AND NOT attisdropped", String.class)) ? "::uuid" : "") + ",?,?,0,?,?::jsonb,?::uuid,?::uuid,?,?,?,?,'available',?)",
                    id, stream, type, occurred, image.get("content_type"), json(meta), source, session, "image:" + id, key, bytes.length, checksum, expiry);
            return response(id, key, expiry, image, false);
        });
    }

    public static Map<String, Object> inspect(byte[] bytes) {
        if (bytes == null || bytes.length == 0 || bytes.length > MAX_BYTES) { throw BusinessException.invalid("图片须为1字节至10MiB"); }
        try (ImageInputStream input = ImageIO.createImageInputStream(new ByteArrayInputStream(bytes))) {
            Iterator<ImageReader> readers = ImageIO.getImageReaders(input);
            if (!readers.hasNext()) { throw BusinessException.invalid("图片须为JPEG或PNG"); }
            ImageReader reader = readers.next();
            try {
                reader.setInput(input, true, true);
                String format = reader.getFormatName().toLowerCase(java.util.Locale.ROOT);
                if (!format.equals("jpeg") && !format.equals("png")) { throw BusinessException.invalid("图片须为JPEG或PNG"); }
                int width = reader.getWidth(0), height = reader.getHeight(0);
                if (width < 1 || height < 1 || (long) width * height > 16000000L) { throw BusinessException.invalid("图片像素数量不得超过1600万"); }
                BufferedImage decoded = reader.read(0);
                if (decoded == null) { throw BusinessException.invalid("图片内容不完整"); }
                return values("content_type", "jpeg".equals(format) ? "image/jpeg" : "image/png", "extension", "jpeg".equals(format) ? ".jpg" : ".png", "image_width", width, "image_height", height);
            } finally { reader.dispose(); }
        } catch (IOException invalid) { throw BusinessException.invalid("图片无法解码"); }
    }

    private void writeFile(String key, byte[] bytes, String checksum) {
        Path temporary = null;
        try {
            Path realRoot = root.toRealPath(), destination = realRoot.resolve(key);
            Files.createDirectories(destination.getParent());
            if (!destination.getParent().toRealPath().startsWith(realRoot)) { throw BusinessException.forbidden(); }
            if (Files.exists(destination)) {
                if (!destination.toRealPath().startsWith(realRoot) || !checksum.equals(sha256(Files.readAllBytes(destination)))) { throw BusinessException.conflict("图片路径已被不同文件占用"); }
                return;
            }
            temporary = Files.createTempFile(destination.getParent(), ".upload-", ".tmp");
            Files.write(temporary, bytes);
            try (java.nio.channels.FileChannel channel = java.nio.channels.FileChannel.open(temporary, java.nio.file.StandardOpenOption.WRITE)) { channel.force(true); }
            Files.move(temporary, destination, StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException failure) { throw BusinessException.unavailable("图片存储暂不可用，请保留原标识重试"); }
        finally { if (temporary != null) { try { Files.deleteIfExists(temporary); } catch (IOException ignored) { } } }
    }

    private static String sha256(byte[] bytes) {
        try {
            StringBuilder result = new StringBuilder();
            for (byte b : MessageDigest.getInstance("SHA-256").digest(bytes)) { result.append(String.format("%02x", b & 255)); }
            return result.toString();
        } catch (java.security.NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
    private Map<String, Object> response(String id, String key, Object expiry, Map<String, Object> image, boolean duplicate) {
        return values("asset_id", id, "storage_key", key, "state", "available", "expires_at", expiry == null ? null : RecordingService.instant(expiry).toString(),
                "image_width", image.get("image_width"), "image_height", image.get("image_height"), "duplicate", duplicate);
    }
}
