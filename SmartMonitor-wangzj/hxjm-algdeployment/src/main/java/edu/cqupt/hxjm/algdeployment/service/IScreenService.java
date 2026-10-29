package edu.cqupt.hxjm.algdeployment.service;

import java.util.Map;

public interface IScreenService {

    Long getDeviceCount();

    Map<String, Object> getAlarmInitData();

    Map<String, Object> getPedestrianInitData();

    Map<String, Object> normalizeAlarmRow(Map<String, Object> row);

    String buildMtxPlayUrl(Map<String, Object> row);
}
