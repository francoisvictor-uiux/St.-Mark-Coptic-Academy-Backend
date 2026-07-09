import os

from .base import *  # noqa: F401,F403
from .base import BASE_DIR

DEBUG = True

# PostgreSQL when DATABASE_URL is set; otherwise a local SQLite file so dev
# works without a Postgres install. Prod requires DATABASE_URL (see prod.py).
if not os.environ.get("DATABASE_URL"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# OTPs and verification emails are sent via real SMTP (info@smcacademy.org).
# EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"  # uncomment to use console in dev
