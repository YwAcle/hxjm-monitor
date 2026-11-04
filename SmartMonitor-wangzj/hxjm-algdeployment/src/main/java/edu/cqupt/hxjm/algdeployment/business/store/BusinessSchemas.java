package edu.cqupt.hxjm.algdeployment.business.store;

import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.Collections;
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
            if (!matches(schema,value)) {
                throw BusinessException.invalid("数据不符合已声明schema");
            }
        } catch (BusinessException exception) { throw exception; }
        catch (RuntimeException exception) { throw BusinessException.invalid("schema校验失败"); }
    }
    /** Fastjson's inferred schemas omit some untyped applicators; enforce them explicitly. */
    private static boolean matches(Map<String,Object> schema,Object value) {
        Map<String,Object> base=new LinkedHashMap<>(schema);
        for(String keyword:Arrays.asList("const","allOf","anyOf","oneOf","not")){base.remove(keyword);}
        if(base.containsKey("properties")){
            Map<String,Object> properties=new LinkedHashMap<>();
            for(String name:BusinessValues.map(base.get("properties")).keySet()){properties.put(name,Collections.emptyMap());}
            base.put("properties",properties);
        }
        if(base.containsKey("items")){base.put("items",Collections.emptyMap());}
        if(base.get("additionalProperties") instanceof Map){base.put("additionalProperties",Collections.emptyMap());}
        if(!base.isEmpty()&&!JSONSchema.parseSchema(BusinessValues.json(base)).isValid(value)){return false;}
        if(schema.containsKey("const")&&!BusinessCanonical.canonical(schema.get("const")).equals(BusinessCanonical.canonical(value))){return false;}
        for(String keyword:Arrays.asList("allOf","anyOf","oneOf")){
            if(schema.containsKey(keyword)){
                int matched=0;List<Object> alternatives=BusinessValues.list(schema.get(keyword));
                for(Object alternative:alternatives){if(matches(BusinessValues.map(alternative),value)){matched++;}}
                if(("allOf".equals(keyword)&&matched!=alternatives.size())||("anyOf".equals(keyword)&&matched==0)||("oneOf".equals(keyword)&&matched!=1)){return false;}
            }
        }
        if(schema.containsKey("not")&&matches(BusinessValues.map(schema.get("not")),value)){return false;}
        if(value instanceof Map){
            Map<String,Object> object=BusinessValues.map(value);
            Map<String,Object> properties=schema.containsKey("properties")?BusinessValues.map(schema.get("properties")):Collections.emptyMap();
            for(Map.Entry<String,Object> entry:object.entrySet()){
                Object child=properties.get(entry.getKey());
                if(child==null&&schema.get("additionalProperties") instanceof Map){child=schema.get("additionalProperties");}
                if(child instanceof Map&&!matches(BusinessValues.map(child),entry.getValue())){return false;}
            }
        }
        if(value instanceof List&&schema.containsKey("items")){
            for(Object item:BusinessValues.list(value)){if(!matches(BusinessValues.map(schema.get("items")),item)){return false;}}
        }
        return true;
    }

}
