"""Production settings — spec Part 4 §5 hardening checklist."""

from .base import *  # noqa: F401,F403
from .base import SECRET_KEY, env

DEBUG = False

# Refuse to boot on the dev fallback key (checklist §5.1).
if "dev-only-insecure" in SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY must be set to a strong value in production")

# Production requires PostgreSQL — no SQLite fallback here.
if not env("DATABASE_URL", default=""):
    raise RuntimeError("DATABASE_URL must be set in production")

# TLS + headers
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True

# Cookies
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True

CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS", default=["https://smcacademy.org", "https://www.smcacademy.org"]
)

# Persistent DB connections
DATABASES["default"]["CONN_MAX_AGE"] = 60  # noqa: F405

# WhiteNoise serves the admin + Swagger static assets straight from the app,
# so no web-server alias is needed. collectstatic must run on each deploy.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
