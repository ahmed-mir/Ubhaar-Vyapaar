"""Settings for the Playwright-managed local E2E server only.

This module is selected only by ``playwright.config.js`` when Playwright starts
its own local server. Use a fast password hasher so the auth smoke test still
exercises Django's complete login and password verification flow without
making the test runtime depend on the host machine's PBKDF2 speed.
"""

from .settings import *  # noqa: F403


PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
