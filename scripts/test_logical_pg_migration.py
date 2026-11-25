import os
import unittest
from unittest import mock

try:
    from scripts import logical_pg_migration as migration
except ImportError:
    import logical_pg_migration as migration


class LogicalMigrationSafetyTests(unittest.TestCase):
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
        columns = [("id", 1, "pg_catalog", "int8", "NO", None, 64, 0, None)]
        migration.compare_table_columns(columns, list(columns), "sample")
        with self.assertRaises(migration.MigrationSafetyError):
            migration.compare_table_columns(columns, [], "sample")

    def test_full_fk_comparison_detects_column_action_and_composite_order(self):
        fk = ("fk", "public", "child", ("a", "b"), "public", "parent", ("x", "y"), "a", "r", "s", False, False)
        migration.compare_foreign_keys([fk], [fk])
        for changed in (fk[:3] + (("owner_id", "b"),) + fk[4:],
                        fk[:6] + (("y", "x"),) + fk[7:],
                        fk[:8] + ("c",) + fk[9:]):
            with self.assertRaises(migration.MigrationSafetyError):
                migration.compare_foreign_keys([fk], [changed])

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
                with self.subTest(error=type(error).__name__, stage=stage), \
                     mock.patch.object(migration.tempfile, "TemporaryFile") as temp_file:
                    with self.assertRaises(type(error)):
                        migration.copy_via_temporary_spool(copy_out, copy_in)
                    temp_file.return_value.__exit__.assert_called_once()

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

    def test_execute_requires_explicit_target_confirmation(self):
        with mock.patch.dict(os.environ, {"SOURCE_DATABASE_URL": "fake", "TARGET_DATABASE_URL": "fake"}):
            with self.assertRaises(SystemExit):
                migration.main(["--execute"])

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
