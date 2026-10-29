package edu.cqupt.hxjm.algdeployment.service.impl;

import edu.cqupt.hxjm.algdeployment.domain.MediaAsset;
import edu.cqupt.hxjm.algdeployment.mapper.MediaAssetMapper;
import edu.cqupt.hxjm.algdeployment.service.IMediaAssetService;
import edu.cqupt.hxjm.common.config.AiTaskProperties;
import edu.cqupt.hxjm.common.constant.HttpStatus;
import edu.cqupt.hxjm.common.exception.ServiceException;
import edu.cqupt.hxjm.common.utils.StringUtils;
import edu.cqupt.hxjm.common.utils.uuid.IdUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Service
public class MediaAssetServiceImpl implements IMediaAssetService {

    private static final Pattern SEGMENT_TS_PATTERN = Pattern.compile("(\\d{4})-(\\d{2})-(\\d{2})_(\\d{2})-(\\d{2})-(\\d{2})-(\\d{3,6})");
    private static final DateTimeFormatter START_PARAM_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSSSSSXXX");

    @Autowired
    private MediaAssetMapper mediaAssetMapper;

    @Autowired
    private AiTaskProperties aiTaskProperties;

    @Override
    public Map<String, Object> createMediaAsset(String streamId, String segmentPath, Double durationS) {
        if (StringUtils.isEmpty(streamId)) {
            throw new ServiceException("stream_id 必填", HttpStatus.BAD_REQUEST);
        }
        if (StringUtils.isEmpty(segmentPath)) {
            throw new ServiceException("segment_path 必填", HttpStatus.BAD_REQUEST);
        }
        if (durationS == null || durationS <= 0) {
            throw new ServiceException("duration_s 必填且大于0", HttpStatus.BAD_REQUEST);
        }

        MediaAsset mediaAsset = new MediaAsset();
        mediaAsset.setId(IdUtils.fastUUID());
        mediaAsset.setStreamId(streamId);
        mediaAsset.setAssetType("segment");
        mediaAsset.setStartTs(parseStartTs(segmentPath));
        mediaAsset.setDurationMs(toDurationMs(durationS));
        mediaAsset.setOssKey(segmentPath);
        mediaAsset.setOssBucket(null);
        mediaAsset.setContentType("video/mp4");
        mediaAsset.setMeta(null);
        mediaAsset.setCreatedAt(new Date());

        mediaAsset.setPlayUrl(buildPlayUrl(mediaAsset));

        mediaAssetMapper.insertMediaAsset(mediaAsset);

        Map<String, Object> data = new HashMap<>();
        data.put("id", mediaAsset.getId());
        return data;
    }

    @Override
    public List<Map<String, Object>> listMediaAssets() {
        List<MediaAsset> list = mediaAssetMapper.selectLatestMediaAssets();
        List<Map<String, Object>> out = new ArrayList<>();
        for (MediaAsset a : list) {
            Map<String, Object> row = new HashMap<>();
            row.put("id", a.getId());
            row.put("stream_id", a.getStreamId());
            row.put("asset_type", a.getAssetType());
            row.put("start_ts", a.getStartTs());
            row.put("duration_ms", a.getDurationMs());
            row.put("oss_bucket", a.getOssBucket());
            row.put("oss_key", a.getOssKey());
            row.put("path", a.getOssKey());
            row.put("content_type", a.getContentType());
            row.put("meta", a.getMeta());
            row.put("created_at", a.getCreatedAt());
            row.put("play_url", a.getPlayUrl() == null ? buildPlayUrl(a) : a.getPlayUrl());
            out.add(row);
        }
        return out;
    }

    private String buildPlayUrl(MediaAsset a) {
        String host = aiTaskProperties != null && StringUtils.isNotEmpty(aiTaskProperties.getPublicHost())
                ? aiTaskProperties.getPublicHost()
                : "192.168.108.238";

        String duration = BigDecimal.valueOf(a.getDurationMs() == null ? 0L : a.getDurationMs())
                .divide(BigDecimal.valueOf(1000L), 3, RoundingMode.HALF_UP)
                .stripTrailingZeros()
                .toPlainString();

        ZonedDateTime zdt = a.getStartTs() == null
                ? ZonedDateTime.now(ZoneId.systemDefault())
                : ZonedDateTime.ofInstant(a.getStartTs().toInstant(), ZoneId.systemDefault());
        String start = zdt.format(START_PARAM_FORMATTER);

        String pathEnc = urlEncode(a.getStreamId());
        String startEnc = urlEncode(start);

        return "http://" + host + ":9996/get?duration=" + duration + "&path=" + pathEnc + "&start=" + startEnc;
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

    private Date parseStartTs(String segmentPath) {
        if (segmentPath == null) {
            return new Date();
        }
        Matcher m = SEGMENT_TS_PATTERN.matcher(segmentPath);
        if (!m.find()) {
            return new Date();
        }
        int year = Integer.parseInt(m.group(1));
        int month = Integer.parseInt(m.group(2));
        int day = Integer.parseInt(m.group(3));
        int hour = Integer.parseInt(m.group(4));
        int minute = Integer.parseInt(m.group(5));
        int second = Integer.parseInt(m.group(6));
        String frac = m.group(7);
        int nanos = parseFractionToNanos(frac);
        ZonedDateTime zdt = ZonedDateTime.of(year, month, day, hour, minute, second, nanos, ZoneId.systemDefault());
        return Date.from(zdt.toInstant());
    }

    private int parseFractionToNanos(String frac) {
        if (frac == null) {
            return 0;
        }
        String digits = frac;
        if (digits.length() > 9) {
            digits = digits.substring(0, 9);
        }
        while (digits.length() < 9) {
            digits = digits + "0";
        }
        return Integer.parseInt(digits);
    }

    private Long toDurationMs(Double durationS) {
        BigDecimal ms = BigDecimal.valueOf(durationS).multiply(BigDecimal.valueOf(1000L));
        return ms.setScale(0, RoundingMode.HALF_UP).longValue();
    }
}
