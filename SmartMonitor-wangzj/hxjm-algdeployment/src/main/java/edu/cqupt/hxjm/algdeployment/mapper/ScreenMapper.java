package edu.cqupt.hxjm.algdeployment.mapper;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface ScreenMapper {

    Long selectDeviceCount();

    Long selectVadAnomalyTotal();

    List<Map<String, Object>> selectVadAnomalyTypeCounts();

    Long selectVadAnomalyTotalToday();

    List<Map<String, Object>> selectVadAnomalyTypeCountsToday();

    Long selectTrackletStrangerCount();

    Map<String, Object> selectLatestStrangerTrackletToday();

    Long selectReidMatchCount();

    Long selectLlmReportCount();

    Long selectChatCount();

    List<Map<String, Object>> selectRecentAlarms();

    Map<String, Object> selectLatestAlarm();

    Long selectTodayFlowTotal();

    Map<String, Object> selectLatestTrackletToday();

    List<Map<String, Object>> selectFlowCountsBy10Min(Map<String, Object> params);

    Long selectFlowCountBetween(Map<String, Object> params);

    List<Map<String, Object>> selectLatestIdentitiesToday();

    Map<String, Object> selectLatestIdentityToday();

    List<Map<String, Object>> selectLatestLlmReports(Map<String, Object> params);

    List<Map<String, Object>> selectLlmReportsAfter(Map<String, Object> params);
}
