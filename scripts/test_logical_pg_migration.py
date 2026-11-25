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
        source.set_session.assert_called()


if __name__ == "__main__":
    unittest.main()
