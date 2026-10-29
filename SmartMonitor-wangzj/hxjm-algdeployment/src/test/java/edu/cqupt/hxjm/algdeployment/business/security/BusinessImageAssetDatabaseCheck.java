package edu.cqupt.hxjm.algdeployment.business.security;

import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Map;
import java.util.UUID;
import javax.imageio.ImageIO;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.service.ImageAssetService;
import edu.cqupt.hxjm.algdeployment.business.service.RecordingService;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessStore;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

/** Run only against a disposable database after both approved migrations. */
public class BusinessImageAssetDatabaseCheck {
    public static void main(String[] args) throws Exception {
        String url = System.getenv("HXJM_TEST_JDBC_URL");
        if (!"1".equals(System.getenv("HXJM_ISOLATED_TEST")) || url == null
                || !url.matches("jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/hxjm_stage[12]_[a-z0-9_]+")) {
            throw new IllegalArgumentException("An explicitly opted-in disposable database is required");
        }
        BusinessStore store = new BusinessStore(new DriverManagerDataSource(url, System.getenv("HXJM_TEST_DB_USER"), System.getenv("HXJM_TEST_DB_PASSWORD")));
        Path fixture = Files.createTempDirectory(Paths.get("/data/nfs_storage/hxjm"), ".test-images-");
        try {
            ImageAssetService images = new ImageAssetService(store, fixture.toString());
            RecordingService recordings = new RecordingService(store, fixture.toString());
            BusinessSecurityProperties.Grant grant = new BusinessSecurityProperties.Grant();
            grant.setOperations(new HashSet<>(Arrays.asList("assets.upload", "media.resolve", "identities.query", "identities.register")));
            BusinessActor owner = new BusinessActor("user:1", 1L, null, grant);
            BusinessActor stranger = new BusinessActor("user:2", 2L, null, grant);
            byte[] bytes = png(0x00ff00), changed = png(0xff0000);
            String queryId = UUID.randomUUID().toString();
            Map<String, Object> query = values("request_id", UUID.randomUUID().toString(), "asset_id", queryId, "purpose", "query");
            Map<String, Object> first = images.upload(owner, query, bytes);
            check("available".equals(first.get("state")) && first.get("expires_at") != null, "query upload is temporary");
            check(recordings.content(owner, queryId).toRealPath().startsWith(fixture), "controlled image path");
            fails(403, () -> recordings.asset(stranger, queryId));
            check(Boolean.TRUE.equals(images.upload(owner, query, bytes).get("duplicate")), "upload retry returns original result");
            fails(409, () -> images.upload(owner, query, changed));
            Map<String, Object> otherRequest = values("request_id", UUID.randomUUID().toString(), "asset_id", queryId, "purpose", "query");
            fails(409, () -> images.upload(owner, otherRequest, changed));
            Map<String, Object> changedTime = new java.util.LinkedHashMap<>(otherRequest);
            changedTime.put("occurred_at", java.time.OffsetDateTime.now().minusMinutes(1).toString());
            fails(409, () -> images.upload(owner, changedTime, bytes));
            Map<String, Object> enrollment = values("request_id", UUID.randomUUID().toString(), "asset_id", UUID.randomUUID().toString(), "purpose", "enrollment");
            check(images.upload(owner, enrollment, bytes).get("expires_at") == null, "explicit enrollment has no automatic expiry");
            check(recordings.asset(stranger, enrollment.get("asset_id").toString()).get("source_id") == null, "authorized personnel library supports non-camera images");
            fails(400, () -> ImageAssetService.inspect("<html>not an image</html>".getBytes(java.nio.charset.StandardCharsets.UTF_8)));
            store.jdbc().update("UPDATE public.media_asset SET expires_at=now()-interval '1 second' WHERE id=?::uuid", queryId);
            fails(410, () -> recordings.asset(owner, queryId));
            fails(410, () -> images.upload(owner, otherRequest, bytes));
            System.out.println("BusinessImageAssetDatabaseCheck passed: upload, private query, durable enrollment, retry, conflict, expiry and file validation.");
        } finally {
            try (java.util.stream.Stream<Path> paths = Files.walk(fixture)) {
                for (Path path : (Iterable<Path>) paths.sorted(Comparator.reverseOrder())::iterator) { Files.delete(path); }
            }
        }
    }
    private static byte[] png(int rgb) throws Exception {
        BufferedImage image = new BufferedImage(8, 6, BufferedImage.TYPE_INT_RGB);
        image.setRGB(1, 1, rgb);
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        ImageIO.write(image, "png", output);
        return output.toByteArray();
    }
    private static void check(boolean condition, String message) { if (!condition) { throw new AssertionError(message); } }
    private static void fails(int status, Runnable action) {
        try { action.run(); throw new AssertionError("Expected " + status); }
        catch (BusinessException expected) { check(expected.getStatus() == status, "Expected " + status + ", got " + expected.getStatus()); }
    }
}
