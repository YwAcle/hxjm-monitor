package edu.cqupt.hxjm.interfaceservice.domain;

import com.alibaba.fastjson2.JSONObject;

import java.util.List;

public class ReID {
    private List<String> machineIds; // 设备ID集合
    private List<String> urlList; // 设备rts流集合
    private int method; // 查找方式的代码
    private String voiceText; // 语音文本
    private List<JSONObject> imgList; // 图像数组

    // Getters and Setters
    public List<String> getMachineIds() {
        return machineIds;
    }

    public void setMachineIds(List<String> machineIds) {
        this.machineIds = machineIds;
    }

    public List<String> getUrlList() {
        return urlList;
    }

    public void setUrlList(List<String> urlList) {
        this.urlList = urlList;
    }

    public int getMethod() {
        return method;
    }

    public void setMethod(int method) {
        this.method = method;
    }

    public String getVoiceText() {
        return voiceText;
    }

    public void setVoiceText(String voiceText) {
        this.voiceText = voiceText;
    }

    // Getter for imgList
    public List<JSONObject> getImgList() {
        return imgList;
    }

    // Setter for imgList
    public void setImgList(List<JSONObject> imgList) {
        this.imgList = imgList;
    }

}

