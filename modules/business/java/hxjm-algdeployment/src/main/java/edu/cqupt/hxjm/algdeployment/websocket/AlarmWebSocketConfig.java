package edu.cqupt.hxjm.algdeployment.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
@EnableScheduling
public class AlarmWebSocketConfig implements WebSocketConfigurer {

    private final AlarmWebSocketHandler alarmWebSocketHandler;

    private final LlmReportWebSocketHandler llmReportWebSocketHandler;

    public AlarmWebSocketConfig(AlarmWebSocketHandler alarmWebSocketHandler,
                                LlmReportWebSocketHandler llmReportWebSocketHandler) {
        this.alarmWebSocketHandler = alarmWebSocketHandler;
        this.llmReportWebSocketHandler = llmReportWebSocketHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(alarmWebSocketHandler, "/ws/alarm", "/ws/pedestrian").setAllowedOrigins("*");
        registry.addHandler(llmReportWebSocketHandler, "/ws/llm-report").setAllowedOrigins("*");
    }
}
