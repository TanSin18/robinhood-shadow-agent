"""Transaction-scoped SQLite ownership, independent of garbage collection."""
from contextlib import contextmanager
import sqlite3


@contextmanager
def connection(database, *, row_factory=None, **options):
    db = sqlite3.connect(database, **options)
    try:
        db.row_factory = row_factory
        has_role=db.execute("SELECT 1 FROM sqlite_master WHERE name='database_role'").fetchone()
        role=db.execute('SELECT role FROM database_role WHERE singleton=1').fetchone() if has_role else None
        if role and role[0] in {'whatif','replay'}:
            protected={'cycle_runs','approval_inbox','paper_accounts','orders','fills','cards',
                       'daily_values','lessons','decision_records','strategy_versions',
                       'strategy_changes','improvement_proposals','weekly_reports'}
            def authorize(action, first, second, schema, trigger):
                if action in {sqlite3.SQLITE_ATTACH,sqlite3.SQLITE_DETACH,
                              sqlite3.SQLITE_DROP_TRIGGER,sqlite3.SQLITE_DROP_TABLE,
                              sqlite3.SQLITE_ALTER_TABLE}:
                    return sqlite3.SQLITE_DENY
                if action in {sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE} and first in protected:
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            db.set_authorizer(authorize)
        # sqlite3's context manager commits/rolls back; it does NOT close.
        with db:
            yield db
    finally:
        db.close()
