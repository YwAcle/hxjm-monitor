package edu.cqupt.hxjm.algdeployment.service;

import javax.servlet.http.HttpServletRequest;

public interface IAiTaskRunService {
    String startAndGetUrl(String task, int cameraId, HttpServletRequest request);
}
