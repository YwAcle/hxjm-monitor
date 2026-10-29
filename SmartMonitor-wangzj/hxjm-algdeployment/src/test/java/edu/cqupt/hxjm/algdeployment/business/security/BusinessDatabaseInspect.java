package edu.cqupt.hxjm.algdeployment.business.security;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.logging.Level;
import java.util.logging.Logger;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

/** Read-only metadata inspection of the configured business database; credentials arrive on stdin. */
public final class BusinessDatabaseInspect {
    private static final List<String> TABLES = Arrays.asList("camera", "camera_stream", "media_asset", "tracklet",
            "stream_session", "capability_definition", "capability_instance", "result_type", "business_task",
            "task_attempt", "request_deduplication", "outbox_event", "tracking_context", "result_set",
            "result_selection", "input_frame", "analysis_frame", "detection_observation", "algorithm_result",
            "processing_coverage", "asset_reference");
    private static final List<String> LEGACY = Arrays.asList("camera", "camera_stream", "media_asset", "tracklet");

    public static void main(String[] args) {
        try {
            if (args.length != 0) { throw new IllegalArgumentException(); }
            Logger.getLogger("org.postgresql").setLevel(Level.OFF);
            ByteArrayOutputStream input = new ByteArrayOutputStream();
            byte[] block = new byte[1024];
            for (int count; (count = System.in.read(block)) != -1;) {
                if (input.size() + count > 32768) { throw new IllegalArgumentException(); }
                input.write(block, 0, count);
            }
            Map<String, Object> config = parse(new String(input.toByteArray(), StandardCharsets.UTF_8));
            fields(config, "url", "username", "password");
            String url = text(config, "url", 8192);
            if (!url.startsWith("jdbc:postgresql://")) { throw new IllegalArgumentException(); }
            Properties properties = new Properties();
            properties.setProperty("user", text(config, "username", 256));
            properties.setProperty("password", text(config, "password", 8192));
            properties.setProperty("connectTimeout", "10");
            properties.setProperty("socketTimeout", "45");
            properties.setProperty("ApplicationName", "hxjm-yh-readonly-inspection");
            Class.forName("org.postgresql.Driver");
            try (Connection connection = DriverManager.getConnection(url, properties)) {
                connection.setReadOnly(true);
                connection.setTransactionIsolation(Connection.TRANSACTION_REPEATABLE_READ);
                connection.setAutoCommit(false);
                try { System.out.println(json(inspect(connection))); }
                finally { connection.rollback(); }
            }
        } catch (Exception failure) {
            String state = failure instanceof SQLException ? ((SQLException) failure).getSQLState() : null;
            System.out.println(json(values("error", "Read-only inspection failed", "sql_state", state)));
            System.exit(1);
        }
    }

    private static Map<String, Object> inspect(Connection connection) throws SQLException {
        Map<String, Object> database = rows(connection, "SELECT current_database() AS database, current_schema() AS schema, "
                + "current_setting('server_version') AS server_version, "
                + "current_setting('transaction_read_only') AS transaction_read_only").get(0);
        if (!"on".equals(database.get("transaction_read_only"))) { throw new SQLException("Read-only transaction required"); }
        List<Object> tables = new ArrayList<>();
        for (String table : TABLES) {
            List<Map<String, Object>> relation = rows(connection, "SELECT c.relkind::text AS relation_kind "
                    + "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                    + "WHERE n.nspname='public' AND c.relname=? AND c.relkind IN ('r','p')", table);
            Map<String, Object> item = values("schema", "public", "table", table, "exists", !relation.isEmpty());
            tables.add(item);
            if (relation.isEmpty()) { continue; }
            item.put("relation_kind", relation.get(0).get("relation_kind"));
            List<Map<String, Object>> columns = rows(connection,
                    "SELECT a.attnum AS ordinal, a.attname AS name, pg_catalog.format_type(a.atttypid,a.atttypmod) AS type, "
                    + "NOT a.attnotnull AS nullable, pg_catalog.pg_get_expr(d.adbin,d.adrelid) AS default_expression, "
                    + "pg_catalog.col_description(a.attrelid,a.attnum) AS comment "
                    + "FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid "
                    + "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                    + "LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
                    + "WHERE n.nspname='public' AND c.relname=? AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum", table);
            item.put("columns", columns);
            item.put("constraints", rows(connection,
                    "SELECT con.conname AS name, con.contype::text AS type, con.convalidated AS validated, "
                    + "pg_catalog.pg_get_constraintdef(con.oid,true) AS definition "
                    + "FROM pg_catalog.pg_constraint con JOIN pg_catalog.pg_class c ON c.oid=con.conrelid "
                    + "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                    + "WHERE n.nspname='public' AND c.relname=? ORDER BY con.conname", table));
            item.put("indexes", rows(connection,
                    "SELECT ix.relname AS name, i.indisunique AS is_unique, i.indisprimary AS is_primary, "
                    + "i.indisvalid AS is_valid, pg_catalog.pg_get_indexdef(ix.oid) AS definition "
                    + "FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indrelid "
                    + "JOIN pg_catalog.pg_class ix ON ix.oid=i.indexrelid "
                    + "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                    + "WHERE n.nspname='public' AND c.relname=? ORDER BY ix.relname", table));
            if (LEGACY.contains(table)) {
                item.put("statistics", rows(connection, "SELECT count(*) AS row_count, "
                        + "pg_catalog.pg_table_size('public.\"" + table + "\"'::regclass) AS table_bytes, "
                        + "pg_catalog.pg_total_relation_size('public.\"" + table + "\"'::regclass) AS total_bytes "
                        + "FROM public.\"" + table + "\"").get(0));
            }
            if ("camera".equals(table) || "camera_stream".equals(table)) {
                List<String> selected = new ArrayList<>();
                for (String allowed : Arrays.asList("id", "camera_id", "stream_name", "task_type", "tasktype")) {
                    for (Map<String, Object> column : columns) {
                        if (allowed.equals(column.get("name"))) { selected.add("\"" + allowed + "\"::text AS \"" + allowed + "\""); }
                    }
                }
                if (!selected.isEmpty()) {
                    item.put("source_directory", rows(connection, "SELECT " + String.join(",", selected)
                            + " FROM public.\"" + table + "\" ORDER BY 1"));
                }
            }
        }
        return values("database", database, "tables", tables);
    }

    private static List<Map<String, Object>> rows(Connection connection, String sql, String... arguments) throws SQLException {
        if (!sql.startsWith("SELECT ")) { throw new IllegalArgumentException("Only SELECT is allowed"); }
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setQueryTimeout(30);
            for (int index = 0; index < arguments.length; index++) { statement.setString(index + 1, arguments[index]); }
            try (ResultSet results = statement.executeQuery()) {
                List<Map<String, Object>> rows = new ArrayList<>();
                ResultSetMetaData metadata = results.getMetaData();
                while (results.next()) {
                    Map<String, Object> row = values();
                    for (int index = 1; index <= metadata.getColumnCount(); index++) {
                        Object value = results.getObject(index);
                        row.put(metadata.getColumnLabel(index), value instanceof java.util.UUID ? value.toString() : value);
                    }
                    rows.add(row);
                }
                return rows;
            }
        }
    }
}
