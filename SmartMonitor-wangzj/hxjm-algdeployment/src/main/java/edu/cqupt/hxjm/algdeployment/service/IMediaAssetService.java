package edu.cqupt.hxjm.algdeployment.service;

import java.util.List;
import java.util.Map;

public interface IMediaAssetService {
    Map<String, Object> createMediaAsset(String streamId, String segmentPath, Double durationS);

    List<Map<String, Object>> listMediaAssets();
}
