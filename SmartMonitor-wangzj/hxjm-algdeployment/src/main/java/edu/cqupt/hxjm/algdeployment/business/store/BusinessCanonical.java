package edu.cqupt.hxjm.algdeployment.business.store;

import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessException;

/** RFC 8785 JSON canonicalization for parsed JSON values (IEEE 754 numbers). */
public final class BusinessCanonical {
    private BusinessCanonical() { }

    public static String canonical(Object value) {
        StringBuilder output = new StringBuilder();
        append(value, output);
        return output.toString();
    }

    public static String digest(Object value) {
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256").digest(canonical(value).getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder(64);
            for (byte item : bytes) { result.append(String.format("%02x", item & 255)); }
            return result.toString();
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static void append(Object value, StringBuilder output) {
        if (value == null) { output.append("null"); }
        else if (value instanceof String) { string((String) value, output); }
        else if (value instanceof Boolean) { output.append(value); }
        else if (value instanceof Number) { output.append(number(((Number) value).doubleValue())); }
        else if (value instanceof List) {
            output.append('[');
            boolean first = true;
            for (Object item : (List<?>) value) {
                if (!first) { output.append(','); }
                first = false;
                append(item, output);
            }
            output.append(']');
        } else if (value instanceof Map) {
            Map<?, ?> values = (Map<?, ?>) value;
            List<String> keys = new ArrayList<>();
            for (Object key : values.keySet()) {
                if (!(key instanceof String)) { throw BusinessException.invalid("JSON对象键须为字符串"); }
                keys.add((String) key);
            }
            keys.sort(String::compareTo);
            output.append('{');
            boolean first = true;
            for (String key : keys) {
                if (!first) { output.append(','); }
                first = false;
                string(key, output);
                output.append(':');
                append(values.get(key), output);
            }
            output.append('}');
        } else { throw BusinessException.invalid("规范请求只能包含JSON类型"); }
    }

    private static void string(String value, StringBuilder output) {
        output.append('"');
        for (int i = 0; i < value.length(); i++) {
            char character = value.charAt(i);
            if (Character.isHighSurrogate(character)) {
                if (i + 1 == value.length() || !Character.isLowSurrogate(value.charAt(i + 1))) {
                    throw BusinessException.invalid("JSON文本含无效Unicode代理项");
                }
                output.append(character).append(value.charAt(++i));
            } else if (Character.isLowSurrogate(character)) {
                throw BusinessException.invalid("JSON文本含无效Unicode代理项");
            } else {
                switch (character) {
                    case '"': output.append("\\\""); break;
                    case '\\': output.append("\\\\"); break;
                    case '\b': output.append("\\b"); break;
                    case '\f': output.append("\\f"); break;
                    case '\n': output.append("\\n"); break;
                    case '\r': output.append("\\r"); break;
                    case '\t': output.append("\\t"); break;
                    default:
                        if (character < 32) { output.append(String.format("\\u%04x", (int) character)); }
                        else { output.append(character); }
                }
            }
        }
        output.append('"');
    }

    private static String number(double value) {
        if (!Double.isFinite(value)) { throw BusinessException.invalid("JSON数值须为有限IEEE754数值"); }
        if (value == 0) { return "0"; }
        boolean negative = value < 0;
        double positive = Math.abs(value);
        BigDecimal exact = new BigDecimal(positive);
        BigDecimal selected = null;
        int exponent = exact.precision() - exact.scale() - 1;
        // Find the shortest decimal that rounds back to this binary64; ties use an even significand.
        for (int precision = 1; precision <= 17 && selected == null; precision++) {
            BigDecimal nearest = exact.round(new MathContext(precision, RoundingMode.HALF_EVEN));
            BigDecimal step = BigDecimal.ONE.scaleByPowerOfTen(exponent - precision + 1);
            for (int offset = -1; offset <= 1; offset++) {
                BigDecimal candidate = nearest.add(step.multiply(BigDecimal.valueOf(offset))).stripTrailingZeros();
                if (candidate.signum() <= 0 || candidate.precision() > precision
                        || Double.doubleToLongBits(candidate.doubleValue()) != Double.doubleToLongBits(positive)) { continue; }
                if (selected == null || candidate.subtract(exact).abs().compareTo(selected.subtract(exact).abs()) < 0
                        || (candidate.subtract(exact).abs().compareTo(selected.subtract(exact).abs()) == 0
                        && !candidate.unscaledValue().testBit(0))) { selected = candidate; }
            }
        }
        if (selected == null) { throw new IllegalStateException("No binary64 decimal representation"); }
        int power = selected.precision() - selected.scale() - 1;
        String text;
        if (power >= -6 && power < 21) { text = selected.toPlainString(); }
        else {
            String digits = selected.unscaledValue().toString();
            text = digits.substring(0, 1) + (digits.length() > 1 ? "." + digits.substring(1) : "")
                    + "e" + (power >= 0 ? "+" : "") + power;
        }
        return negative ? "-" + text : text;
    }
}
