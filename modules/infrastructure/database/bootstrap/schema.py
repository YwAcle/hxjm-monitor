"""Ordered SQL migrations. SQL is the only authority for object definitions."""
import hashlib
import json
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent.parent / 'migrations'
HISTORY = 'hxjm_schema_history'


def migrations(database):
    items = []
    for directory in sorted(MIGRATIONS.iterdir()):
        if not directory.is_dir():
            continue
        path = directory / (database + '.sql')
        if path.exists():
            sql = path.read_text()
            items.append((directory.name, hashlib.sha256(sql.encode()).hexdigest(), sql))
    if not items:
        raise ValueError('No migrations for ' + database)
    return items


def rows(connection, database, sql, params=()):
    if database == 'mysql':
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()
    return connection.execute(sql, params).fetchall()


def tables(connection, database):
    condition = 'table_schema=DATABASE()' if database == 'mysql' else "table_schema='public'"
    return [row[0] for row in rows(connection, database,
        'SELECT table_name FROM information_schema.tables WHERE ' + condition + ' ORDER BY table_name')]


def fingerprint(connection, database):
    """No row data or sequence positions: detect actual structural drift."""
    if database == 'mysql':
        import re
        objects = [re.sub(r'AUTO_INCREMENT=\d+\s*', '', rows(connection, database,
                   'SHOW CREATE TABLE `' + table + '`')[0][1]) for table in tables(connection, database)]
    else:
        queries = [
            "SELECT c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,pg_get_expr(d.adbin,d.adrelid) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum WHERE n.nspname='public' AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum",
            "SELECT c.relname,k.conname,pg_get_constraintdef(k.oid) FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.relname,k.conname",
            "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY tablename,indexname",
            "SELECT extname,extversion FROM pg_extension ORDER BY extname",
        ]
        objects = [rows(connection, database, query) for query in queries]
    return hashlib.sha256(json.dumps(objects, default=str, ensure_ascii=False).encode()).hexdigest()


def history(connection, database):
    if HISTORY not in tables(connection, database):
        raise ValueError(database + ': unmanaged schema; explicitly rebuild an isolated development database')
    applied = rows(connection, database, 'SELECT version,checksum,structure_sha256 FROM ' + HISTORY + ' ORDER BY version')
    expected = migrations(database)
    if [(r[0], r[1]) for r in applied] != [(r[0], r[1]) for r in expected[:len(applied)]] or len(applied) > len(expected):
        raise ValueError(database + ': migration history/checksum mismatch')
    if not applied or fingerprint(connection, database) != applied[-1][2]:
        raise ValueError(database + ': schema drift or incomplete migration; no changes made')
    return applied


def apply_pending(connection, database, fresh=False):
    applied = [] if fresh else history(connection, database)
    for version, checksum, sql in migrations(database)[len(applied):]:
        if database == 'postgres':
            with connection.transaction():
                if fresh and not applied:
                    connection.execute('CREATE TABLE ' + HISTORY + '(version varchar(64) PRIMARY KEY,checksum char(64) NOT NULL,structure_sha256 char(64) NOT NULL,applied_at timestamptz NOT NULL DEFAULT now())')
                connection.execute(sql, prepare=False)
                connection.execute('INSERT INTO ' + HISTORY + '(version,checksum,structure_sha256) VALUES(%s,%s,%s)',
                                   (version, checksum, fingerprint(connection, database)))
        else:
            with connection.cursor() as cursor:
                if fresh and not applied:
                    cursor.execute('CREATE TABLE ' + HISTORY + '(version varchar(64) PRIMARY KEY,checksum char(64) NOT NULL,structure_sha256 char(64) NOT NULL,applied_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP)')
                cursor.execute(sql)
                while cursor.nextset():
                    pass
                cursor.execute('INSERT INTO ' + HISTORY + '(version,checksum,structure_sha256) VALUES(%s,%s,%s)',
                               (version, checksum, fingerprint(connection, database)))
            connection.commit()
        applied.append((version, checksum))


def check(connections):
    for database, connection in connections.items():
        applied = history(connection, database)
        if len(applied) != len(migrations(database)):
            raise ValueError(database + ': pending migrations; run upgrade')
        print(database + ': schema verified at ' + applied[-1][0])


def upgrade(connections):
    # Validate BOTH targets before modifying either database. DDL is not a distributed transaction.
    for database, connection in connections.items():
        history(connection, database)
    for database, connection in connections.items():
        apply_pending(connection, database)
    check(connections)
