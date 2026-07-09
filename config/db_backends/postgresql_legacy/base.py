"""Custom PostgreSQL backend that accepts PostgreSQL 10.x.

Identical to django.db.backends.postgresql except it swaps in a features
class with a lowered ``minimum_database_version``. All other behavior
(introspection, schema editor, operations, client) is inherited unchanged.
"""

from django.db.backends.postgresql import base as postgresql_base

from .features import DatabaseFeatures


class DatabaseWrapper(postgresql_base.DatabaseWrapper):
    features_class = DatabaseFeatures
