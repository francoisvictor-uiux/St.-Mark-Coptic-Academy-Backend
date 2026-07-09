"""Lower Django's minimum PostgreSQL version so it will run on the host's
PostgreSQL 10.x. Django 5.2 defaults to requiring PostgreSQL 14+, but this
project uses only standard field types (verified: no generated columns,
covering indexes, exclusion constraints, or array/trigram features), so
PostgreSQL 10 is sufficient in practice. This is unsupported by Django
upstream; revisit if the host upgrades PostgreSQL or you add newer features.
"""

from django.db.backends.postgresql.features import (
    DatabaseFeatures as PostgresDatabaseFeatures,
)


class DatabaseFeatures(PostgresDatabaseFeatures):
    minimum_database_version = (10,)
