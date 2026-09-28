"""Operator-assisted Robinhood access revocation and reauthorization drill."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import uuid4

from broker.read_contracts import READ_METHODS
from data.connections import connection


class RevocationDrill:
    def __init__(self, database, *, config_hash: str, preregistration_hash: str):
        self.database = Path(database)
        self.config_hash = config_hash
        self.preregistration_hash = preregistration_hash

    def _schema(self, db):
        db.execute('''CREATE TABLE IF NOT EXISTS oauth_revocation_drills (
          id TEXT PRIMARY KEY, begun_at TEXT NOT NULL,
          revoked_read_failed_at TEXT, local_credentials_removed_at TEXT,
          reauthorized_read_passed_at TEXT, status TEXT NOT NULL,
          preregistration_hash TEXT NOT NULL, config_hash TEXT NOT NULL)''')

    def _latest(self, db):
        cursor = db.execute('SELECT * FROM oauth_revocation_drills ORDER BY begun_at DESC LIMIT 1')
        row = cursor.fetchone()
        if row is None: raise ValueError('revocation drill has not begun')
        return {description[0]: value for description, value in zip(cursor.description, row)}

    def begin(self, now):
        if now.tzinfo is None: raise ValueError('timezone-aware time required')
        with connection(self.database) as db:
            self._schema(db)
            identifier = uuid4().hex
            db.execute('''INSERT INTO oauth_revocation_drills
              VALUES (?,?,NULL,NULL,NULL,'AWAITING_REMOTE_REVOKE',?,?)''',
              (identifier, now.isoformat(), self.preregistration_hash, self.config_hash))
        return {'status': 'AWAITING_REMOTE_REVOKE'}

    def record_revoked_read_failure(self, error_class, now):
        if error_class not in {'AUTH_REVOKED', 'UNAUTHORIZED'}:
            raise ValueError('an authentication-class failure is required')
        with connection(self.database) as db:
            self._schema(db); row = self._latest(db)
            if row['status'] != 'AWAITING_REMOTE_REVOKE': raise ValueError('invalid drill state')
            db.execute('''UPDATE oauth_revocation_drills SET revoked_read_failed_at=?,
              status='AWAITING_LOCAL_DELETE' WHERE id=?''', (now.isoformat(), row['id']))

    def record_local_credentials_removed(self, now):
        with connection(self.database) as db:
            self._schema(db); row = self._latest(db)
            if row['status'] != 'AWAITING_LOCAL_DELETE' or not row['revoked_read_failed_at']:
                raise ValueError('a failed revoked-credential read is required first')
            db.execute('''UPDATE oauth_revocation_drills SET local_credentials_removed_at=?,
              status='AWAITING_REAUTHORIZATION' WHERE id=?''', (now.isoformat(), row['id']))

    def verify_reauthorized(self, *, greeting, read_succeeded, now):
        if set(greeting.get('effective_read_tools', [])) != set(READ_METHODS) or greeting.get('effective_write_tool_count') != 0:
            raise ValueError('exact read inventory is required')
        if greeting.get('config_hash') != self.config_hash or greeting.get('preregistration_hash') != self.preregistration_hash:
            raise ValueError('current configuration hashes are required')
        if read_succeeded is not True: raise ValueError('fresh allowed read is required')
        with connection(self.database) as db:
            self._schema(db); row = self._latest(db)
            if row['status'] != 'AWAITING_REAUTHORIZATION' or not row['local_credentials_removed_at']:
                raise ValueError('local credential removal is not proven')
            db.execute('''UPDATE oauth_revocation_drills SET reauthorized_read_passed_at=?,
              status='COMPLETED' WHERE id=?''', (now.isoformat(), row['id']))
        return self.receipt()

    def receipt(self):
        with connection(self.database) as db:
            self._schema(db); row = self._latest(db)
            return {key: row[key] for key in (
                'status', 'begun_at', 'revoked_read_failed_at',
                'local_credentials_removed_at', 'reauthorized_read_passed_at',
                'preregistration_hash', 'config_hash',
            )}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('begin', 'verify-revoked', 'remove-local-credentials', 'verify-reauthorized'))
    parser.add_argument('--database', default='data/agent.db')
    args = parser.parse_args()
    print(json.dumps({'status': 'OPERATOR_STEP_REQUIRED', 'action': args.action,
                      'runbook': 'docs/operations/robinhood-access-revocation.md'}))
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
