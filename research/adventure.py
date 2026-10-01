"""Adventure book (scaffold): schema and isolation rules only. Nothing runs it yet.

The Adventure book is a separate paper database for recipes that passed the research harness
(or explicit "explore" recipes capped at 2% of Adventure capital). It can never write to the
Official database, and Official results never include it. A monthly bandit across passed
recipes will set Adventure weights later; that code is not written yet.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROLE = 'adventure'
EXPLORE_CAP = 0.02
SCHEMA = (
    "CREATE TABLE IF NOT EXISTS adventure_meta (key TEXT PRIMARY KEY, value TEXT)",
    "CREATE TABLE IF NOT EXISTS adventure_recipes (recipe_id TEXT, recipe_sha256 TEXT, trial_id INTEGER, "
    "status TEXT CHECK (status IN ('PASSED_HARNESS','EXPLORE_CAPPED','RETIRED')), weight TEXT, "
    "added_at TEXT, PRIMARY KEY (recipe_id, recipe_sha256))",
    "CREATE TABLE IF NOT EXISTS adventure_fills (id INTEGER PRIMARY KEY, created_at TEXT, recipe_id TEXT, "
    "payload_json TEXT, tag TEXT NOT NULL DEFAULT 'ADVENTURE_NOT_OFFICIAL' CHECK (tag='ADVENTURE_NOT_OFFICIAL'))",
    "CREATE TABLE IF NOT EXISTS adventure_values (id INTEGER PRIMARY KEY, created_at TEXT, recipe_id TEXT, "
    "value TEXT, tag TEXT NOT NULL DEFAULT 'ADVENTURE_NOT_OFFICIAL' CHECK (tag='ADVENTURE_NOT_OFFICIAL'))",
)


class AdventureError(RuntimeError):
    pass


def open_adventure(path, official):
    """Create or open the Adventure database. Refuses the Official file and its directory."""
    path, official = Path(path).resolve(), Path(official).resolve()
    if path == official or path.parent == official.parent:
        raise AdventureError('ADVENTURE_MUST_HAVE_ITS_OWN_DIRECTORY')
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, isolation_level=None)
    for statement in SCHEMA:
        db.execute(statement)
    db.execute("INSERT OR IGNORE INTO adventure_meta VALUES ('role', ?)", (ROLE,))
    role = db.execute("SELECT value FROM adventure_meta WHERE key='role'").fetchone()[0]
    if role != ROLE:
        db.close()
        raise AdventureError('NOT_AN_ADVENTURE_DATABASE')
    return db


def admit(db, *, recipe_id, recipe_sha256, trial_id, verdict, explore=False, weight='0', added_at):
    """Only a harness PASS, or an explicit explore recipe within the 2% cap, may enter."""
    if not explore and verdict != 'PASS':
        raise AdventureError('ONLY_HARNESS_PASSES_ENTER_ADVENTURE')
    if explore and float(weight) > EXPLORE_CAP:
        raise AdventureError('EXPLORE_WEIGHT_ABOVE_CAP')
    db.execute('INSERT INTO adventure_recipes VALUES (?,?,?,?,?,?)',
               (recipe_id, recipe_sha256, trial_id, 'EXPLORE_CAPPED' if explore else 'PASSED_HARNESS', str(weight), added_at))
