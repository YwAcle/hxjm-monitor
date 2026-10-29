package edu.cqupt.hxjm.algdeployment.websocket;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import edu.cqupt.hxjm.algdeployment.mapper.ScreenMapper;
import edu.cqupt.hxjm.algdeployment.service.IScreenService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class LlmReportWebSocketHandler extends TextWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(LlmReportWebSocketHandler.class);

    private final ScreenMapper screenMapper;

    private final IScreenService screenService;

    private final Set<WebSocketSession> sessions = ConcurrentHashMap.newKeySet();

    private final Set<WebSocketSession> initializingSessions = ConcurrentHashMap.newKeySet();

    @Value("${smartmonitor.ws.llmReport.initLimit:20}")
    private int initLimit;

    @Value("${smartmonitor.ws.llmReport.initLookbackSeconds:3600}")
    private int initLookbackSeconds;

    private static final int INIT_LIMIT = 5;

    @Value("${smartmonitor.ws.llmReport.pushLimit:200}")
    private int pushLimit;

    @Value("${smartmonitor.ws.dailyReset.enabled:true}")
    private boolean dailyResetEnabled;

    private static final DateTimeFormatter EVENT_TIME_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.SSS x");

    private volatile Timestamp lastCreatedAt;
    private volatile String lastId;

    public LlmReportWebSocketHandler(ScreenMapper screenMapper, IScreenService screenService) {
        this.screenMapper = screenMapper;
        this.screenService = screenService;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        initializingSessions.add(session);
        sessions.add(session);

        try {
            List<Map<String, Object>> rows;
            try {
                Map<String, Object> params = new HashMap<>();
                params.put("limit", INIT_LIMIT);
                params.put("lookbackSeconds", initLookbackSeconds);
                rows = screenMapper.selectLatestLlmReports(params);
            } catch (Exception e) {
                log.error("ws/llm-report init_failed: selectLatestLlmReports query error", e);
                JSONObject payload = new JSONObject();
                payload.put("type", "error");
                payload.put("message", "init_failed");
                sendTextSafely(session, payload.toJSONString(), sessions);
                return;
            }

            if (rows == null) {
                rows = new ArrayList<>();
            }

            if (!rows.isEmpty()) {
                updateCursorFromRow(rows.get(0));
                Collections.reverse(rows);
            } else if (lastCreatedAt == null || lastId == null) {
                lastCreatedAt = new Timestamp(0L);
                lastId = "00000000-0000-0000-0000-000000000000";
            }

            JSONObject payload = new JSONObject();
            payload.put("type", "llm_report");
            payload.put("op", "init");
            payload.put("data", buildData(rows));
            sendTextSafely(session, payload.toJSONString(), sessions);
        } finally {
            initializingSessions.remove(session);
        }
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) throws Exception {
        JSONObject obj;
        try {
            obj = JSON.parseObject(message.getPayload());
        } catch (Exception e) {
            return;
        }
        String type = obj.getString("type");
        if ("ping".equalsIgnoreCase(type)) {
            JSONObject pong = new JSONObject();
            pong.put("type", "pong");
            sendTextSafely(session, pong.toJSONString(), sessions);
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) throws Exception {
        sessions.remove(session);
        initializingSessions.remove(session);
    }

    @Scheduled(cron = "${smartmonitor.ws.dailyReset.cron:0 0 2 * * *}")
    public void dailyResetAndBroadcastInit() {
        if (!dailyResetEnabled) {
            return;
        }

        lastCreatedAt = null;
        lastId = null;

        if (sessions.isEmpty()) {
            return;
        }

        List<Map<String, Object>> rows;
        try {
            Map<String, Object> params = new HashMap<>();
            params.put("limit", INIT_LIMIT);
            params.put("lookbackSeconds", initLookbackSeconds);
            rows = screenMapper.selectLatestLlmReports(params);
        } catch (Exception e) {
            log.warn("ws/llm-report daily reset init query failed", e);
            return;
        }

        if (rows == null) {
            rows = new ArrayList<>();
        }

        if (!rows.isEmpty()) {
            updateCursorFromRow(rows.get(0));
            Collections.reverse(rows);
        } else {
            lastCreatedAt = new Timestamp(0L);
            lastId = "00000000-0000-0000-0000-000000000000";
        }

        JSONObject payload = new JSONObject();
        payload.put("type", "llm_report");
        payload.put("op", "init");
        payload.put("data", buildData(rows));
        String text = payload.toJSONString();

        for (WebSocketSession s : sessions) {
            if (s == null || !s.isOpen()) {
                continue;
            }
            if (initializingSessions.contains(s)) {
                continue;
            }
            sendTextSafely(s, text, sessions);
        }
    }

    @Scheduled(fixedDelayString = "${smartmonitor.ws.llmReport.pollDelayMs:3000}")
    public void pollAndBroadcast() {
        if (sessions.isEmpty()) {
            return;
        }
        if (lastCreatedAt == null || lastId == null) {
            return;
        }

        List<Map<String, Object>> rows;
        try {
            Map<String, Object> params = new HashMap<>();
            params.put("createdAt", lastCreatedAt);
            params.put("id", lastId);
            params.put("limit", pushLimit);
            rows = screenMapper.selectLlmReportsAfter(params);
        } catch (Exception e) {
            throw new RuntimeException("ws/llm-report selectLlmReportsAfter failed", e);
        }

        if (rows == null || rows.isEmpty()) {
            return;
        }

        updateCursorFromRow(rows.get(rows.size() - 1));

        JSONObject payload = new JSONObject();
        payload.put("type", "llm_report");
        payload.put("op", "append");
        payload.put("data", buildData(rows));
        String text = payload.toJSONString();

        for (WebSocketSession s : sessions) {
            if (s == null || !s.isOpen()) {
                continue;
            }
            if (initializingSessions.contains(s)) {
                continue;
            }
            sendTextSafely(s, text, sessions);
        }
    }

    private Map<String, Object> buildData(List<Map<String, Object>> rows) {
        List<Map<String, Object>> items = new ArrayList<>();
        if (rows != null) {
            for (Map<String, Object> row : rows) {
                if (row == null || row.isEmpty()) {
                    continue;
                }
                Map<String, Object> item = new HashMap<>();
                item.put("id", row.get("id"));
                item.put("episode_id", row.get("episode_id"));
                item.put("vad_id", row.get("vad_id"));
                item.put("prompt_type", row.get("prompt_type"));
                item.put("report_text", row.get("report_text"));
                item.put("created_at", toIsoInstantString(row.get("created_at")));

                String promptType = row.get("prompt_type") == null ? null : String.valueOf(row.get("prompt_type")).trim();
                if ("reid".equalsIgnoreCase(promptType)) {
                    Object reidFrameEndB64 = row.get("reid_frame_end_base64");
                    String reidFrameEndB64Str = reidFrameEndB64 == null ? null : String.valueOf(reidFrameEndB64).trim();

                    Object episodeMeta = row.get("episode_meta");
                    JSONObject meta = null;
                    if (episodeMeta != null && !String.valueOf(episodeMeta).trim().isEmpty()) {
                        try {
                            meta = JSON.parseObject(String.valueOf(episodeMeta));
                        } catch (Exception ignored) {
                        }
                    }

                    if (reidFrameEndB64Str != null && !reidFrameEndB64Str.isEmpty()) {
                        item.put("thumbnail", "data:image/jpeg;base64," + reidFrameEndB64Str);
                    } else {
                        String personImage = meta == null ? null : meta.getString("person_image");
                        if (personImage != null) {
                            personImage = personImage.trim();
                        }
                        if (personImage != null && !personImage.isEmpty()) {
                            if (personImage.startsWith("data:image")) {
                                item.put("thumbnail", personImage);
                            } else {
                                item.put("thumbnail", "data:image/jpeg;base64," + personImage);
                            }
                        } else {
                            item.put("thumbnail", null);
                        }
                    }

                    String playUrl = screenService == null ? null : screenService.buildMtxPlayUrl(row);
                    if (playUrl == null || playUrl.trim().isEmpty()) {
                        String streamId = meta == null ? null : meta.getString("stream_id");
                        String startTsStr = meta == null ? null : meta.getString("start_ts");
                        Date startTs = null;
                        if (startTsStr != null) {
                            startTsStr = startTsStr.trim();
                        }
                        if (startTsStr != null && !startTsStr.isEmpty()) {
                            try {
                                LocalDateTime ldt = LocalDateTime.parse(startTsStr);
                                ZonedDateTime zdt = ldt.atZone(ZoneId.systemDefault());
                                startTs = Date.from(zdt.toInstant());
                            } catch (Exception ignored) {
                            }
                        }

                        if (screenService != null && streamId != null && !streamId.trim().isEmpty() && startTs != null) {
                            Map<String, Object> metaRow = new HashMap<>();
                            metaRow.put("stream_id", streamId);
                            metaRow.put("asset_start_ts", startTs);
                            metaRow.put("duration_ms", 10_000L);
                            metaRow.put("alarm_ts", startTs);
                            playUrl = screenService.buildMtxPlayUrl(metaRow);
                        }
                    }

                    if (playUrl == null || playUrl.trim().isEmpty()) {
                        Object recordUrlObj = row.get("record_url");
                        playUrl = recordUrlObj == null ? null : String.valueOf(recordUrlObj);
                    }
                    item.put("record_url", playUrl);
                } else {
                    Object frameB64 = row.get("frame_vad_base64");
                    if (frameB64 != null && !String.valueOf(frameB64).trim().isEmpty()) {
                        item.put("thumbnail", "data:image/jpeg;base64," + String.valueOf(frameB64));
                    } else {
                        item.put("thumbnail", null);
                    }

                    String playUrl = screenService == null ? null : screenService.buildMtxPlayUrl(row);
                    if (playUrl == null || playUrl.trim().isEmpty()) {
                        Object recordUrlObj = row.get("record_url");
                        playUrl = recordUrlObj == null ? null : String.valueOf(recordUrlObj);
                    }
                    item.put("record_url", playUrl);
                }

                Object reportJson = row.get("report_json");
                if (reportJson != null) {
                    try {
                        item.put("report_json", JSON.parse(String.valueOf(reportJson)));
                    } catch (Exception e) {
                        item.put("report_json", reportJson);
                    }
                } else {
                    item.put("report_json", null);
                }

                items.add(item);
            }
        }

        Map<String, Object> cursor = new HashMap<>();
        cursor.put("id", lastId);
        cursor.put("created_at", lastCreatedAt == null ? null : lastCreatedAt.getTime());

        Map<String, Object> data = new HashMap<>();
        data.put("items", items);
        data.put("cursor", cursor);
        return data;
    }

    private String toIsoInstantString(Object tsObj) {
        if (tsObj == null) {
            return null;
        }
        try {
            if (tsObj instanceof Timestamp) {
                return ((Timestamp) tsObj).toInstant().toString();
            }
            if (tsObj instanceof Date) {
                return Instant.ofEpochMilli(((Date) tsObj).getTime()).toString();
            }
        } catch (Exception ignored) {
        }
        return String.valueOf(tsObj);
    }

    private void updateCursorFromRow(Map<String, Object> row) {
        if (row == null) {
            return;
        }
        Object idObj = row.get("id");
        Object tsObj = row.get("sort_ts");
        Timestamp ts = null;
        if (tsObj instanceof Timestamp) {
            ts = (Timestamp) tsObj;
        } else if (tsObj instanceof java.util.Date) {
            ts = new Timestamp(((java.util.Date) tsObj).getTime());
        }

        if (idObj == null || ts == null) {
            return;
        }

        String idStr = String.valueOf(idObj);
        UUID candidateId;
        try {
            candidateId = UUID.fromString(idStr);
        } catch (Exception e) {
            return;
        }

        Timestamp currentTs = lastCreatedAt;
        UUID currentId = null;
        if (lastId != null) {
            try {
                currentId = UUID.fromString(lastId);
            } catch (Exception ignored) {
            }
        }

        boolean shouldAdvance = false;
        if (currentTs == null) {
            shouldAdvance = true;
        } else {
            int tsCmp = ts.compareTo(currentTs);
            if (tsCmp > 0) {
                shouldAdvance = true;
            } else if (tsCmp == 0) {
                if (currentId == null) {
                    shouldAdvance = true;
                } else if (candidateId.compareTo(currentId) > 0) {
                    shouldAdvance = true;
                }
            }
        }

        if (shouldAdvance) {
            lastId = idStr;
            lastCreatedAt = ts;
        }
    }

    private void sendTextSafely(WebSocketSession session, String text, Set<WebSocketSession> sessionSet) {
        if (session == null || !session.isOpen()) {
            return;
        }
        synchronized (session) {
            if (!session.isOpen()) {
                return;
            }
            try {
                session.sendMessage(new TextMessage(text));
            } catch (Exception e) {
                log.warn("ws sendText failed, sessionId={}", session.getId(), e);
                if (sessionSet != null) {
                    sessionSet.remove(session);
                }
            }
        }
    }
}
