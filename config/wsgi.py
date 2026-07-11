"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.
"""

import os

# Route Django's MySQL backend through PyMySQL (pure-Python; mysqlclient can't
# compile on this shell-less cPanel host). This MUST run before Django loads any
# database backend. LiteSpeed's LSAPI can import config.wsgi directly (bypassing
# passenger_wsgi.py), so the shim lives here too — and deliberately does NOT
# swallow errors, so a failure surfaces in the log instead of degrading into a
# confusing "Error loading MySQLdb module" further down the stack.
import pymysql

pymysql.version_info = (1, 4, 6, "final", 0)
pymysql.install_as_MySQLdb()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
