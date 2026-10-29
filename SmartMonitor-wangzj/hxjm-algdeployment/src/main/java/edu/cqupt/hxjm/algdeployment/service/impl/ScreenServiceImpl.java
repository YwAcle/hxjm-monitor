package edu.cqupt.hxjm.algdeployment.service.impl;

import edu.cqupt.hxjm.algdeployment.mapper.ScreenMapper;
import edu.cqupt.hxjm.algdeployment.service.IScreenService;
import edu.cqupt.hxjm.common.config.AiTaskProperties;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class ScreenServiceImpl implements IScreenService {

    private final ScreenMapper screenMapper;
    private final AiTaskProperties aiTaskProperties;

    private static final DateTimeFormatter START_PARAM_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSSSSSXXX");
    private static final long MTX_START_PREROLL_MS = 2000L;
    private static final int DEFAULT_MTX_HTTP_PORT = 9996;

    public ScreenServiceImpl(ScreenMapper screenMapper, AiTaskProperties aiTaskProperties) {
        this.screenMapper = screenMapper;
        this.aiTaskProperties = aiTaskProperties;
    }

    @Override
    public Long getDeviceCount() {
        return screenMapper.selectDeviceCount();
    }

    @Override
    public Map<String, Object> getAlarmInitData() {
        Long vadTotalToday = screenMapper.selectVadAnomalyTotalToday();
        List<Map<String, Object>> vadTypeCountsToday = screenMapper.selectVadAnomalyTypeCountsToday();
        Long vadTotal = screenMapper.selectVadAnomalyTotal();
        Long strangerCount = screenMapper.selectTrackletStrangerCount();
        Long reidCount = screenMapper.selectReidMatchCount();
        Long llmCount = screenMapper.selectLlmReportCount();

        Long chatCount = 0L;
        try {
            chatCount = screenMapper.selectChatCount();
        } catch (Exception ignored) {
        }

        long fight = 0L;
        long fire = 0L;
        long fall = 0L;
        if (vadTypeCountsToday != null) {
            for (Map<String, Object> row : vadTypeCountsToday) {
                if (row == null) {
                    continue;
                }
                Object typeObj = row.get("type");
                Object cntObj = row.get("count");
                String type = typeObj == null ? null : String.valueOf(typeObj);
                long cnt = 0L;
                if (cntObj instanceof Number) {
                    cnt = ((Number) cntObj).longValue();
                } else if (cntObj != null) {
                    try {
                        cnt = Long.parseLong(String.valueOf(cntObj));
                    } catch (NumberFormatException ignored) {
                    }
                }
                if ("fight".equalsIgnoreCase(type)) {
                    fight = cnt;
                } else if ("fire".equalsIgnoreCase(type)) {
                    fire = cnt;
                } else if ("fall".equalsIgnoreCase(type)) {
                    fall = cnt;
                }
            }
        }

        long stranger = strangerCount == null ? 0L : strangerCount;
        long vadAnomalyTotal = vadTotalToday == null ? 0L : vadTotalToday;
        long anomalyTotal = vadAnomalyTotal + stranger;

        List<Map<String, Object>> items = new ArrayList<>();
        items.add(buildCountItem("fight", fight));
        items.add(buildCountItem("fire", fire));
        items.add(buildCountItem("fall", fall));
        items.add(buildCountItem("stranger", stranger));

        Map<String, Object> anomaly = new HashMap<>();
        anomaly.put("total", anomalyTotal);
        anomaly.put("items", items);

        long aiCount = ((vadTotal == null ? 0L : vadTotal) + stranger)
                + (reidCount == null ? 0L : reidCount)
                + (llmCount == null ? 0L : llmCount);

        aiCount = aiCount + (chatCount == null ? 0L : chatCount);

        List<Map<String, Object>> recent = screenMapper.selectRecentAlarms();
        if (recent == null) {
            recent = new ArrayList<>();
        }

        for (Map<String, Object> row : recent) {
            if (row == null) {
                continue;
            }
            normalizeAlarmRow(row);
        }

        Map<String, Object> out = new HashMap<>();
        out.put("ai_count", aiCount);
        out.put("anomaly", anomaly);
        out.put("recent_alarms", recent);
        return out;
    }

    @Override
    public Map<String, Object> normalizeAlarmRow(Map<String, Object> row) {
        if (row == null) {
            return null;
        }
        String playUrl = buildMtxPlayUrl(row);
        if (playUrl != null) {
            row.put("record_url", playUrl);

            Object th = row.get("thumbnail");
            String thStr = th == null ? null : String.valueOf(th);
            if (thStr == null || thStr.trim().isEmpty()) {
                row.put("thumbnail", playUrl);
            }
        }

        row.remove("stream_id");
        row.remove("asset_start_ts");
        row.remove("duration_ms");
        row.remove("alarm_ts");
        return row;
    }

    @Override
    public String buildMtxPlayUrl(Map<String, Object> row) {
        if (row == null) {
            return null;
        }
        String streamId = row.get("stream_id") == null ? null : String.valueOf(row.get("stream_id")).trim();
        if (streamId == null || streamId.isEmpty()) {
            return null;
        }

        if (streamId.endsWith("_vad")) {
            streamId = streamId.substring(0, streamId.length() - "_vad".length());
        }

        Date alarmTs = null;
        Object ats = row.get("alarm_ts");
        if (ats instanceof Date) {
            alarmTs = (Date) ats;
        } else if (ats instanceof Timestamp) {
            alarmTs = new Date(((Timestamp) ats).getTime());
        }

        Date assetStartTs = null;
        Object st = row.get("asset_start_ts");
        if (st instanceof Date) {
            assetStartTs = (Date) st;
        } else if (st instanceof Timestamp) {
            assetStartTs = new Date(((Timestamp) st).getTime());
        }

        Long durationMs = null;
        Object dm = row.get("duration_ms");
        if (dm instanceof Number) {
            durationMs = ((Number) dm).longValue();
        } else if (dm != null) {
            try {
                durationMs = Long.parseLong(String.valueOf(dm));
            } catch (NumberFormatException ignored) {
            }
        }

        long maxClipMs = 10_000L;
        long minClipMs = 1000L;
        long startMs;
        long endMs;
        boolean clampedByAssetEnd = false;

        if (alarmTs != null) {
            startMs = alarmTs.getTime() - MTX_START_PREROLL_MS;
            if (assetStartTs != null) {
                long assetStartMs = assetStartTs.getTime();
                if (startMs < assetStartMs) {
                    startMs = assetStartMs;
                }
            }
            endMs = startMs + maxClipMs;

            if (assetStartTs != null && durationMs != null && durationMs > 0L) {
                long assetStartMs = assetStartTs.getTime();
                long assetEndMs = assetStartMs + durationMs;
                if (assetEndMs > assetStartMs && endMs > assetEndMs && assetEndMs > startMs) {
                    endMs = assetEndMs;
                    clampedByAssetEnd = true;
                }
            }
        } else {
            if (assetStartTs == null || durationMs == null || durationMs <= 0L) {
                return null;
            }

            long assetStartMs = assetStartTs.getTime();
            long assetEndMs = assetStartMs + durationMs;
            if (assetEndMs <= assetStartMs) {
                return null;
            }

            startMs = assetStartMs;
            endMs = assetEndMs;
        }

        if (endMs <= startMs) {
            return null;
        }

        long newDurationMs = endMs - startMs;
        if (alarmTs != null && clampedByAssetEnd && newDurationMs < minClipMs) {
            endMs = startMs + maxClipMs;
            newDurationMs = maxClipMs;
        }
        if (newDurationMs <= 0L) {
            return null;
        }

        String baseUrl = aiTaskProperties == null ? null : aiTaskProperties.getMtxBaseUrl();
        if (baseUrl != null) {
            baseUrl = baseUrl.trim();
        }
        if (baseUrl == null || baseUrl.isEmpty()) {
            String host = aiTaskProperties != null && aiTaskProperties.getPublicHost() != null && !aiTaskProperties.getPublicHost().trim().isEmpty()
                    ? aiTaskProperties.getPublicHost().trim()
                    : "192.168.108.238";

            int port = DEFAULT_MTX_HTTP_PORT;
            baseUrl = "http://" + host + ":" + port;
        }
        while (baseUrl.endsWith("/")) {
            baseUrl = baseUrl.substring(0, baseUrl.length() - 1);
        }

        String durationS = BigDecimal.valueOf(newDurationMs)
                .divide(BigDecimal.valueOf(1000L), 3, RoundingMode.HALF_UP)
                .stripTrailingZeros()
                .toPlainString();

        ZonedDateTime zdt = ZonedDateTime.ofInstant(new Date(startMs).toInstant(), ZoneId.systemDefault());
        String start = zdt.format(START_PARAM_FORMATTER);

        String pathEnc = urlEncode(streamId);
        String startEnc = urlEncode(start);

        return baseUrl + "/get?path=" + pathEnc
                + "&start=" + startEnc
                + "&duration=" + durationS;
    }

    private String urlEncode(String val) {
        if (val == null) {
            return "";
        }
        try {
            return URLEncoder.encode(val, StandardCharsets.UTF_8.name());
        } catch (java.io.UnsupportedEncodingException e) {
            throw new IllegalStateException(e);
        }
    }

    @Override
    public Map<String, Object> getPedestrianInitData() {
        Long vadTotal = screenMapper.selectVadAnomalyTotal();
        Long flowTotal = screenMapper.selectTodayFlowTotal();
        Long reidCount = screenMapper.selectReidMatchCount();
        Long llmCount = screenMapper.selectLlmReportCount();

        Long chatCount = 0L;
        try {
            chatCount = screenMapper.selectChatCount();
        } catch (Exception ignored) {
        }

        long totalToday = flowTotal == null ? 0L : flowTotal;
        long aiCount = (vadTotal == null ? 0L : vadTotal)
                + totalToday
                + (reidCount == null ? 0L : reidCount)
                + (llmCount == null ? 0L : llmCount)
                + (chatCount == null ? 0L : chatCount);

        ZoneId zoneId = ZoneId.systemDefault();
        ZonedDateTime now = ZonedDateTime.now(zoneId);
        ZonedDateTime endFloor = now.withSecond(0).withNano(0);
        int minuteMod = endFloor.getMinute() % 10;
        if (minuteMod != 0) {
            endFloor = endFloor.minusMinutes(minuteMod);
        }

        LocalDate today = endFloor.toLocalDate();
        ZonedDateTime dayStart = today.atStartOfDay(zoneId);
        ZonedDateTime startBucket = endFloor.minusHours(8);
        if (startBucket.isBefore(dayStart)) {
            startBucket = dayStart;
        }

        DateTimeFormatter hm = DateTimeFormatter.ofPattern("HH:mm");
        String startTimeStr = startBucket.format(hm);
        String endTimeStr = endFloor.format(hm);

        long bucketCount = Duration.between(startBucket, endFloor).toMinutes() / 10;
        List<Map<String, Object>> points = new ArrayList<>();
        if (bucketCount > 0) {
            Map<String, Object> params = new HashMap<>();
            params.put("startTs", Timestamp.valueOf(startBucket.toLocalDateTime()));
            params.put("endTs", Timestamp.valueOf(endFloor.toLocalDateTime()));
            List<Map<String, Object>> bucketRows = screenMapper.selectFlowCountsBy10Min(params);
            Map<String, Long> bucketMap = new HashMap<>();
            if (bucketRows != null) {
                for (Map<String, Object> r : bucketRows) {
                    if (r == null) {
                        continue;
                    }
                    Object t = r.get("time");
                    Object c = r.get("count");
                    if (t == null) {
                        continue;
                    }
                    long cv = 0L;
                    if (c instanceof Number) {
                        cv = ((Number) c).longValue();
                    } else if (c != null) {
                        try {
                            cv = Long.parseLong(String.valueOf(c));
                        } catch (NumberFormatException ignored) {
                        }
                    }
                    bucketMap.put(String.valueOf(t), cv);
                }
            }

            for (int i = 0; i < (int) bucketCount; i++) {
                ZonedDateTime t = startBucket.plusMinutes(10L * i);
                String label = t.format(hm);
                long cv = bucketMap.getOrDefault(label, 0L);
                Map<String, Object> p = new HashMap<>();
                p.put("time", label);
                p.put("count", cv);
                points.add(p);
            }
        }

        Map<String, Object> flow = new HashMap<>();
        flow.put("total_today", totalToday);
        flow.put("start_time", startTimeStr);
        flow.put("end_time", endTimeStr);
        flow.put("data_points", points);

        List<Map<String, Object>> identities = screenMapper.selectLatestIdentitiesToday();
        List<Map<String, Object>> identitiesOut = new ArrayList<>();
        if (identities != null) {
            for (Map<String, Object> row : identities) {
                if (row == null) {
                    continue;
                }
                Map<String, Object> copy = new HashMap<>(row);
                if (copy.containsKey("identity_type") && !copy.containsKey("identity")) {
                    copy.put("identity", copy.get("identity_type"));
                }
                copy.remove("identity_type");
                copy.remove("sort_ts");
                identitiesOut.add(copy);
            }
        }

        Map<String, Object> out = new HashMap<>();
        out.put("ai_count", aiCount);
        out.put("flow", flow);
        out.put("identities", identitiesOut);
        return out;
    }

    private Map<String, Object> buildCountItem(String type, long count) {
        Map<String, Object> item = new HashMap<>();
        item.put("type", type);
        item.put("count", count);
        return item;
    }
}
