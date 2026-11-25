import os
import unittest
from contextlib import ExitStack
from unittest import mock

try:
    from scripts import logical_pg_migration as migration
except ImportError:
    import logical_pg_migration as migration


class LogicalMigrationSafetyTests(unittest.TestCase):
    def _inspection_mocks(
        self,
        stack,
        *,
        source_identity=("source", "10.0.0.1", 5432),
        target_identity=("target", "10.0.0.2", 5432),
        source_keys=(),
        target_keys=(),
        column_results=None,
    ):
        stack.enter_context(mock.patch.object(migration, "_version", side_effect=[18, 17]))
        stack.enter_context(mock.patch.object(migration, "_tables", return_value=["django_migrations"]))
        stack.enter_context(mock.patch.object(
            migration, "_columns", side_effect=column_results or [("id",), ("id",)]
        ))
        stack.enter_context(mock.patch.object(migration, "_foreign_keys", return_value=[]))
        stack.enter_context(mock.patch.object(migration, "_foreign_key_structures", side_effect=[[], []]))
        stack.enter_context(mock.patch.object(
            migration, "_key_constraint_structures", side_effect=[source_keys, target_keys]
        ))
        stack.enter_context(mock.patch.object(migration, "_migration_rows", return_value=[]))
        stack.enter_context(mock.patch.object(migration, "_counts", return_value={"django_migrations": 0}))
        stack.enter_context(mock.patch.object(
            migration, "_target_identity", side_effect=[source_identity, target_identity]
        ))
        stack.enter_context(mock.patch.object(migration, "_sequence_reset_statements", return_value=[]))
        return stack.enter_context(mock.patch.object(migration, "target_reset_statements"))

    def test_parent_tables_precede_children(self):
        order = migration.topological_table_order(
            ["child", "parent", "join"],
            [("child", "parent"), ("join", "child"), ("join", "parent")],
        )
        self.assertLess(order.index("parent"), order.index("child"))
        self.assertLess(order.index("child"), order.index("join"))

    def test_foreign_key_cycle_fails_closed(self):
        with self.assertRaises(migration.MigrationSafetyError):
            migration.topological_table_order(["a", "b"], [("a", "b"), ("b", "a")])

    def test_column_compatibility_requires_exact_order_and_metadata(self):
        columns = [("id", "pg_catalog", "int8", "NO", None, 64, 0, None, "NO", None)]
        migration.compare_table_columns(columns, list(columns), "sample")
        with self.assertRaises(migration.MigrationSafetyError):
            migration.compare_table_columns(columns, [], "sample")

    def test_contenttype_dropped_ordinal_gap_is_logically_compatible(self):
        definitions = [
            ("id", "pg_catalog", "int4", "NO", None, 32, 0, None, "YES", "BY DEFAULT"),
            ("app_label", "pg_catalog", "varchar", "NO", 100, None, None, None, "NO", None),
            ("model", "pg_catalog", "varchar", "NO", 100, None, None, None, "NO", None),
        ]
        source_physical = [(1, *definitions[0]), (2, *definitions[1]), (3, *definitions[2])]
        target_physical = [(1, *definitions[0]), (3, *definitions[1]), (4, *definitions[2])]
        self.assertNotEqual(source_physical, target_physical)
        # The first tuple item is physical ordinal_position. _columns orders by
        # it, then omits it from the logical metadata passed to the comparator.
        source = [row[1:] for row in source_physical]
        target = [row[1:] for row in target_physical]
        migration.compare_table_columns(source, target, "django_content_type")

    def test_column_query_orders_visible_columns_without_selecting_physical_ordinal(self):
        class Cursor:
            query = None
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def execute(self, query, _params):
                self.query = query
            def fetchall(self):
                return [("id", "pg_catalog", "int4", "NO", None, 32, 0, None, "YES", "BY DEFAULT")]

        cursor = Cursor()
        connection = mock.Mock()
        connection.cursor.return_value = cursor
        rows = migration._columns(connection, "django_content_type")
        select_clause = cursor.query.split("FROM", 1)[0]
        self.assertNotIn("ordinal_position", select_clause)
        self.assertIn("ORDER BY ordinal_position", cursor.query)
        self.assertEqual(rows[0][0], "id")
        self.assertEqual(rows[0][-2:], ("YES", "BY DEFAULT"))

    def test_visible_column_reordering_remains_incompatible(self):
        id_column = ("id", "pg_catalog", "int4", "NO", None, 32, 0, None, "YES", "BY DEFAULT")
        app_label = ("app_label", "pg_catalog", "varchar", "NO", 100, None, None, None, "NO", None)
        model = ("model", "pg_catalog", "varchar", "NO", 100, None, None, None, "NO", None)
        with self.assertRaises(migration.MigrationSafetyError):
            migration.compare_table_columns(
                [id_column, app_label, model], [id_column, model, app_label], "django_content_type"
            )

    def test_genuine_column_mismatches_abort_before_reset_planning(self):
        id_column = ("id", "pg_catalog", "int4", "NO", None, 32, 0, None, "YES", "BY DEFAULT")
        varchar_100 = ("app_label", "pg_catalog", "varchar", "NO", 100, None, None, None, "NO", None)
        varchar_200 = ("app_label", "pg_catalog", "varchar", "NO", 200, None, None, None, "NO", None)
        nullable = ("app_label", "pg_catalog", "varchar", "YES", 100, None, None, None, "NO", None)
        int8 = ("id", "pg_catalog", "int8", "NO", None, 64, 0, None, "YES", "BY DEFAULT")
        identity_always = ("id", "pg_catalog", "int4", "NO", None, 32, 0, None, "YES", "ALWAYS")
        numeric_10_2 = ("amount", "pg_catalog", "numeric", "NO", None, 10, 2, None, "NO", None)
        numeric_12_2 = ("amount", "pg_catalog", "numeric", "NO", None, 12, 2, None, "NO", None)
        base = [id_column, varchar_100]
        mismatches = (
            (base, [id_column]),
            (base, [id_column, varchar_100, ("extra", "pg_catalog", "text", "YES", None, None, None, None, "NO", None)]),
            (base, [id_column, ("other",) + varchar_100[1:]]),
            (base, [id_column, varchar_200]),
            (base, [id_column, nullable]),
            (base, [int8, varchar_100]),
            (base, [identity_always, varchar_100]),
            ([numeric_10_2], [numeric_12_2]),
        )
        for source_columns, target_columns in mismatches:
            with self.subTest(source=source_columns, target=target_columns), ExitStack() as stack:
                reset_plan = self._inspection_mocks(
                    stack, column_results=[source_columns, target_columns]
                )
                with self.assertRaises(migration.MigrationSafetyError):
                    migration.inspect(mock.Mock(), mock.Mock())
                reset_plan.assert_not_called()

    def test_full_fk_comparison_detects_column_action_and_composite_order(self):
        # psycopg2 adapts PostgreSQL array_agg results to Python lists.
        fk = ("fk", "public", "child", ["a", "b"], "public", "parent", ["x", "y"], "a", "r", "s", False, False)
        migration.compare_foreign_keys([fk], [fk])
        changed_rows = (
            fk[:3] + (["owner_id", "b"],) + fk[4:],
            fk[:6] + (["other_id", "y"],) + fk[7:],
            fk[:6] + (["y", "x"],) + fk[7:],
            fk[:7] + ("c",) + fk[8:],  # ON UPDATE
            fk[:8] + ("c",) + fk[9:],  # ON DELETE
            fk[:10] + (True,) + fk[11:],  # deferrable
            fk[:11] + (True,),  # initially deferred
        )
        for changed in changed_rows:
            with self.assertRaises(migration.MigrationSafetyError):
                migration.compare_foreign_keys([fk], [changed])

    def test_fk_array_metadata_rejects_null_or_empty_columns(self):
        valid = ("fk", "public", "child", ["id"], "public", "parent", ["id"], "a", "r", "s", False, False)
        for invalid in (None, []):
            malformed = valid[:3] + (invalid,) + valid[4:]
            with self.assertRaises(migration.MigrationSafetyError):
                migration.compare_foreign_keys([malformed], [valid])

    def test_external_fk_aborts_and_reset_is_child_first_scoped_and_quoted(self):
        external = ("fk", "provider", "referrer", ("id",), "public", "parent", ("id",), "a", "r", "s", False, False)
        with self.assertRaises(migration.MigrationSafetyError):
            migration.require_no_external_references([external], "public", ["parent"])
        reset = migration.target_reset_statements("public", ["parent", "child"], ["parent", "child"])
        self.assertEqual(reset[0]._wrapped[3].strings, ("child",))
        self.assertEqual(reset[0]._wrapped[1].strings, ("public",))
        self.assertNotIn("CASCADE", repr(reset))
        self.assertTrue(all(statement._wrapped[0].string == "DELETE FROM " for statement in reset))

    def test_external_fk_aborts_inspection_before_reset_plan(self):
        source = mock.Mock()
        target = mock.Mock()
        external = ("fk", "provider", "referrer", ("id",), "public", "parent", ("id",), "a", "r", "s", False, False)
        with mock.patch.object(migration, "_version", side_effect=[18, 17]), \
             mock.patch.object(migration, "_tables", return_value=["django_migrations", "parent"]), \
             mock.patch.object(migration, "_columns", return_value=[("id",)]), \
             mock.patch.object(migration, "_foreign_keys", return_value=[]), \
             mock.patch.object(migration, "_foreign_key_structures", return_value=[external]), \
             mock.patch.object(migration, "_key_constraint_structures", return_value=[]), \
             mock.patch.object(migration, "_migration_rows", return_value=[]), \
             mock.patch.object(migration, "_counts", return_value={"django_migrations": 0, "parent": 0}), \
             mock.patch.object(migration, "_target_identity", side_effect=[("source", "1", 5432), ("target", "2", 5432)]), \
             mock.patch.object(migration, "target_reset_statements") as reset_plan:
            with self.assertRaisesRegex(migration.MigrationSafetyError, "provider.referrer.fk"):
                migration.inspect(source, target)
        reset_plan.assert_not_called()

    def test_pk_mismatch_aborts_inspection_before_reset_plan(self):
        source_pk = ("public", "marketplace_order", "marketplace_order_pkey", "p", "PRIMARY KEY (id)", False, False)
        target_pk = ("public", "marketplace_order", "marketplace_order_pkey", "p", "PRIMARY KEY (id, other_id)", False, False)
        with ExitStack() as stack:
            reset_plan = self._inspection_mocks(
                stack, source_keys=[source_pk], target_keys=[target_pk]
            )
            with self.assertRaisesRegex(migration.MigrationSafetyError, "primary or unique"):
                migration.inspect(mock.Mock(), mock.Mock())
            reset_plan.assert_not_called()

    def test_unique_mismatch_aborts_inspection_before_reset_plan(self):
        source_unique = ("public", "marketplace_order", "order_external_id_key", "u", "UNIQUE (external_id, buyer_id)", False, False)
        target_unique = ("public", "marketplace_order", "order_external_id_key", "u", "UNIQUE (buyer_id, external_id)", False, False)
        with ExitStack() as stack:
            reset_plan = self._inspection_mocks(
                stack, source_keys=[source_unique], target_keys=[target_unique]
            )
            with self.assertRaisesRegex(migration.MigrationSafetyError, "primary or unique"):
                migration.inspect(mock.Mock(), mock.Mock())
            reset_plan.assert_not_called()

    def test_same_current_database_and_server_identity_is_rejected(self):
        identity = ("shared_db", "10.0.0.1", 5432)
        with ExitStack() as stack:
            reset_plan = self._inspection_mocks(
                stack, source_identity=identity, target_identity=identity
            )
            with self.assertRaisesRegex(migration.MigrationSafetyError, "same database endpoint"):
                migration.inspect(mock.Mock(), mock.Mock())
            reset_plan.assert_not_called()

    def test_different_server_endpoints_are_accepted(self):
        with ExitStack() as stack:
            self._inspection_mocks(
                stack,
                source_identity=("shared_db", "10.0.0.1", 5432),
                target_identity=("shared_db", "10.0.0.2", 6543),
            )
            report = migration.inspect(mock.Mock(), mock.Mock())
        self.assertEqual(report["tables"], ["django_migrations"])

    def test_spool_closes_after_error_and_keyboard_interrupt(self):
        def fail_with(error):
            def fail(_spool):
                raise error
            return fail

        failures = (("COPY TO", True), ("COPY FROM", False))
        for error in (RuntimeError(), KeyboardInterrupt()):
            for stage, fail_during_copy_out in failures:
                copy_out = fail_with(error) if fail_during_copy_out else mock.Mock()
                copy_in = mock.Mock() if fail_during_copy_out else fail_with(error)
                real_temporary_file = migration.tempfile.TemporaryFile
                opened_spools = []

                def tracked_temporary_file(*args, **kwargs):
                    spool = real_temporary_file(*args, **kwargs)
                    opened_spools.append(spool)
                    return spool

                with self.subTest(error=type(error).__name__, stage=stage), \
                     mock.patch.object(migration.tempfile, "TemporaryFile", side_effect=tracked_temporary_file):
                    with self.assertRaises(type(error)):
                        migration.copy_via_temporary_spool(copy_out, copy_in)
                self.assertEqual(len(opened_spools), 1)
                self.assertTrue(opened_spools[0].closed)

    def test_target_safety_rejects_non_framework_rows(self):
        target = mock.Mock()
        with mock.patch.object(migration, "_counts", return_value={"accounts_user": 1}):
            with self.assertRaises(migration.MigrationSafetyError):
                migration._target_freshness_check(target, ["accounts_user"])

    def test_target_safety_allows_only_migration_generated_allowlist(self):
        target = mock.Mock()
        with mock.patch.object(
            migration, "_counts", return_value={"django_migrations": 12, "accounts_user": 0}
        ):
            result = migration._target_freshness_check(
                target, ["django_migrations", "accounts_user"]
            )
        self.assertEqual(result["django_migrations"], 12)

    def test_sequence_restart_sql_is_qualified_and_uses_next_id(self):
        statement = migration.sequence_restart_sql("public", "accounts_user_id_seq", 19)
        self.assertEqual(len(statement._wrapped), 6)
        self.assertEqual(statement._wrapped[0].string, "ALTER SEQUENCE ")
        self.assertEqual(statement._wrapped[1].strings, ("public",))
        self.assertEqual(statement._wrapped[3].strings, ("accounts_user_id_seq",))
        self.assertEqual(statement._wrapped[4].string, " RESTART WITH ")
        self.assertEqual(statement._wrapped[5]._wrapped, 19)

    def test_sequence_reset_uses_max_plus_one_and_valid_empty_start(self):
        class Cursor:
            def __init__(self, maxima):
                self.maxima = iter(maxima)
                self.executed = []
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def execute(self, statement):
                self.executed.append(statement)
            def fetchone(self):
                return (next(self.maxima),)

        cursor = Cursor([41, 0])
        connection = mock.Mock()
        connection.cursor.return_value = cursor
        sequence_rows = [
            ("app_record", "id", "public.app_record_id_seq"),
            ("empty_record", "id", "public.empty_record_id_seq"),
        ]
        migration._reset_sequences(connection, sequence_rows)
        restarts = cursor.executed[1::2]
        self.assertEqual([statement._wrapped[-1]._wrapped for statement in restarts], [42, 1])

    def test_sequence_discovery_uses_owned_serial_and_identity_catalog_metadata(self):
        class Cursor:
            def __init__(self):
                self.calls = []
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def execute(self, statement, params):
                self.calls.append((statement, params))
            def fetchall(self):
                table = self.calls[-1][1][2]
                if table == "serial_table":
                    return [("id", "public.actual_serial_seq")]
                return [("id", "public.actual_identity_seq")]

        cursor = Cursor()
        connection = mock.Mock()
        connection.cursor.return_value = cursor
        discovered = migration._sequence_reset_statements(connection, ["serial_table", "identity_table"])
        self.assertEqual(
            discovered,
            [("serial_table", "id", "public.actual_serial_seq"),
             ("identity_table", "id", "public.actual_identity_seq")],
        )
        self.assertEqual(
            [params for _, params in cursor.calls],
            [('public."serial_table"', "public", "serial_table"),
             ('public."identity_table"', "public", "identity_table")],
        )
        self.assertTrue(all("pg_get_serial_sequence" in statement for statement, _ in cursor.calls))

    def test_execute_requires_explicit_target_confirmation(self):
        with mock.patch.dict(os.environ, {"SOURCE_DATABASE_URL": "fake", "TARGET_DATABASE_URL": "fake"}):
            for args in (["--execute"], ["--execute", "--confirm-target-reset"],
                         ["--execute", "--expected-target-database", "rehearsal"]):
                with self.subTest(args=args), self.assertRaises(SystemExit):
                    migration.main(args)

    def test_dry_run_does_not_invoke_copy(self):
        source = mock.Mock()
        target = mock.Mock()
        report = {"source_version": 18, "target_version": 17, "tables": [], "order": [],
                  "source_counts": {}, "target_counts": {}, "sequence_rows": []}
        with mock.patch.dict(os.environ, {"SOURCE_DATABASE_URL": "fake", "TARGET_DATABASE_URL": "fake"}):
            with mock.patch.object(migration.psycopg2, "connect", side_effect=[source, target]):
                with mock.patch.object(migration, "inspect", return_value=report):
                    with mock.patch.object(migration, "copy_data") as copy:
                        self.assertEqual(migration.main(["--dry-run"]), 0)
                        copy.assert_not_called()
        source.set_session.assert_called_once_with(readonly=True, autocommit=False)

    def test_keyboard_interrupt_rolls_back_target_context_and_propagates(self):
        class Cursor:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def execute(self, _statement):
                pass

        class TransactionConnection:
            autocommit = True
            def __init__(self):
                self.rollback_count = 0
                self.commit_count = 0
            def __enter__(self):
                return self
            def __exit__(self, exc_type, _exc, _tb):
                # Mirrors psycopg2 connection context semantics: rollback on any
                # exception (including BaseException subclasses), commit otherwise.
                if exc_type is None:
                    self.commit_count += 1
                else:
                    self.rollback()
                return False
            def cursor(self):
                return Cursor()
            def rollback(self):
                self.rollback_count += 1

        target = TransactionConnection()
        report = {"reset_statements": ["DELETE FROM public.sample"], "order": ["sample"],
                  "sequence_rows": [], "tables": ["sample"], "source_counts": {"sample": 1}}
        with mock.patch.object(migration, "_columns", return_value=[("id",)]), \
             mock.patch.object(migration, "_copy_table", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                migration.copy_data(mock.Mock(), target, report)
        self.assertEqual(target.rollback_count, 1)
        self.assertEqual(target.commit_count, 0)

    def test_credentials_never_appear_in_connection_failure_output(self):
        sentinel_source = "postgresql://source:secret-source@host/source"
        sentinel_target = "postgresql://target:secret-target@host/target"
        stdout, stderr = mock.patch("sys.stdout"), mock.patch("sys.stderr")
        with mock.patch.dict(os.environ, {"SOURCE_DATABASE_URL": sentinel_source,
                                          "TARGET_DATABASE_URL": sentinel_target}):
            with mock.patch.object(migration.psycopg2, "connect",
                                   side_effect=migration.psycopg2.OperationalError(sentinel_source)):
                with stdout as out, stderr as err:
                    self.assertEqual(migration.main(["--dry-run"]), 2)
                    rendered = out.getvalue() + err.getvalue()
        self.assertNotIn("secret-source", rendered)
        self.assertNotIn("secret-target", rendered)
        self.assertNotIn(sentinel_source, rendered)
        self.assertNotIn(sentinel_target, rendered)


if __name__ == "__main__":
    unittest.main()
