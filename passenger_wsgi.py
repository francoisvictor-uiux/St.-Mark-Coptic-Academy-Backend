"""Passenger entry point for cPanel "Setup Python App" (LiteSpeed/Apache)."""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_ENV", "prod")

# Route Django's MySQL backend through PyMySQL (pure-Python, no C build on cPanel).
try:
    import pymysql

    pymysql.version_info = (1, 4, 6, "final", 0)
    pymysql.install_as_MySQLdb()
except Exception:
    pass

from config.wsgi import application  # noqa: E402
