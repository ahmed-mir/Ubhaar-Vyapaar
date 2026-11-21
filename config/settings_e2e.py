"""Settings for the Playwright-managed local E2E server only.

This module is selected only by ``playwright.config.js`` when Playwright starts
its own local server. Use a fast password hasher so the auth smoke test still
exercises Django's complete login and password verification flow without
making the test runtime depend on the host machine's PBKDF2 speed.
"""

import os

# Prevent both the parent shell and load_dotenv() in base settings from
# supplying a database URL or production DEBUG setting to the E2E process.
os.environ["DATABASE_URL"] = ""
os.environ["DJANGO_DEBUG"] = "True"

from .settings import *  # noqa: F403


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(BASE_DIR / "db_e2e.sqlite3"),  # noqa: F405
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
