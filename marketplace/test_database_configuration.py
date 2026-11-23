import json
import os
import subprocess
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.database import (
    build_database_config,
    is_django_test_command,
    POSTGRES_ENGINE,
    SQLITE_ENGINE,
)


BASE_DIR = Path(__file__).resolve().parents[1]


class DatabaseConfigurationTests(SimpleTestCase):
    def build(self, *, debug, url=""):
        return build_database_config(
            debug=debug,
            database_url=url,
            base_dir=BASE_DIR,
        )

    def test_debug_development_defaults_to_local_sqlite(self):
        config = self.build(debug=True)

        self.assertEqual(config["ENGINE"], SQLITE_ENGINE)
        self.assertEqual(config["NAME"], str(BASE_DIR / "db.sqlite3"))

    def test_debug_development_can_use_an_explicit_postgresql_url(self):
        config = self.build(
            debug=True,
            url="postgresql://user:password@db.example.test/app",
        )

        self.assertEqual(config["ENGINE"], POSTGRES_ENGINE)

    def test_production_requires_database_url(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "DATABASE_URL is required when DEBUG=False.",
        ):
            self.build(debug=False)

    def test_production_rejects_sqlite(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "DATABASE_URL must configure PostgreSQL when DEBUG=False.",
        ):
            self.build(debug=False, url="sqlite:///production.sqlite3")

    def test_production_accepts_postgresql_without_connecting(self):
        config = self.build(
            debug=False,
            url="postgresql://user:password@db.example.test/app",
        )

        self.assertEqual(config["ENGINE"], POSTGRES_ENGINE)
        self.assertEqual(config["HOST"], "db.example.test")
        self.assertEqual(config["OPTIONS"]["sslmode"], "require")
        self.assertEqual(config["OPTIONS"]["connect_timeout"], 10)

    def test_production_preserves_finite_connect_timeout_and_replaces_unbounded(self):
        explicit = self.build(
            debug=False,
            url=(
                "postgresql://user:password@db.example.test/app"
                "?connect_timeout=20"
            ),
        )
        unbounded = self.build(
            debug=False,
            url=(
                "postgresql://user:password@db.example.test/app"
                "?connect_timeout=0"
            ),
        )

        self.assertEqual(explicit["OPTIONS"]["connect_timeout"], 20)
        self.assertEqual(unbounded["OPTIONS"]["connect_timeout"], 10)

    def test_production_replaces_weaker_ssl_modes_with_require(self):
        for mode in ("disable", "allow", "prefer"):
            with self.subTest(mode=mode):
                config = self.build(
                    debug=False,
                    url=(
                        "postgresql://user:password@db.example.test/app"
                        f"?sslmode={mode}"
                    ),
                )
                self.assertEqual(config["OPTIONS"]["sslmode"], "require")

    def test_production_preserves_stricter_ssl_modes(self):
        for mode in ("verify-ca", "verify-full"):
            with self.subTest(mode=mode):
                config = self.build(
                    debug=False,
                    url=(
                        "postgresql://user:password@db.example.test/app"
                        f"?sslmode={mode}"
                    ),
                )
                self.assertEqual(config["OPTIONS"]["sslmode"], mode)

    def test_production_rejects_invalid_ssl_mode_without_echoing_url(self):
        url = (
            "postgresql://user:do-not-print@db.example.test/app"
            "?sslmode=invalid"
        )

        with self.assertRaises(ImproperlyConfigured) as raised:
            self.build(debug=False, url=url)

        self.assertNotIn("do-not-print", str(raised.exception))

    def test_invalid_database_url_error_does_not_echo_credentials(self):
        url = "mysql://user:do-not-print@db.example.test/app"

        with self.assertRaises(ImproperlyConfigured) as raised:
            self.build(debug=False, url=url)

        self.assertNotIn("do-not-print", str(raised.exception))

    def test_only_actual_test_subcommand_enables_test_mode(self):
        cases = (
            (["manage.py", "test"], True),
            (["manage.py", "test", "accounts"], True),
            (["manage.py", "test", "marketplace.tests.SomeTest"], True),
            (["manage.py", "check", "test"], False),
            (["manage.py", "shell", "test"], False),
            (["manage.py", "migrate", "test"], False),
            (["manage.py", "somecommand", "test"], False),
        )

        for argv, expected in cases:
            with self.subTest(argv=argv):
                self.assertIs(is_django_test_command(argv), expected)

    def test_test_subcommand_in_real_settings_uses_local_test_database(self):
        fake_database_url = (
            "postgresql://local-test:fake@db.example.test/prod"
        )
        environment = os.environ.copy()
        environment.update(
            {
                "DATABASE_URL": fake_database_url,
                "DJANGO_DEBUG": "False",
                "DJANGO_SECRET_KEY": "local-settings-test-key",
                "DJANGO_USE_CLOUDINARY_MEDIA": "False",
                "SENTRY_DSN": "https://test@example.invalid/1",
            }
        )
        script = (
            "import json, sys; "
            "sys.argv = ['manage.py', 'test', 'accounts']; "
            "from config import settings as s; "
            "print(json.dumps({"
            "'engine': s.DATABASES['default']['ENGINE'], "
            "'name': s.DATABASES['default']['NAME'], "
            "'staticfiles_backend': s.STORAGES['staticfiles']['BACKEND'], "
            "'sentry_enabled': s.SENTRY_ENABLED}))"
        )

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        settings_result = json.loads(result.stdout.strip().splitlines()[-1])

        self.assertEqual(settings_result["engine"], SQLITE_ENGINE)
        self.assertEqual(
            settings_result["name"],
            str(BASE_DIR / "db.sqlite3"),
        )
        self.assertEqual(
            settings_result["staticfiles_backend"],
            "django.contrib.staticfiles.storage.StaticFilesStorage",
        )
        self.assertFalse(settings_result["sentry_enabled"])

    def test_non_test_command_with_test_argument_fails_closed(self):
        environment = os.environ.copy()
        environment.update(
            {
                "DATABASE_URL": "",
                "DJANGO_DEBUG": "False",
                "DJANGO_SECRET_KEY": "local-settings-test-key",
                "DJANGO_USE_CLOUDINARY_MEDIA": "False",
                "SENTRY_DSN": "",
            }
        )
        script = (
            "import sys\n"
            "sys.argv = ['manage.py', 'shell', 'test']\n"
            "from django.core.exceptions import ImproperlyConfigured\n"
            "try:\n"
            "    import config.settings\n"
            "except ImproperlyConfigured as exc:\n"
            "    expected = 'DATABASE_URL is required when DEBUG=False.'\n"
            "    if str(exc) != expected:\n"
            "        raise\n"
            "    print('production database guard active')\n"
            "else:\n"
            "    raise AssertionError('settings did not fail closed')\n"
        )

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )

        self.assertIn("production database guard active", result.stdout)

    def test_e2e_settings_ignore_parent_database_url(self):
        fake_database_url = (
            "postgresql://local-test:do-not-print@db.example.test/prod"
        )
        environment = os.environ.copy()
        environment.update(
            {
                "DATABASE_URL": fake_database_url,
                "DJANGO_DEBUG": "False",
                "DJANGO_SECRET_KEY": "local-e2e-settings-test-key",
                "SENTRY_DSN": "https://test@example.invalid/1",
            }
        )
        script = (
            "import json, os; "
            "from config import settings_e2e as s; "
            "print(json.dumps({"
            "'engine': s.DATABASES['default']['ENGINE'], "
            "'name': s.DATABASES['default']['NAME'], "
            "'debug': s.DEBUG, "
            "'sentry_enabled': s.SENTRY_ENABLED, "
            "'database_url': os.environ.get('DATABASE_URL')}))"
        )

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        settings_result = json.loads(result.stdout.strip().splitlines()[-1])

        self.assertEqual(settings_result["engine"], SQLITE_ENGINE)
        self.assertEqual(
            settings_result["name"],
            str(BASE_DIR / "db_e2e.sqlite3"),
        )
        self.assertNotEqual(
            settings_result["name"],
            str(BASE_DIR / "db.sqlite3"),
        )
        self.assertTrue(settings_result["debug"])
        self.assertFalse(settings_result["sentry_enabled"])
        self.assertEqual(settings_result["database_url"], "")
        self.assertNotIn(fake_database_url, result.stdout + result.stderr)
