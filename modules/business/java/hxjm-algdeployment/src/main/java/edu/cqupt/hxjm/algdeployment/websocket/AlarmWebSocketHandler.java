//-- Active: 1766990771677@@192.168.108.238@5432@postgres
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
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class AlarmWebSocketHandler extends TextWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(AlarmWebSocketHandler.class);

    private final ScreenMapper screenMapper;
    private final IScreenService screenService;

    private final Set<WebSocketSession> alarmSessions = ConcurrentHashMap.newKeySet();
    private final Set<WebSocketSession> pedestrianSessions = ConcurrentHashMap.newKeySet();

    private volatile String lastAlarmKey;
    private volatile String lastIdentityKey;

    private volatile String lastStrangerKey;

    private volatile Long lastStrangerCount;

    private volatile String lastTrackletKey;
    private volatile String lastFlowUpdateTime;

    private volatile Long lastPedestrianTotalToday;
    private volatile Long lastPedestrianAiCount;

    @Value("${smartmonitor.ws.dailyReset.enabled:true}")
    private boolean dailyResetEnabled;

    public AlarmWebSocketHandler(ScreenMapper screenMapper, IScreenService screenService) {
        this.screenMapper = screenMapper;
        this.screenService = screenService;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        String path = session.getUri() == null ? null : session.getUri().getPath();
        boolean isPedestrian = path != null && path.endsWith("/ws/pedestrian");
        if (isPedestrian) {
            pedestrianSessions.add(session);
        } else {
            alarmSessions.add(session);
        }

        try {
            Map<String, Object> initData = isPedestrian
                    ? screenService.getPedestrianInitData()
                    : screenService.getAlarmInitData();

            if (isPedestrian && initData != null) {
                Object ai = initData.get("ai_count");
                if (ai instanceof Number) {
                    lastPedestrianAiCount = ((Number) ai).longValue();
                }

                Object flowObj = initData.get("flow");
                if (flowObj instanceof Map) {
                    Object total = ((Map<?, ?>) flowObj).get("total_today");
                    if (total instanceof Number) {
                        lastPedestrianTotalToday = ((Number) total).longValue();
                    }
                }
            }

            JSONObject payload = new JSONObject();
            payload.put("type", "init");
            payload.put("data", initData);
            sendTextSafely(session, payload.toJSONString(), isPedestrian ? pedestrianSessions : alarmSessions);
        } catch (Exception e) {
            JSONObject payload = new JSONObject();
            payload.put("type", "error");
            payload.put("message", "init_failed");
            sendTextSafely(session, payload.toJSONString(), isPedestrian ? pedestrianSessions : alarmSessions);
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
            Set<WebSocketSession> set = pedestrianSessions.contains(session)
                    ? pedestrianSessions
                    : (alarmSessions.contains(session) ? alarmSessions : null);
            sendTextSafely(session, pong.toJSONString(), set);
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) throws Exception {
        alarmSessions.remove(session);
        pedestrianSessions.remove(session);
    }

    public void broadcastNewAlarm(Map<String, Object> data) {
        JSONObject payload = new JSONObject();
        payload.put("type", "new_alarm");
        payload.put("data", data);
        String text = payload.toJSONString();
        for (WebSocketSession s : alarmSessions) {
            if (s == null || !s.isOpen()) {
                continue;
            }
            sendTextSafely(s, text, alarmSessions);
        }
    }

    public void broadcastNewIdentity(Map<String, Object> data) {
        JSONObject payload = new JSONObject();
        payload.put("type", "new_identity");
        payload.put("data", data);
        String text = payload.toJSONString();
        for (WebSocketSession s : pedestrianSessions) {
            if (s == null || !s.isOpen()) {
                continue;
            }
            sendTextSafely(s, text, pedestrianSessions);
        }
    }

    public void broadcastPedestrianMetrics(Map<String, Object> data) {
        JSONObject payload = new JSONObject();
        payload.put("type", "metrics");
        payload.put("data", data);
        String text = payload.toJSONString();
        for (WebSocketSession s : pedestrianSessions) {
            if (s == null || !s.isOpen()) {
                continue;
            }
            sendTextSafely(s, text, pedestrianSessions);
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

    @Scheduled(cron = "${smartmonitor.ws.dailyReset.cron:0 0 2 * * *}")
    public void dailyResetAndBroadcastInit() {
        if (!dailyResetEnabled) {
            return;
        }

        lastAlarmKey = null;
        lastStrangerKey = null;
        lastStrangerCount = null;
        lastIdentityKey = null;
        lastTrackletKey = null;
        lastFlowUpdateTime = null;
        lastPedestrianTotalToday = null;
        lastPedestrianAiCount = null;

        if (!alarmSessions.isEmpty()) {
            try {
                Map<String, Object> initData = screenService.getAlarmInitData();
                JSONObject payload = new JSONObject();
                payload.put("type", "init");
                payload.put("data", initData);
                String text = payload.toJSONString();
                for (WebSocketSession s : alarmSessions) {
                    if (s == null || !s.isOpen()) {
                        continue;
                    }
                    sendTextSafely(s, text, alarmSessions);
                }
            } catch (Exception e) {
                log.warn("ws/alarm daily reset init broadcast failed", e);
            }
        }

        if (!pedestrianSessions.isEmpty()) {
            try {
                Map<String, Object> initData = screenService.getPedestrianInitData();
                if (initData != null) {
                    Object ai = initData.get("ai_count");
                    if (ai instanceof Number) {
                        lastPedestrianAiCount = ((Number) ai).longValue();
                    }

                    Object flowObj = initData.get("flow");
                    if (flowObj instanceof Map) {
                        Object total = ((Map<?, ?>) flowObj).get("total_today");
                        if (total instanceof Number) {
                            lastPedestrianTotalToday = ((Number) total).longValue();
                        }
                    }
                }

                JSONObject payload = new JSONObject();
                payload.put("type", "init");
                payload.put("data", initData);
                String text = payload.toJSONString();
                for (WebSocketSession s : pedestrianSessions) {
                    if (s == null || !s.isOpen()) {
                        continue;
                    }
                    sendTextSafely(s, text, pedestrianSessions);
                }
            } catch (Exception e) {
                log.warn("ws/pedestrian daily reset init broadcast failed", e);
            }
        }
    }

    @Scheduled(fixedDelayString = "${smartmonitor.ws.alarm.pollDelayMs:2000}")
    public void pollAndBroadcastAlarm() {
        if (alarmSessions.isEmpty()) {
            return;
        }

        Long vadTotalToday;
        List<Map<String, Object>> vadTypeCountsToday;
        Long strangerCount;
        try {
            vadTotalToday = screenMapper.selectVadAnomalyTotalToday();
        } catch (Exception e) {
            throw new RuntimeException("ws/alarm selectVadAnomalyTotalToday failed", e);
        }
        try {
            vadTypeCountsToday = screenMapper.selectVadAnomalyTypeCountsToday();
        } catch (Exception e) {
            throw new RuntimeException("ws/alarm selectVadAnomalyTypeCountsToday failed", e);
        }
        try {
            strangerCount = screenMapper.selectTrackletStrangerCount();
        } catch (Exception e) {
            throw new RuntimeException("ws/alarm selectTrackletStrangerCount failed", e);
        }

        long strangerVal = strangerCount == null ? 0L : strangerCount;
        long vadTodayVal = vadTotalToday == null ? 0L : vadTotalToday;

        boolean hasNewStranger = lastStrangerCount == null || !Objects.equals(lastStrangerCount, strangerVal);
        if (hasNewStranger) {
            lastStrangerCount = strangerVal;
        }

        Map<String, Object> latest = null;
        String key = null;
        try {
            latest = screenMapper.selectLatestAlarm();
        } catch (Exception e) {
            throw new RuntimeException("ws/alarm selectLatestAlarm failed", e);
        }
        boolean hasLatestAlarm = latest != null && !latest.isEmpty();
        boolean hasNewAlarm = false;
        if (hasLatestAlarm) {
            screenService.normalizeAlarmRow(latest);
            Object id = latest.get("id");
            Object ts = latest.get("timestamp");
            key = String.valueOf(id) + "|" + String.valueOf(ts);
            hasNewAlarm = !Objects.equals(key, lastAlarmKey);
        }

        if (!hasNewAlarm && !hasNewStranger) {
            return;
        }
        if (hasNewAlarm) {
            lastAlarmKey = key;
        }

        Long vadTotal;
        Long reidCount;
        Long llmCount;
        Long chatCount;
        try {
            vadTotal = screenMapper.selectVadAnomalyTotal();
        } catch (Exception e) {
            throw new RuntimeException("ws/alarm selectVadAnomalyTotal failed", e);
        }
        try {
            reidCount = screenMapper.selectReidMatchCount();
        } catch (Exception e) {
            throw new RuntimeException("ws/alarm selectReidMatchCount failed", e);
        }
        try {
            llmCount = screenMapper.selectLlmReportCount();
        } catch (Exception e) {
            throw new RuntimeException("ws/alarm selectLlmReportCount failed", e);
        }
        try {
            chatCount = screenMapper.selectChatCount();
        } catch (Exception e) {
            log.warn("ws/alarm selectChatCount failed", e);
            chatCount = 0L;
        }

        long aiCount = (vadTotal == null ? 0L : vadTotal)
                + strangerVal
                + (reidCount == null ? 0L : reidCount)
                + (llmCount == null ? 0L : llmCount)
                + (chatCount == null ? 0L : chatCount);

        Map<String, Object> anomalyUpdate = new HashMap<>();
        anomalyUpdate.put("total", vadTodayVal + strangerVal);

        Map<String, Object> data = new HashMap<>();
        data.put("ai_count", aiCount);

        if (!hasNewAlarm) {
            anomalyUpdate.put("type", "stranger");
            anomalyUpdate.put("count", strangerVal);
            data.put("anomaly_update", anomalyUpdate);
            broadcastNewAlarm(data);
            return;
        }

        String eventType = latest.get("event_type_key") == null ? null : String.valueOf(latest.get("event_type_key"));
        long typeCount = 0L;
        if (eventType != null && vadTypeCountsToday != null) {
            for (Map<String, Object> row : vadTypeCountsToday) {
                if (row == null) {
                    continue;
                }
                Object t = row.get("type");
                if (t == null) {
                    continue;
                }
                if (!eventType.equalsIgnoreCase(String.valueOf(t))) {
                    continue;
                }
                Object c = row.get("count");
                if (c instanceof Number) {
                    typeCount = ((Number) c).longValue();
                } else if (c != null) {
                    try {
                        typeCount = Long.parseLong(String.valueOf(c));
                    } catch (NumberFormatException ignored) {
                    }
                }
                break;
            }
        }

        Map<String, Object> alarm = new HashMap<>();
        alarm.put("id", latest.get("id"));
        alarm.put("alarm_level", latest.get("alarm_level"));
        alarm.put("event_type_key", latest.get("event_type_key"));
        alarm.put("camera_id", latest.get("camera_id"));
        alarm.put("thumbnail", latest.get("thumbnail"));
        alarm.put("record_url", latest.get("record_url"));
        alarm.put("timestamp", latest.get("timestamp"));

        anomalyUpdate.put("type", eventType);
        anomalyUpdate.put("count", typeCount);

        data.put("alarm", alarm);
        data.put("anomaly_update", anomalyUpdate);
        broadcastNewAlarm(data);
    }

    @Scheduled(fixedDelayString = "${smartmonitor.ws.pedestrian.pollDelayMs:2000}")
    public void pollAndBroadcastPedestrian() {
        if (pedestrianSessions.isEmpty()) {
            return;
        }

        pollAndBroadcastPedestrianMetrics();
        pollAndBroadcastFlowUpdate();

        Map<String, Object> latest;
        try {
            latest = screenMapper.selectLatestIdentityToday();
        } catch (Exception e) {
            log.warn("ws/pedestrian selectLatestIdentityToday failed", e);
            return;
        }
        if (latest == null || latest.isEmpty()) {
            return;
        }

        Object id = latest.get("id");
        Object ts = latest.get("detected_time");
        String key = String.valueOf(id) + "|" + String.valueOf(ts);
        if (key.equals(lastIdentityKey)) {
            return;
        }
        lastIdentityKey = key;

        Object aiCount = lastPedestrianAiCount;
        Map<String, Object> identity = new HashMap<>(latest);
        if (identity.containsKey("identity_type") && !identity.containsKey("identity")) {
            identity.put("identity", identity.get("identity_type"));
        }
        identity.remove("identity_type");
        identity.remove("sort_ts");

        Map<String, Object> data = new HashMap<>();
        data.put("ai_count", aiCount);
        Long totalToday = lastPedestrianTotalToday;
        if (totalToday == null) {
            try {
                totalToday = screenMapper.selectTodayFlowTotal();
            } catch (Exception e) {
                log.warn("ws/pedestrian selectTodayFlowTotal failed", e);
                totalToday = 0L;
            }
        }
        data.put("total_today", totalToday);
        data.put("identity", identity);

        broadcastNewIdentity(data);
    }

    private void pollAndBroadcastPedestrianMetrics() {
        Map<String, Object> latest;
        try {
            latest = screenMapper.selectLatestTrackletToday();
        } catch (Exception e) {
            log.warn("ws/pedestrian selectLatestTrackletToday failed", e);
            return;
        }
        if (latest == null || latest.isEmpty()) {
            return;
        }

        String id = String.valueOf(latest.get("id"));
        String ts = String.valueOf(latest.get("start_time"));
        String key = id + "|" + ts;
        if (Objects.equals(key, lastTrackletKey)) {
            return;
        }
        lastTrackletKey = key;

        Long totalToday;
        Long vadTotal;
        Long reidCount;
        Long llmCount;
        Long chatCount;

        try {
            totalToday = screenMapper.selectTodayFlowTotal();
        } catch (Exception e) {
            log.warn("ws/pedestrian selectTodayFlowTotal failed", e);
            totalToday = 0L;
        }
        try {
            vadTotal = screenMapper.selectVadAnomalyTotal();
        } catch (Exception e) {
            log.warn("ws/pedestrian selectVadAnomalyTotal failed", e);
            vadTotal = 0L;
        }
        try {
            reidCount = screenMapper.selectReidMatchCount();
        } catch (Exception e) {
            log.warn("ws/pedestrian selectReidMatchCount failed", e);
            reidCount = 0L;
        }
        try {
            llmCount = screenMapper.selectLlmReportCount();
        } catch (Exception e) {
            log.warn("ws/pedestrian selectLlmReportCount failed", e);
            llmCount = 0L;
        }
        try {
            chatCount = screenMapper.selectChatCount();
        } catch (Exception e) {
            log.warn("ws/pedestrian selectChatCount failed", e);
            chatCount = 0L;
        }

        long totalTodayVal = totalToday == null ? 0L : totalToday;
        long aiCountVal = (vadTotal == null ? 0L : vadTotal)
                + totalTodayVal
                + (reidCount == null ? 0L : reidCount)
                + (llmCount == null ? 0L : llmCount)
                + (chatCount == null ? 0L : chatCount);

        lastPedestrianTotalToday = totalTodayVal;
        lastPedestrianAiCount = aiCountVal;

        Map<String, Object> out = new HashMap<>();
        out.put("total_today", totalTodayVal);
        out.put("ai_count", aiCountVal);
        broadcastPedestrianMetrics(out);
    }

    private void pollAndBroadcastFlowUpdate() {
        ZoneId zoneId = ZoneId.systemDefault();
        ZonedDateTime now = ZonedDateTime.now(zoneId);
        ZonedDateTime endFloor = now.withSecond(0).withNano(0);
        int minuteMod = endFloor.getMinute() % 10;
        if (minuteMod != 0) {
            return;
        }

        String label = endFloor.format(DateTimeFormatter.ofPattern("HH:mm"));
        if (Objects.equals(label, lastFlowUpdateTime)) {
            return;
        }
        lastFlowUpdateTime = label;

        ZonedDateTime start = endFloor.minusMinutes(10);
        Map<String, Object> params = new HashMap<>();
        params.put("startTs", Timestamp.valueOf(start.toLocalDateTime()));
        params.put("endTs", Timestamp.valueOf(endFloor.toLocalDateTime()));

        Long cnt;
        try {
            cnt = screenMapper.selectFlowCountBetween(params);
        } catch (Exception e) {
            log.warn("ws/pedestrian selectFlowCountBetween failed", e);
            cnt = 0L;
        }

        Long totalToday = lastPedestrianTotalToday;
        if (totalToday == null) {
            try {
                totalToday = screenMapper.selectTodayFlowTotal();
            } catch (Exception e) {
                totalToday = 0L;
            }
        }

        Map<String, Object> flowUpdate = new HashMap<>();
        flowUpdate.put("total_today", totalToday == null ? 0L : totalToday);
        flowUpdate.put("time", label);
        flowUpdate.put("count", cnt == null ? 0L : cnt);

        Map<String, Object> data = new HashMap<>();
        data.put("flow_update", flowUpdate);
        broadcastPedestrianMetrics(data);
    }
}
