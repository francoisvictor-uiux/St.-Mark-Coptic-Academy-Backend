import os

if os.environ.get("DJANGO_ENV", "dev") == "prod":
    from .prod import *  # noqa: F401,F403
else:
    from .dev import *  # noqa: F401,F403
