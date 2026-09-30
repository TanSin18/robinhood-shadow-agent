import json
import random
import sqlite3
from datetime import datetime, timedelta, timezone

from eval.promotion_stats import MIN_DECISIONS, evaluate, load


def _db(path, days, edge=0.0, decisions=0, before=True):
    db = sqlite3.connect(path)
    for t in ('daily_values', 'fills', 'api_costs'):
        db.execute(f'CREATE TABLE {t} (id INTEGER PRIMARY KEY, created_at TEXT, payload_json TEXT)')
    rng = random.Random(2)
    start = datetime(2026, 10, 1, 14, 5, tzinfo=timezone.utc)
    arm, vti = 500.0, 300.0
    rows = []
    if before:  # build-phase record must be ignored
        rows.append(('daily_values', {'kind': 'paper_valuation', 'lane': 'A', 'track': 'agent_alone', 'value': '900',
                                      'data_mode': 'live_readonly', 'timestamp': '2026-09-30T14:05:00+00:00'}))
    for i in range(days):
        ts = (start + timedelta(days=i)).isoformat()
        r = rng.gauss(0.0003, 0.01)
        vti *= 1 + r
        arm *= 1 + r + edge
        for track in ('agent_alone', 'with_approvals', 'deterministic_no_ai'):
            rows.append(('daily_values', {'kind': 'paper_valuation', 'lane': 'A', 'track': track, 'value': str(arm),
                                          'data_mode': 'live_readonly', 'timestamp': ts}))
        rows.append(('daily_values', {'benchmark': 'VTI', 'close': {'date': ts[:10], 'price': str(vti)},
                                      'data_mode': 'live_readonly', 'timestamp': ts}))
    for i in range(decisions):
        rows.append(('fills', {'status': 'filled', 'track': 'A:deterministic_no_ai',
                               'timestamp': (start + timedelta(hours=i)).isoformat()}))
    for table, payload in rows:
        db.execute(f'INSERT INTO {table}(created_at,payload_json) VALUES (?,?)', ('x', json.dumps(payload)))
    db.commit(); db.close()


def test_small_sample_is_not_proven(tmp_path):
    _db(tmp_path / 'a.db', 30, edge=0.01)
    result = evaluate(load(tmp_path / 'a.db'))
    arm = result['arms']['deterministic_no_ai']
    assert arm['verdict'] == 'NOT_PROVEN' and any('SAMPLE_TOO_SMALL' in r for r in arm['reasons'])
    assert result['unlocks_live_money'] is False


def test_large_clear_edge_passes_and_zero_edge_does_not(tmp_path):
    _db(tmp_path / 'b.db', 260, edge=0.002, decisions=MIN_DECISIONS)
    assert evaluate(load(tmp_path / 'b.db'))['arms']['deterministic_no_ai']['verdict'] == 'EDGE_SHOWN'
    _db(tmp_path / 'c.db', 260, edge=0.0)
    assert evaluate(load(tmp_path / 'c.db'))['arms']['deterministic_no_ai']['verdict'] == 'NOT_PROVEN'


def test_build_phase_rows_ignored(tmp_path):
    _db(tmp_path / 'd.db', 5)
    data = load(tmp_path / 'd.db')
    assert min(data['series']['agent_alone']) >= '2026-10-01'
