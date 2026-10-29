package edu.cqupt.hxjm.algdeployment.business.security;

import java.util.Collections;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessSchemas;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

public final class BusinessSchemaCheck {
    public static void main(String[] args) {
        BusinessSchemas.validate(Collections.emptyMap(),values("anything",true));
        BusinessSchemas.validate(parse("{\"type\":\"object\",\"properties\":{\"score\":{\"type\":\"number\",\"minimum\":0,\"maximum\":1}},\"required\":[\"score\"],\"additionalProperties\":false}"),values("score",0.5));
        rejects(() -> BusinessSchemas.validate(parse("{\"type\":\"object\",\"required\":[\"id\"]}"),Collections.emptyMap()));
        rejects(() -> BusinessSchemas.validate(parse("{\"type\":\"object\",\"additionalProperties\":false}"),values("extra",true)));
        rejects(() -> BusinessSchemas.validate(parse("{\"type\":\"integer\",\"minimum\":0,\"maximum\":5}"),6));
        rejects(() -> BusinessSchemas.validate(parse("{\"type\":\"string\",\"enum\":[\"person\"]}"),"vehicle"));
        rejects(() -> BusinessSchemas.validate(parse("{\"const\":\"person\"}"),"vehicle"));
        rejects(() -> BusinessSchemas.validate(parse("{\"type\":\"array\",\"minItems\":1}"),Collections.emptyList()));
        rejects(() -> BusinessSchemas.validate(parse("{\"type\":\"array\",\"items\":{\"type\":\"integer\"}}"),Collections.singletonList("text")));
        rejects(() -> BusinessSchemas.validate(parse("{\"type\":\"array\",\"uniqueItems\":true}"),java.util.Arrays.asList(1,1)));
        rejects(() -> BusinessSchemas.validate(parse("{\"type\":\"number\",\"exclusiveMinimum\":0}"),0));
        rejects(() -> BusinessSchemas.validate(parse("{\"type\":\"number\",\"multipleOf\":2}"),3));
        rejects(() -> BusinessSchemas.validate(parse("{\"type\":\"string\",\"minLength\":2}"),"x"));
        rejects(() -> BusinessSchemas.validate(parse("{\"type\":\"string\",\"pattern\":\"^[a-z]+$\"}"),"1"));
        rejects(() -> BusinessSchemas.validate(parse("{\"type\":\"object\",\"minProperties\":1}"),Collections.emptyMap()));
        rejects(() -> BusinessSchemas.validate(parse("{\"allOf\":[{\"type\":\"string\"},{\"minLength\":2}]}"),"x"));
        rejects(() -> BusinessSchemas.check(parse("{\"$ref\":\"https://example.invalid/remote\"}")));
        rejects(() -> BusinessSchemas.check(parse("{\"type\":\"string\",\"format\":\"email\"}")));
        System.out.println("BusinessSchemaCheck passed");
    }
    private static void rejects(Runnable work) {
        try { work.run(); throw new AssertionError("Invalid schema/data accepted"); }
        catch (BusinessException expected) { }
    }
}
