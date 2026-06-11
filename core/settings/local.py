"""Local development settings."""
from .base import *  # noqa: F401, F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Use SQLite for tests when no DB env is set
import os  # noqa: E402

if not os.environ.get("DB_PASSWORD"):
    DATABASES = {  # noqa: F405
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
        }
    }

# Shorter connection pool for local dev
DATABASES["default"]["CONN_MAX_AGE"] = 0  # noqa: F405
