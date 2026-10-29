package edu.cqupt.hxjm.interfaceservice.domain;

public class StreamRequest {

    private String streamUrl;

    // 无参构造函数
    public StreamRequest() {
    }

    // 构造函数
    public StreamRequest(String streamUrl) {
        this.streamUrl = streamUrl;
    }

    // Getter 和 Setter
    public String getStreamUrl() {
        return streamUrl;
    }

    public void setStreamUrl(String streamUrl) {
        this.streamUrl = streamUrl;
    }
}
