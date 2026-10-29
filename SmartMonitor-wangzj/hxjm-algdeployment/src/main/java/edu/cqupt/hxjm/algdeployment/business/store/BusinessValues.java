package edu.cqupt.hxjm.algdeployment.business.store;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeParseException;
import java.time.format.DateTimeFormatter;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;

public final class BusinessValues {
    private static final ObjectMapper JSON = new ObjectMapper()
            .enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION)
            .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
            .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
            .enable(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS);

    private BusinessValues() { }

    public static Map<String, Object> parse(String raw) {
        try {
            Map<String, Object> value = JSON.readValue(raw, new TypeReference<Map<String, Object>>() { });
            if (value == null) { throw BusinessException.invalid("请求须为JSON对象"); }
            normalizeNumbers(value);
            BusinessCanonical.canonical(value);
            return value;
        } catch (BusinessException exception) { throw exception; }
        catch (Exception exception) { throw BusinessException.invalid("JSON格式不正确或含重复字段"); }
    }

    private static Object normalizeNumbers(Object value) {
        if (value instanceof Map) {
            Map<String, Object> object = map(value);
            for (Map.Entry<String, Object> item : object.entrySet()) { item.setValue(normalizeNumbers(item.getValue())); }
        } else if (value instanceof List) {
            List<Object> array = list(value);
            for (int index = 0; index < array.size(); index++) { array.set(index, normalizeNumbers(array.get(index))); }
        } else if (value instanceof BigInteger) {
            if (((BigInteger) value).abs().compareTo(BigInteger.valueOf(9007199254740991L)) > 0) {
                throw BusinessException.invalid("JSON整数不得超过IEEE754安全范围；大整数标识使用字符串");
            }
        } else if (value instanceof BigDecimal) {
            double number = ((BigDecimal) value).doubleValue();
            if (!Double.isFinite(number)) { throw BusinessException.invalid("JSON数值超出IEEE754范围"); }
            return number;
        }
        return value;
    }

    public static String json(Object value) {
        try { return JSON.writeValueAsString(value); }
        catch (Exception exception) { throw BusinessException.invalid("无法序列化JSON数据"); }
    }

    public static void fields(Map<String, Object> value, String... allowed) {
        for (String key : value.keySet()) {
            if (!Arrays.asList(allowed).contains(key)) { throw BusinessException.invalid("不支持字段: " + key); }
        }
    }

    public static Object required(Map<String, Object> value, String key) {
        if (!value.containsKey(key) || value.get(key) == null) { throw BusinessException.invalid("缺少字段: " + key); }
        return value.get(key);
    }

    public static String text(Map<String, Object> value, String key) { return text(value, key, 128); }

    public static String text(Map<String, Object> value, String key, int maximum) {
        Object item = required(value, key);
        if (!(item instanceof String) || ((String) item).trim().isEmpty() || ((String) item).length() > maximum
                || ((String) item).chars().anyMatch(character -> character < 32 || character == 127)) {
            throw BusinessException.invalid(key + "须为非空文本且长度不超过" + maximum);
        }
        return (String) item;
    }

    public static String uuid(Map<String, Object> value, String key) { return uuid(text(value, key, 36), key); }

    public static String uuid(Object value, String key) {
        try {
            if (!(value instanceof String) || ((String) value).length() != 36
                    || !UUID.fromString((String) value).toString().equals(value)
                    || UUID.fromString((String) value).equals(new UUID(0, 0))) {
                throw BusinessException.invalid(key + "须为规范UUID");
            }
            return (String) value;
        } catch (IllegalArgumentException exception) { throw BusinessException.invalid(key + "须为规范UUID"); }
    }

    public static OffsetDateTime time(Map<String, Object> value, String key) {
        try {
            String raw=text(value,key,40);
            if(!raw.matches("[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})")) {
                throw BusinessException.invalid(key+"须为含时区且最多六位小数秒的RFC3339时间");
            }
            OffsetDateTime result = OffsetDateTime.parse(raw).withOffsetSameInstant(ZoneOffset.UTC);
            if(result.getYear()<1||result.getYear()>9999){throw BusinessException.invalid(key+"年份须为1至9999");}
            if (result.getNano() % 1000 != 0) { throw BusinessException.invalid(key + "最多保留六位小数秒"); }
            return result;
        } catch (DateTimeParseException exception) { throw BusinessException.invalid(key + "须含时区日期时间"); }
    }

    public static String iso(OffsetDateTime value) { return DateTimeFormatter.ISO_INSTANT.format(value.toInstant()); }

    public static long integer(Map<String, Object> value, String key, long minimum, long maximum) {
        Object item = required(value, key);
        if (!(item instanceof Number)) { throw BusinessException.invalid(key + "须为整数"); }
        try {
            long result = new BigDecimal(item.toString()).longValueExact();
            if (result < minimum || result > maximum || Math.abs(result) > 9007199254740991L) { throw BusinessException.invalid(key + "超出允许范围"); }
            return result;
        } catch (ArithmeticException exception) { throw BusinessException.invalid(key + "须为范围内整数"); }
    }

    @SuppressWarnings("unchecked")
    public static Map<String, Object> map(Object value) {
        if (!(value instanceof Map)) { throw BusinessException.invalid("字段须为JSON对象"); }
        return (Map<String, Object>) value;
    }

    @SuppressWarnings("unchecked")
    public static List<Object> list(Object value) {
        if (!(value instanceof List)) { throw BusinessException.invalid("字段须为JSON数组"); }
        return (List<Object>) value;
    }

    public static Map<String, Object> values(Object... pairs) {
        Map<String, Object> value = new LinkedHashMap<>();
        for (int index = 0; index < pairs.length; index += 2) { value.put((String) pairs[index], pairs[index + 1]); }
        return value;
    }
}
