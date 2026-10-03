"""Additive research storage; refuses official paths and unidentified databases."""
from datetime import datetime, timezone
from dataclasses import asdict
from pathlib import Path
import sqlite3
import uuid

from .types import canonical, content_hash, from_payload
from .registry import validate_definition
from .stored_payload import read_result

CANONICAL_OFFICIAL = Path('/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/data/agent.db')
TABLES = ('research_feature_definitions', 'research_feature_runs',
          'research_feature_results', 'research_feature_inputs', 'research_sector_mappings')


def validate_path(path, official_db):
    target = Path(path).resolve()
    for raw in (official_db, CANONICAL_OFFICIAL):
        official = Path(raw).resolve()
        if (target == official or official.parent in target.parents or
                (target.exists() and official.exists() and target.samefile(official))):
            raise ValueError('OFFICIAL_DATABASE_FORBIDDEN')
    if not target.is_file():
        raise ValueError('EXISTING_FIRM_LAB_REQUIRED')
    with sqlite3.connect(target.as_uri() + '?mode=ro', uri=True) as db:
        names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if names & {'paper_accounts', 'cycle_runs', 'orders', 'fills', 'positions', 'accounts'}:
            raise ValueError('OFFICIAL_OR_EXECUTION_SCHEMA_FORBIDDEN')
        if 'firm_meta' not in names:
            raise ValueError('FIRM_LAB_IDENTITY_REQUIRED')
        row = db.execute("SELECT value FROM firm_meta WHERE key='mode'").fetchone()
        if row != ('BUILD_OBSERVE',):
            raise ValueError('BUILD_OBSERVE_REQUIRED')
    return target


class FeatureStore:
    def __init__(self, path, official_db=CANONICAL_OFFICIAL):
        self.active_run=None
        self.result_ids=[]
        self.path = validate_path(path, official_db)
        self.db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True)
        with self.db:
            for table in TABLES:
                self.db.execute(f'CREATE TABLE IF NOT EXISTS {table} ('
                                'id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL)')
                for action in ('UPDATE', 'DELETE'):
                    self.db.execute(f'CREATE TRIGGER IF NOT EXISTS {table}_{action.lower()} '
                                    f'BEFORE {action} ON {table} BEGIN '
                                    "SELECT RAISE(ABORT, 'APPEND_ONLY'); END")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.db.close()

    def _insert(self, table, identity, payload):
        return self.db.execute(f'INSERT OR IGNORE INTO {table}(id,payload,created_at) VALUES(?,?,?)',
            (identity, canonical(payload), datetime.now(timezone.utc).isoformat())).rowcount > 0

    def append(self, result):
        # Revalidate even if a caller mutated a nested audit/value object.
        result = from_payload(canonical(result))
        if any(r.table == 'corporate_action_observations' for r in result.refs):
            raise ValueError('BENCHMARK_SOURCE_FORBIDDEN')
        identity = content_hash(result)
        inputs={'refs':[asdict(ref) for ref in result.refs]}
        input_set_id=content_hash(inputs)
        payload={**asdict(result),'refs':None,'input_set_id':input_set_id}
        with self.db:
            self._insert('research_feature_inputs',input_set_id,inputs)
            added = self._insert('research_feature_results', identity, payload)
        if self.active_run is not None:
            self.result_ids.append(identity)
        return added

    def register(self, definition):
        definition = validate_definition(definition)
        identity = content_hash([definition[k] for k in ('family', 'name', 'version')])
        with self.db:
            previous = self.db.execute('SELECT payload FROM research_feature_definitions WHERE id=?', (identity,)).fetchone()
            if previous and previous[0] != canonical(definition):
                raise ValueError('FORMULA_CHANGE_REQUIRES_VERSION')
            return self._insert('research_feature_definitions', identity, definition)

    def register_mapping(self,record):
        from .sector import validate_mapping_record
        record=validate_mapping_record(record)
        with self.db:
            return self._insert('research_sector_mappings',record['content_hash'],record)

    def read(self, request):
        selected = {}
        for (payload,) in self.db.execute('SELECT payload FROM research_feature_results ORDER BY id'):
            r = read_result(self.db,payload)
            if r.instrument != request.instrument or r.as_of_session != request.as_of_session:
                continue
            # Unavailable rows need the requested cutoff in audit to avoid leaking later diagnostics.
            eligible_at = r.known_at or r.audit.get('knowledge_cutoff')
            if eligible_at is None or eligible_at > request.knowledge_cutoff:
                continue
            key = (r.family, r.name, r.feature_version, r.calculation_hash)
            prev = selected.get(key)
            if prev is None or eligible_at > (prev.known_at or prev.audit['knowledge_cutoff']):
                selected[key] = r
            elif eligible_at == (prev.known_at or prev.audit['knowledge_cutoff']) and r != prev:
                raise ValueError('CONFLICTING_RESULT_REVISION')
        return tuple(selected[k] for k in sorted(selected))

    def start_run(self, request):
        if self.active_run is not None:
            raise ValueError('RUN_ALREADY_ACTIVE')
        run_id = uuid.uuid4().hex
        with self.db:
            self._insert('research_feature_runs', run_id, {'request': asdict(request), 'state': 'STARTED'})
        self.active_run=run_id
        self.result_ids=[]
        return run_id

    def finish_run(self, run_id, receipt):
        with self.db:
            if not self.db.execute('SELECT 1 FROM research_feature_runs WHERE id=?', (run_id,)).fetchone():
                raise ValueError('UNKNOWN_RUN')
            if self.db.execute('SELECT 1 FROM research_feature_runs WHERE id=?',(run_id+':finished',)).fetchone():
                raise ValueError('RUN_ALREADY_FINISHED')
            if self.active_run!=run_id:
                raise ValueError('RUN_NOT_ACTIVE')
            receipt={**receipt,'result_ids':sorted(set(self.result_ids)),
                     'result_count':len(set(self.result_ids))}
            if not self._insert('research_feature_runs', run_id + ':finished',
                                {'run_id': run_id, 'state': 'FINISHED', 'receipt': receipt}):
                raise ValueError('RUN_ALREADY_FINISHED')
        self.active_run=None
