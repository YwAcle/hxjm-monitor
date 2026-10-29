package edu.cqupt.hxjm.algdeployment.business.store;

import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import com.alibaba.fastjson2.schema.JSONSchema;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;

/** Supported local schema keywords are explicit; references never fetch remote documents. */
public final class BusinessSchemas {
    private static final Set<String> KEYWORDS = new HashSet<>(Arrays.asList("type", "title", "description", "default", "enum", "const",
            "properties", "required", "additionalProperties", "items", "minItems", "maxItems", "uniqueItems",
            "minLength", "maxLength", "pattern", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
            "multipleOf", "minProperties", "maxProperties", "allOf", "anyOf", "oneOf", "not"));

    private BusinessSchemas() { }

    public static void check(Map<String, Object> schema) {
        for (String keyword : schema.keySet()) {
            if (!KEYWORDS.contains(keyword)) { throw BusinessException.invalid("当前不支持schema关键字: " + keyword); }
        }
        if (schema.containsKey("properties")) {
            for (Object value : BusinessValues.map(schema.get("properties")).values()) { check(BusinessValues.map(value)); }
        }
        for (String nested : Arrays.asList("items", "not")) {
            if (schema.containsKey(nested)) { check(BusinessValues.map(schema.get(nested))); }
        }
        if (schema.get("additionalProperties") instanceof Map) { check(BusinessValues.map(schema.get("additionalProperties"))); }
        for (String nested : Arrays.asList("allOf", "anyOf", "oneOf")) {
            if (schema.containsKey(nested)) {
                for (Object value : BusinessValues.list(schema.get(nested))) { check(BusinessValues.map(value)); }
            }
        }
        try { JSONSchema.parseSchema(BusinessValues.json(schema)); }
        catch (RuntimeException exception) { throw BusinessException.invalid("schema结构无效"); }
    }

    public static void validate(Map<String, Object> schema, Object value) {
        check(schema);
        if (schema.isEmpty()) { return; }
        try {
            if (!JSONSchema.parseSchema(BusinessValues.json(schema)).isValid(value)) {
                throw BusinessException.invalid("数据不符合已声明schema");
            }
        } catch (BusinessException exception) { throw exception; }
        catch (RuntimeException exception) { throw BusinessException.invalid("schema校验失败"); }
    }
}
