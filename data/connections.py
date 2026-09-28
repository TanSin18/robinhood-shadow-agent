"""Transaction-scoped SQLite ownership, independent of garbage collection."""
from contextlib import contextmanager
import sqlite3


@contextmanager
def connection(database, *, row_factory=None, **options):
    db = sqlite3.connect(database, **options)
    try:
        db.row_factory = row_factory
        # sqlite3's context manager commits/rolls back; it does NOT close.
        with db:
            yield db
    finally:
        db.close()
