"""Database configuration helpers shared by Django settings modules."""

from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured


POSTGRES_ENGINE = "django.db.backends.postgresql"
SQLITE_ENGINE = "django.db.backends.sqlite3"
_VALID_SSL_MODES = {
    "disable",
    "allow",
    "prefer",
    "require",
    "verify-ca",
    "verify-full",
}
_STRICT_SSL_MODES = {"verify-ca", "verify-full"}


def sqlite_database_config(path):
    """Return a SQLite config without parsing an environment-provided URL."""
    return {
        "ENGINE": SQLITE_ENGINE,
        "NAME": str(Path(path)),
        "CONN_MAX_AGE": 600,
    }


def build_database_config(*, debug, database_url, base_dir, test_mode=False):
    """Build a safe DB config for development, tests, or production.

    Django's standard test runner always receives a local SQLite database so
    its normal isolated test database cannot be redirected by DATABASE_URL.
    Production is deliberately fail-closed and always requires PostgreSQL/TLS.
    """
    base_dir = Path(base_dir)

    if test_mode:
        return sqlite_database_config(base_dir / "db.sqlite3")

    normalized_url = (database_url or "").strip()
    if not normalized_url:
        if not debug:
            raise ImproperlyConfigured(
                "DATABASE_URL is required when DEBUG=False."
            )
        return sqlite_database_config(base_dir / "db.sqlite3")

    try:
        database = dj_database_url.parse(
            normalized_url,
            conn_max_age=600,
        )
    except Exception:
        # Do not include the supplied URL in configuration errors.
        raise ImproperlyConfigured(
            "DATABASE_URL must be a valid supported database URL."
        ) from None

    if debug:
        return database

    if database.get("ENGINE") != POSTGRES_ENGINE:
        raise ImproperlyConfigured(
            "DATABASE_URL must configure PostgreSQL when DEBUG=False."
        )

    if not database.get("HOST") or not database.get("NAME"):
        raise ImproperlyConfigured(
            "DATABASE_URL must include a PostgreSQL host and database name."
        )

    options = database.setdefault("OPTIONS", {})
    sslmode = options.get("sslmode", "require").lower()
    if sslmode not in _VALID_SSL_MODES:
        raise ImproperlyConfigured(
            "DATABASE_URL contains an unsupported PostgreSQL SSL mode."
        )
    if sslmode not in _STRICT_SSL_MODES:
        options["sslmode"] = "require"

    return database
