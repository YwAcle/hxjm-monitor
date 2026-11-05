package edu.cqupt.hxjm.algdeployment.business.security;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessCanonical;
import edu.cqupt.hxjm.algdeployment.business.store.BusinessValues;

public final class BusinessCanonicalCheck {
    public static void main(String[] args) throws Exception {
        if (args.length > 0 && "numbers".equals(args[0])) {
            BufferedReader input = new BufferedReader(new InputStreamReader(System.in, "UTF-8"));
            String line;
            while ((line = input.readLine()) != null) {
                System.out.println(BusinessCanonical.canonical(Double.valueOf(line)));
            }
            return;
        }
        String raw = "{\"numbers\":[333333333.33333329,1E30,4.50,2e-3,0.000000000000000000000000001],"
                + "\"string\":\"€$\\u000f\\nA'B\\\"\\\\\\\\\\\"/\",\"literals\":[null,true,false]}";
        String expected = "{\"literals\":[null,true,false],\"numbers\":[333333333.3333333,1e+30,4.5,0.002,1e-27],"
                + "\"string\":\"€$\\u000f\\nA'B\\\"\\\\\\\\\\\"/\"}";
        check(expected.equals(BusinessCanonical.canonical(BusinessValues.parse(raw))), "RFC 8785 section 3.2.2");
        String[] bits = {"0000000000000000", "8000000000000000", "0000000000000001", "8000000000000001",
                "7fefffffffffffff", "ffefffffffffffff", "4340000000000000", "4430000000000000",
                "44b52d02c7e14af5", "44b52d02c7e14af6", "44b52d02c7e14af7", "3eb0c6f7a0b5ed8d",
                "3eb0c6f7a0b5ed8c", "41b3de4355555553", "41b3de4355555554", "41b3de4355555555",
                "41b3de4355555556", "41b3de4355555557", "becbf647612f3696", "43143ff3c1cb0959"};
        String[] numbers = {"0", "0", "5e-324", "-5e-324", "1.7976931348623157e+308", "-1.7976931348623157e+308",
                "9007199254740992", "295147905179352830000", "9.999999999999997e+22", "1e+23",
                "1.0000000000000001e+23", "0.000001", "9.999999999999997e-7", "333333333.3333332",
                "333333333.33333325", "333333333.3333333", "333333333.3333334", "333333333.33333343",
                "-0.0000033333333333333333", "1424953923781206.2"};
        for (int index = 0; index < bits.length; index++) {
            String number = BusinessCanonical.canonical(Double.longBitsToDouble(Long.parseUnsignedLong(bits[index], 16)));
            check(numbers[index].equals(number), "RFC appendix B " + bits[index] + ": " + number);
        }
        Map<String, Object> keys = new LinkedHashMap<>();
        for (String key : Arrays.asList("€", "\r", "דּ", "1", "😀", "\u0080", "ö")) { keys.put(key, 1); }
        check("{\"\\r\":1,\"1\":1,\"\u0080\":1,\"ö\":1,\"€\":1,\"😀\":1,\"דּ\":1}".equals(BusinessCanonical.canonical(keys)), "UTF-16 property order");
        rejects(() -> BusinessCanonical.canonical("\uD800"));
        rejects(() -> BusinessCanonical.canonical(Double.NaN));
        rejects(() -> BusinessValues.parse("{\"x\":1,\"x\":2}"));
        rejects(() -> BusinessValues.parse("{} {}"));
        rejects(() -> BusinessValues.parse("[]"));
        rejects(() -> BusinessValues.parse("{\"id\":9007199254740993}"));
        System.out.println("BusinessCanonicalCheck passed");
    }

    private static void rejects(Runnable operation) {
        try { operation.run(); throw new AssertionError("Invalid canonical input accepted"); }
        catch (BusinessException expected) { }
    }
    private static void check(boolean condition, String message) { if (!condition) { throw new AssertionError(message); } }
}
