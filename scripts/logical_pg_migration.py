"""Guarded logical copy from PostgreSQL 18 source to migrated PG17 target.

Dry-run is the default. This utility is preparation tooling, not an application
management command. It never writes to the source. See the migration runbook
before using --execute; do not use production URLs for an initial rehearsal.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from collections import defaultdict, deque

import psycopg2
from psycopg2 import sql

APP_SCHEMA = "public"
TARGET_RESET_CONFIRMATION = "RESET TARGET APPLICATION TABLES"
FRESH_TARGET_ALLOWLIST = {
    "django_migrations",
    "django_content_type",
    "auth_permission",
}


class MigrationSafetyError(RuntimeError):
    pass


def topological_table_order(tables, foreign_keys):
    """Return parent-before-child order; fail closed on FK cycles."""
    table_set = set(tables)
    children = defaultdict(set)
    indegree = {table: 0 for table in table_set}
    for child, parent in foreign_keys:
        if child not in table_set or parent not in table_set or child == parent:
            if child == parent:
                raise MigrationSafetyError(f"Self-referencing FK cycle in {child}")
            continue
        if child not in children[parent]:
            children[parent].add(child)
            indegree[child] += 1
    ready = deque(sorted(name for name, degree in indegree.items() if degree == 0))
    ordered = []
    while ready:
        parent = ready.popleft()
        ordered.append(parent)
        for child in sorted(children[parent]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if len(ordered) != len(table_set):
        cyclic = sorted(name for name, degree in indegree.items() if degree)
        raise MigrationSafetyError("Foreign-key cycle detected: " + ", ".join(cyclic))
    return ordered


def compare_table_columns(source_columns, target_columns, table_name):
    """Require identical ordered column metadata before COPY."""
    if source_columns != target_columns:
        raise MigrationSafetyError(f"Column structure mismatch in {table_name}")


def _tables(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = %s AND table_type = 'BASE TABLE' "
            "ORDER BY table_name",
            (APP_SCHEMA,),
        )
        return [row[0] for row in cursor.fetchall()]


def _columns(connection, table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name, ordinal_position, udt_schema, udt_name, "
            "is_nullable, character_maximum_length, numeric_precision, "
            "numeric_scale, datetime_precision "
            "FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s "
            "ORDER BY ordinal_position",
            (APP_SCHEMA, table),
        )
        return cursor.fetchall()


def _foreign_keys(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT child.relname, parent.relname "
            "FROM pg_constraint c "
            "JOIN pg_class child ON child.oid = c.conrelid "
            "JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace "
            "JOIN pg_class parent ON parent.oid = c.confrelid "
            "JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace "
            "WHERE c.contype = 'f' AND child_ns.nspname = %s "
            "AND parent_ns.nspname = %s",
            (APP_SCHEMA, APP_SCHEMA),
        )
        return cursor.fetchall()


def _foreign_key_structures(connection):
    """Return ordered, complete FK metadata for constraints touching public."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.conname, child_ns.nspname, child.relname, "
            "array_agg(child_col.attname ORDER BY child_key.ord), "
            "parent_ns.nspname, parent.relname, "
            "array_agg(parent_col.attname ORDER BY parent_key.ord), "
            "c.confupdtype, c.confdeltype, c.confmatchtype, "
            "c.condeferrable, c.condeferred "
            "FROM pg_constraint c "
            "JOIN pg_class child ON child.oid = c.conrelid "
            "JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace "
            "JOIN pg_class parent ON parent.oid = c.confrelid "
            "JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace "
            "JOIN LATERAL unnest(c.conkey) WITH ORDINALITY child_key(attnum, ord) ON TRUE "
            "JOIN pg_attribute child_col ON child_col.attrelid = child.oid AND child_col.attnum = child_key.attnum "
            "JOIN LATERAL unnest(c.confkey) WITH ORDINALITY parent_key(attnum, ord) ON parent_key.ord = child_key.ord "
            "JOIN pg_attribute parent_col ON parent_col.attrelid = parent.oid AND parent_col.attnum = parent_key.attnum "
            "WHERE c.contype = 'f' AND (child_ns.nspname = %s OR parent_ns.nspname = %s) "
            "GROUP BY c.conname, child_ns.nspname, child.relname, parent_ns.nspname, "
            "parent.relname, c.confupdtype, c.confdeltype, c.confmatchtype, "
            "c.condeferrable, c.condeferred "
            "ORDER BY child_ns.nspname, child.relname, c.conname",
            (APP_SCHEMA, APP_SCHEMA),
        )
        return cursor.fetchall()


def compare_foreign_keys(source_constraints, target_constraints):
    if set(source_constraints) != set(target_constraints):
        raise MigrationSafetyError("Source/target foreign-key structures differ.")


def external_references(foreign_key_rows, app_schema, app_tables):
    table_set = set(app_tables)
    return [
        row for row in foreign_key_rows
        if row[4] == app_schema and row[5] in table_set
        and (row[1] != app_schema or row[2] not in table_set)
    ]


def require_no_external_references(foreign_key_rows, app_schema, app_tables):
    external = external_references(foreign_key_rows, app_schema, app_tables)
    if external:
        details = ", ".join(
            f"{row[1]}.{row[2]}.{row[0]} -> {row[4]}.{row[5]}" for row in external
        )
        raise MigrationSafetyError("External target FK references block reset: " + details)


def _key_constraint_structures(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT n.nspname, t.relname, c.conname, c.contype, "
            "pg_get_constraintdef(c.oid), c.condeferrable, c.condeferred "
            "FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_namespace n ON n.oid = t.relnamespace "
            "WHERE n.nspname = %s AND c.contype IN ('p', 'u') "
            "ORDER BY n.nspname, t.relname, c.conname",
            (APP_SCHEMA,),
        )
        return cursor.fetchall()


def target_reset_statements(schema_name, tables, parent_first_order):
    """Build qualified child-first DELETE statements for verified tables only."""
    if set(tables) != set(parent_first_order):
        raise MigrationSafetyError("Reset list does not match verified table set.")
    return [
        sql.SQL("DELETE FROM {}.{}").format(
            sql.Identifier(schema_name), sql.Identifier(table)
        )
        for table in reversed(parent_first_order)
    ]


def _migration_rows(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT app, name FROM public.django_migrations ORDER BY app, name"
        )
        return cursor.fetchall()


def _version(connection):
    with connection.cursor() as cursor:
        cursor.execute("SHOW server_version_num")
        number = int(cursor.fetchone()[0])
    return number // 10000


def _counts(connection, tables):
    result = {}
    with connection.cursor() as cursor:
        for table in tables:
            cursor.execute(
                sql.SQL("SELECT count(*) FROM {}.{}").format(
                    sql.Identifier(APP_SCHEMA), sql.Identifier(table)
                )
            )
            result[table] = cursor.fetchone()[0]
    return result


def _target_identity(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database(), inet_server_addr()::text, inet_server_port()")
        return cursor.fetchone()


def sequence_restart_sql(schema_name, sequence_name, next_value):
    """Compose transactional sequence reset SQL from catalog-derived names."""
    return sql.SQL("ALTER SEQUENCE {}.{} RESTART WITH {}").format(
        sql.Identifier(schema_name),
        sql.Identifier(sequence_name),
        sql.Literal(max(1, int(next_value))),
    )


def _target_freshness_check(target_conn, target_tables):
    counts = _counts(target_conn, target_tables)
    unexpected = {
        table: count
        for table, count in counts.items()
        if count and table not in FRESH_TARGET_ALLOWLIST
    }
    if unexpected:
        raise MigrationSafetyError(
            "Target contains rows outside the allowed Django migration-generated "
            "tables; refusing reset."
        )
    return counts


def _sequence_reset_statements(target_conn, tables):
    statements = []
    with target_conn.cursor() as cursor:
        for table in tables:
            cursor.execute(
                "SELECT a.attname, pg_get_serial_sequence(%s, a.attname) "
                "FROM pg_attribute a "
                "JOIN pg_class t ON t.oid = a.attrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = %s AND t.relname = %s "
                "AND a.attnum > 0 AND NOT a.attisdropped",
                (f'{APP_SCHEMA}."{table}"', APP_SCHEMA, table),
            )
            for column, sequence_name in cursor.fetchall():
                if sequence_name:
                    statements.append((table, column, sequence_name))
    return statements


def _reset_sequences(target_conn, sequence_rows):
    with target_conn.cursor() as cursor:
        for table, column, sequence_name in sequence_rows:
            cursor.execute(
                sql.SQL("SELECT COALESCE(MAX({}), 0) FROM {}.{}").format(
                    sql.Identifier(column), sql.Identifier(APP_SCHEMA), sql.Identifier(table)
                )
            )
            maximum = cursor.fetchone()[0]
            # ALTER SEQUENCE RESTART is transactional (unlike setval).
            sequence_schema, sequence_local_name = sequence_name.split(".", 1)
            cursor.execute(sequence_restart_sql(
                sequence_schema, sequence_local_name, maximum + 1
            ))


def _copy_table(source_conn, target_conn, table, columns):
    identifiers = sql.SQL(", ").join(sql.Identifier(row[0]) for row in columns)
    source_copy = sql.SQL("COPY {}.{} ({}) TO STDOUT").format(
        sql.Identifier(APP_SCHEMA), sql.Identifier(table), identifiers
    )
    target_copy = sql.SQL("COPY {}.{} ({}) FROM STDIN").format(
        sql.Identifier(APP_SCHEMA), sql.Identifier(table), identifiers
    )
    # Per-table secure temporary spool allows native COPY text escaping without
    # constructing INSERTs or holding a whole database/table in memory.
    try:
        def copy_out(spool):
            with source_conn.cursor() as source_cursor:
                source_cursor.copy_expert(source_copy.as_string(source_conn), spool)

        def copy_in(spool):
            with target_conn.cursor() as target_cursor:
                target_cursor.copy_expert(target_copy.as_string(target_conn), spool)

        copy_via_temporary_spool(copy_out, copy_in)
    except Exception as exc:
        raise MigrationSafetyError(
            f"COPY failed for table {table} ({type(exc).__name__}); row details withheld."
        ) from None


def copy_via_temporary_spool(copy_out, copy_in):
    """TemporaryFile closes and removes its OS-managed spool on all exits."""
    with tempfile.TemporaryFile(mode="w+b") as spool:
        copy_out(spool)
        spool.seek(0)
        copy_in(spool)


def inspect(source_conn, target_conn, expected_target_database=None):
    source_conn.set_session(readonly=True, autocommit=False)
    source_version = _version(source_conn)
    target_version = _version(target_conn)
    if (source_version, target_version) != (18, 17):
        raise MigrationSafetyError(
            f"Expected cross-major PostgreSQL 18 to 17; observed {source_version} to {target_version}."
        )
    source_tables = _tables(source_conn)
    target_tables = _tables(target_conn)
    if not source_tables or set(source_tables) != set(target_tables):
        raise MigrationSafetyError("Source/target application table inventories differ.")
    if "django_migrations" not in source_tables:
        raise MigrationSafetyError("django_migrations is missing from source schema.")
    for table in source_tables:
        compare_table_columns(_columns(source_conn, table), _columns(target_conn, table), table)
    fk_rows = _foreign_keys(source_conn)
    source_fk_structures = _foreign_key_structures(source_conn)
    target_fk_structures = _foreign_key_structures(target_conn)
    compare_foreign_keys(source_fk_structures, target_fk_structures)
    if _key_constraint_structures(source_conn) != _key_constraint_structures(target_conn):
        raise MigrationSafetyError("Source/target primary or unique constraints differ.")
    require_no_external_references(target_fk_structures, APP_SCHEMA, target_tables)
    if _migration_rows(source_conn) != _migration_rows(target_conn):
        raise MigrationSafetyError("Source and migrated target Django migration histories differ.")
    order = topological_table_order(source_tables, fk_rows)
    source_counts = _counts(source_conn, source_tables)
    target_counts = _target_freshness_check(target_conn, target_tables)
    source_identity = _target_identity(source_conn)
    target_identity = _target_identity(target_conn)
    if source_identity == target_identity:
        raise MigrationSafetyError("Source and target appear to be the same database endpoint.")
    if expected_target_database and target_identity[0] != expected_target_database:
        raise MigrationSafetyError("Target database name did not match explicit expectation.")
    if source_identity[0] == target_identity[0] and source_identity[1:] == target_identity[1:]:
        raise MigrationSafetyError("Source and target resolve to the same PostgreSQL endpoint.")
    return {
        "source_version": source_version,
        "target_version": target_version,
        "tables": source_tables,
        "order": order,
        "reset_statements": target_reset_statements(APP_SCHEMA, source_tables, order),
        "source_counts": source_counts,
        "target_counts": target_counts,
        "sequence_rows": _sequence_reset_statements(target_conn, target_tables),
    }


def copy_data(source_conn, target_conn, report):
    target_conn.autocommit = False
    try:
        with target_conn:
            with target_conn.cursor() as cursor:
                for statement in report["reset_statements"]:
                    cursor.execute(statement)
            for table in report["order"]:
                _copy_table(source_conn, target_conn, table, _columns(source_conn, table))
            _reset_sequences(target_conn, report["sequence_rows"])
            target_counts = _counts(target_conn, report["tables"])
            if target_counts != report["source_counts"]:
                raise MigrationSafetyError("Post-copy row-count validation failed.")
    except Exception:
        target_conn.rollback()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Inspect only; this is the default.")
    mode.add_argument("--execute", action="store_true", help="Reset and logically copy TARGET only.")
    parser.add_argument("--confirm-target-reset", action="store_true")
    parser.add_argument("--expected-target-database", help="Exact database name expected for this disposable rehearsal.")
    args = parser.parse_args(argv)
    if args.execute and not (args.confirm_target_reset and args.expected_target_database):
        parser.error("--execute requires --confirm-target-reset and --expected-target-database.")
    source_url = os.environ.get("SOURCE_DATABASE_URL")
    target_url = os.environ.get("TARGET_DATABASE_URL")
    if not source_url or not target_url:
        parser.error("Set SOURCE_DATABASE_URL and TARGET_DATABASE_URL in the environment.")
    source_conn = target_conn = None
    try:
        source_conn = psycopg2.connect(source_url)
        source_conn.set_session(readonly=True, autocommit=False)
        target_conn = psycopg2.connect(target_url)
        report = inspect(source_conn, target_conn, args.expected_target_database)
        print(f"Cross-major logical migration: PostgreSQL {report['source_version']} -> {report['target_version']}")
        print("schema=public (must be confirmed before use)")
        print("table | source_count | target_count | target_fresh_allowlist")
        for table in report["tables"]:
            allowed = table in FRESH_TARGET_ALLOWLIST
            print(f"{table} | {report['source_counts'][table]} | {report['target_counts'][table]} | {allowed}")
        print("FK copy order: " + " -> ".join(report["order"]))
        print(f"owned sequences to reset: {len(report['sequence_rows'])}")
        if args.execute:
            copy_data(source_conn, target_conn, report)
            print("Copy and row-count validation: PASS")
        else:
            print("DRY RUN: no target data mutation performed")
        return 0
    except MigrationSafetyError as exc:
        # Safety errors contain only structural metadata (schema/table names,
        # versions, or counts); database driver errors remain redacted below.
        print(f"Migration safety check failed: {exc}", file=sys.stderr)
        return 2
    except psycopg2.Error as exc:
        print(f"Migration safety check failed ({type(exc).__name__}); details withheld.", file=sys.stderr)
        return 2
    finally:
        if source_conn is not None:
            source_conn.close()
        if target_conn is not None:
            target_conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
