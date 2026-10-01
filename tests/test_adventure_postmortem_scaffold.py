import sqlite3

import pytest

from research.adventure import AdventureError, admit, open_adventure
from research.postmortem import Label, LabelError, decide, propose


def test_adventure_refuses_official_directory(tmp_path):
    official = tmp_path / 'data' / 'agent.db'
    official.parent.mkdir()
    with pytest.raises(AdventureError):
        open_adventure(tmp_path / 'data' / 'adventure.db', official)


def test_adventure_admits_only_passes_or_capped_explore(tmp_path):
    db = open_adventure(tmp_path / 'adv' / 'adventure.db', tmp_path / 'data' / 'agent.db')
    with pytest.raises(AdventureError):
        admit(db, recipe_id='r', recipe_sha256='a', trial_id=1, verdict='NOT_PROVEN', added_at='t')
    with pytest.raises(AdventureError):
        admit(db, recipe_id='r', recipe_sha256='a', trial_id=1, verdict='NOT_PROVEN', explore=True, weight='0.05', added_at='t')
    admit(db, recipe_id='r', recipe_sha256='a', trial_id=1, verdict='PASS', added_at='t')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO adventure_fills(created_at,recipe_id,payload_json,tag) VALUES ('t','r','{}','OFFICIAL')")


def _label(**kw):
    base = dict(trade_id='t1', recipe_id='r', book='adventure', primary_cause='luck', excess_vs_vti='-0.01',
                window_start='2026-10-01', window_end='2026-10-20', proposed_by='critic', proposed_at='t')
    base.update(kw)
    return Label(**base)


def test_postmortem_validation_and_operator_decides(tmp_path):
    db = sqlite3.connect(tmp_path / 'pm.db', isolation_level=None)
    for bad in (dict(primary_cause='vibes'), dict(book='real'), dict(dirty=('rumor',)), dict(proposed_by='operator')):
        with pytest.raises(LabelError):
            propose(db, _label(**bad))
    propose(db, _label(dirty=('stale_quote',)))
    with pytest.raises(LabelError):
        decide(db, 't1', 'ACCEPTED', decided_by='critic', decided_at='t')
    decide(db, 't1', 'ACCEPTED', decided_by='operator', decided_at='t')
    with pytest.raises(LabelError):
        decide(db, 't1', 'REJECTED', decided_by='operator', decided_at='t')
