"""Post-mortem labels (scaffold): schema and validation only. Nothing writes these yet.

A post-mortem agent (or the Critic) may PROPOSE one label per closed trade. Only the operator
can accept or reject it. Accepted labels may later update Adventure weights; they never change
Official rules, which need a signed amendment.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

PRIMARY_CAUSES = ('signal', 'timing', 'size', 'cost', 'luck')
DIRTY_FLAGS = ('earnings_day', 'missing_bars', 'stale_quote', 'corporate_action', 'partial_data')
STATUSES = ('PROPOSED', 'ACCEPTED', 'REJECTED')
SCHEMA = ("CREATE TABLE IF NOT EXISTS postmortem_labels (trade_id TEXT PRIMARY KEY, recipe_id TEXT NOT NULL, "
          "book TEXT NOT NULL CHECK (book IN ('official','adventure')), primary_cause TEXT NOT NULL, "
          "excess_vs_vti TEXT NOT NULL, window_start TEXT, window_end TEXT, dirty_json TEXT, note TEXT, "
          "proposed_by TEXT NOT NULL, proposed_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PROPOSED', "
          "decided_by TEXT, decided_at TEXT)")


class LabelError(ValueError):
    pass


@dataclass(frozen=True)
class Label:
    trade_id: str
    recipe_id: str
    book: str
    primary_cause: str
    excess_vs_vti: str
    window_start: str
    window_end: str
    proposed_by: str
    proposed_at: str
    dirty: tuple = field(default_factory=tuple)
    note: str = ''

    def validate(self):
        if self.book not in ('official', 'adventure'):
            raise LabelError('BOOK_INVALID')
        if self.primary_cause not in PRIMARY_CAUSES:
            raise LabelError('PRIMARY_CAUSE_MUST_BE_ONE_OF ' + ','.join(PRIMARY_CAUSES))
        if any(flag not in DIRTY_FLAGS for flag in self.dirty):
            raise LabelError('UNKNOWN_DIRTY_FLAG')
        try:
            float(self.excess_vs_vti)
        except ValueError:
            raise LabelError('EXCESS_MUST_BE_NUMERIC') from None
        if self.proposed_by == 'operator':
            raise LabelError('AGENTS_PROPOSE_OPERATOR_DECIDES')
        return self


def propose(db, label: Label):
    import json
    label.validate()
    db.execute(SCHEMA)
    db.execute('INSERT INTO postmortem_labels (trade_id,recipe_id,book,primary_cause,excess_vs_vti,window_start,window_end,'
               'dirty_json,note,proposed_by,proposed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
               (label.trade_id, label.recipe_id, label.book, label.primary_cause, label.excess_vs_vti, label.window_start,
                label.window_end, json.dumps(list(label.dirty)), label.note, label.proposed_by, label.proposed_at))


def decide(db, trade_id, decision, *, decided_by, decided_at):
    if decided_by != 'operator':
        raise LabelError('ONLY_THE_OPERATOR_DECIDES')
    if decision not in ('ACCEPTED', 'REJECTED'):
        raise LabelError('DECISION_INVALID')
    changed = db.execute("UPDATE postmortem_labels SET status=?, decided_by=?, decided_at=? WHERE trade_id=? AND status='PROPOSED'",
                         (decision, decided_by, decided_at, trade_id)).rowcount
    if changed != 1:
        raise LabelError('NO_PROPOSED_LABEL')
