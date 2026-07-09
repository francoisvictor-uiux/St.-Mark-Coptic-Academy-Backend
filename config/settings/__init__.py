import os

# Route Django's MySQL backend through PyMySQL (pure-Python, no C build on cPanel).
try:
    import pymysql

    pymysql.version_info = (1, 4, 6, "final", 0)
    pymysql.install_as_MySQLdb()
except Exception:
    pass

if os.environ.get("DJANGO_ENV", "dev") == "prod":
    from .prod import *  # noqa: F401,F403
else:
    from .dev import *  # noqa: F401,F403
