"""Card inbox: one card shape for everything the desk may show you, plus your answers and a journal.

A card is never a recommendation and never an order. It lives in its own database (never the
Official one), and the Official scoreboard never reads it.

Rules enforced here:
* Sources: ``official_rule`` (the registered desk rule) and ``watch`` (S&P 500 watch notes) only.
  ``explore`` cards are refused until 2026-11-01, and after that only for recipes in the trial log.
* Numbers come from code. The AI may write prose (``opinion``, ``kills``) but not digits, and
  never words like "target" or "guaranteed". Facts are code-generated strings.
* The record shown on a card is computed from this journal; with no history it reads
  NO_RECORD_YET. A backtest is never shown as a streak.
* "I may copy live" is allowed only for a copyable card: an order-shaped card (not a watch note)
  whose cost fits under the $1,200 Agentic cash cap. It writes a copy acknowledgement
  (ticker, side, quantity, window) that is NOT yet enforced by the account tripwire.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

SOURCES = ('official_rule', 'watch', 'explore')
ANSWERS = ('paper_only', 'may_copy_live', 'skip')
EXPLORE_OPENS = date(2026, 11, 1)
AGENTIC_CASH_CAP_USD = Decimal('1200')
WATCH_PER_DAY = 5
LABEL = 'NOT A RECOMMENDATION — your click'
ACK_WINDOW = timedelta(hours=2)
# Off until the account tripwire reads copy_acks; the page and the front door refuse live copies meanwhile.
LIVE_COPY_ENABLED = False
BANNED = re.compile(r'\b(target|guarantee[sd]?|sure thing|can\'?t lose|moon|to the moon|good trade|great trade|\d+\s*x)\b', re.I)

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)",
    "CREATE TABLE IF NOT EXISTS cards (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, source TEXT NOT NULL, "
    "recipe_id TEXT NOT NULL, ticker TEXT NOT NULL, instrument TEXT NOT NULL, side TEXT, quantity TEXT, "
    "est_cost_usd TEXT, max_loss_usd TEXT, facts_json TEXT NOT NULL, kills TEXT NOT NULL, opinion TEXT, "
    "record_json TEXT NOT NULL, copyable INTEGER NOT NULL, copy_block_reason TEXT, label TEXT NOT NULL, "
    "expires_at TEXT, status TEXT NOT NULL DEFAULT 'OPEN')",
    "CREATE TABLE IF NOT EXISTS answers (card_id TEXT PRIMARY KEY REFERENCES cards(id), answer TEXT NOT NULL, "
    "answered_at TEXT NOT NULL, answered_by TEXT NOT NULL CHECK (answered_by='operator'))",
    "CREATE TABLE IF NOT EXISTS journal (id INTEGER PRIMARY KEY, card_id TEXT, recipe_id TEXT NOT NULL, event TEXT NOT NULL, "
    "at TEXT NOT NULL, payload_json TEXT)",
    "CREATE TABLE IF NOT EXISTS copy_acks (id INTEGER PRIMARY KEY, card_id TEXT NOT NULL, ticker TEXT NOT NULL, side TEXT NOT NULL, "
    "quantity TEXT NOT NULL, window_start TEXT NOT NULL, window_end TEXT NOT NULL, created_at TEXT NOT NULL, "
    "status TEXT NOT NULL DEFAULT 'DECLARED_NOT_ENFORCED')",
)


class CardError(ValueError):
    pass


def _dec(value):
    if value is None:
        return None
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise CardError('NUMBER_INVALID') from None
    if not out.is_finite() or out < 0:
        raise CardError('NUMBER_INVALID')
    return out


@dataclass(frozen=True)
class Card:
    id: str
    source: str
    recipe_id: str
    ticker: str
    instrument: str              # 'share' or a contract description built by code
    facts: tuple                 # code-generated strings
    kills: str                   # what invalidates it (prose, no digits)
    created_at: datetime
    side: str | None = None
    quantity: str | None = None
    est_cost_usd: str | None = None
    max_loss_usd: str | None = None
    opinion: str = ''            # AI opinion, tagged as such in every view (prose, no digits)
    expires_at: datetime | None = None
    record_hint: dict = field(default_factory=dict)

    def validate(self):
        if self.source not in SOURCES:
            raise CardError('SOURCE_INVALID')
        if self.source == 'explore' and self.created_at.date() < EXPLORE_OPENS:
            raise CardError('EXPLORE_FROZEN_UNTIL_2026_11_01')
        if not re.fullmatch(r'[A-Z][A-Z.]{0,5}', self.ticker or ''):
            raise CardError('TICKER_INVALID')
        if not self.facts or any(not isinstance(f, str) or not f for f in self.facts):
            raise CardError('FACTS_REQUIRED')
        for text, name in ((self.kills, 'KILLS'), (self.opinion, 'OPINION')):
            if re.search(r'\d', text or ''):
                raise CardError(f'{name}_MUST_NOT_CONTAIN_NUMBERS')
            if BANNED.search(text or ''):
                raise CardError(f'{name}_HYPE_NOT_ALLOWED')
        if not self.kills:
            raise CardError('KILLS_REQUIRED')
        if self.source == 'watch':
            if any(v is not None for v in (self.side, self.quantity, self.est_cost_usd, self.max_loss_usd)):
                raise CardError('WATCH_NOTES_ARE_NOT_ORDERS')
        else:
            if self.side not in ('buy', 'sell'):
                raise CardError('SIDE_REQUIRED')
            if _dec(self.quantity) in (None, Decimal(0)) or _dec(self.est_cost_usd) is None or _dec(self.max_loss_usd) is None:
                raise CardError('SIZE_COST_AND_MAX_LOSS_REQUIRED')
        return self

    def copy_status(self):
        if self.source == 'watch':
            return False, 'Watch notes are not orders.'
        if self.side == 'buy' and _dec(self.est_cost_usd) > AGENTIC_CASH_CAP_USD:
            return False, f'Needs more than the ${AGENTIC_CASH_CAP_USD:,.0f} Agentic cash cap.'
        return True, None


class CardStore:
    def __init__(self, path, official=None):
        self.path = Path(path).resolve()
        if official is not None:
            off = Path(official).resolve()
            if self.path == off or self.path.parent == off.parent:
                raise CardError('CARDS_MUST_HAVE_THEIR_OWN_DIRECTORY')
        if (self.path.parent / 'agent.db').exists():
            raise CardError('CARDS_MUST_HAVE_THEIR_OWN_DIRECTORY')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            for statement in SCHEMA:
                db.execute(statement)
            db.execute("INSERT OR IGNORE INTO meta VALUES ('role','cards_not_official')")

    def connect(self):
        db = sqlite3.connect(self.path, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    # ---------------------------------------------------------------- record (from the journal only)
    def record(self, recipe_id):
        with self.connect() as db:
            rows = db.execute("SELECT event, payload_json FROM journal WHERE recipe_id=? AND event='outcome'", (recipe_id,)).fetchall()
        if not rows:
            return {'status': 'NO_RECORD_YET'}
        outcomes = [json.loads(r['payload_json'] or '{}') for r in rows]
        wins = sum(1 for o in outcomes if Decimal(str(o.get('pnl_usd', 0))) > 0)
        zeros = sum(1 for o in outcomes if o.get('expired_worthless'))
        paid = sum((Decimal(str(o.get('premium_in_usd', 0))) for o in outcomes), Decimal(0))
        got = sum((Decimal(str(o.get('premium_out_usd', 0))) for o in outcomes), Decimal(0))
        excess = [Decimal(str(o['excess_vs_cash'])) for o in outcomes if o.get('excess_vs_cash') is not None]
        return {'status': 'RECORDED', 'fires': len(outcomes), 'wins': wins, 'losses': len(outcomes) - wins, 'zeros': zeros,
                'premium_out_over_in': str((got / paid).quantize(Decimal('0.01'))) if paid > 0 else None,
                'mean_excess_vs_cash': str((sum(excess) / len(excess)).quantize(Decimal('0.0001'))) if excess else None}

    # ---------------------------------------------------------------- cards
    def add(self, card: Card):
        card.validate()
        if card.source == 'watch':
            day = card.created_at.date().isoformat()
            with self.connect() as db:
                count = db.execute("SELECT count(*) FROM cards WHERE source='watch' AND substr(created_at,1,10)=?", (day,)).fetchone()[0]
            if count >= WATCH_PER_DAY:
                raise CardError('WATCH_LIMIT_FIVE_PER_DAY')
        copyable, reason = card.copy_status()
        record = self.record(card.recipe_id)
        with self.connect() as db:
            db.execute('INSERT INTO cards (id,created_at,source,recipe_id,ticker,instrument,side,quantity,est_cost_usd,max_loss_usd,'
                       'facts_json,kills,opinion,record_json,copyable,copy_block_reason,label,expires_at) '
                       'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (card.id, card.created_at.isoformat(), card.source, card.recipe_id, card.ticker, card.instrument, card.side,
                        card.quantity, card.est_cost_usd, card.max_loss_usd, json.dumps(list(card.facts)), card.kills, card.opinion,
                        json.dumps(record), int(copyable), reason, LABEL, card.expires_at.isoformat() if card.expires_at else None))
            db.execute('INSERT INTO journal (card_id,recipe_id,event,at,payload_json) VALUES (?,?,?,?,?)',
                       (card.id, card.recipe_id, 'issued', card.created_at.isoformat(), json.dumps({'source': card.source})))
        return record

    def answer(self, card_id, answer, *, at: datetime, by='operator'):
        if by != 'operator':
            raise CardError('ONLY_THE_OPERATOR_ANSWERS')
        if answer not in ANSWERS:
            raise CardError('ANSWER_INVALID')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            card = db.execute('SELECT * FROM cards WHERE id=?', (card_id,)).fetchone()
            if card is None:
                db.execute('ROLLBACK'); raise CardError('UNKNOWN_CARD')
            if db.execute('SELECT 1 FROM answers WHERE card_id=?', (card_id,)).fetchone():
                db.execute('ROLLBACK'); raise CardError('ALREADY_ANSWERED')
            if card['expires_at'] and at >= datetime.fromisoformat(card['expires_at']):
                db.execute('ROLLBACK'); raise CardError('CARD_EXPIRED')
            if answer == 'may_copy_live' and not card['copyable']:
                db.execute('ROLLBACK'); raise CardError('NOT_COPYABLE: ' + (card['copy_block_reason'] or ''))
            db.execute('INSERT INTO answers VALUES (?,?,?,?)', (card_id, answer, at.isoformat(), by))
            db.execute("UPDATE cards SET status='ANSWERED' WHERE id=?", (card_id,))
            db.execute('INSERT INTO journal (card_id,recipe_id,event,at,payload_json) VALUES (?,?,?,?,?)',
                       (card_id, card['recipe_id'], 'answered', at.isoformat(), json.dumps({'answer': answer})))
            if answer == 'may_copy_live':
                # Shape only: recorded before you act at the broker; NOT yet read by the account tripwire.
                db.execute('INSERT INTO copy_acks (card_id,ticker,side,quantity,window_start,window_end,created_at) VALUES (?,?,?,?,?,?,?)',
                           (card_id, card['ticker'], card['side'], card['quantity'], at.isoformat(), (at + ACK_WINDOW).isoformat(), at.isoformat()))
            db.execute('COMMIT')

    def record_outcome(self, card_id, *, at: datetime, pnl_usd, premium_in_usd=0, premium_out_usd=0, excess_vs_cash=None,
                       expired_worthless=False):
        """Called by code when a paper position from this card closes. Numbers only from the paper ledger."""
        with self.connect() as db:
            card = db.execute('SELECT recipe_id FROM cards WHERE id=?', (card_id,)).fetchone()
            if card is None:
                raise CardError('UNKNOWN_CARD')
            db.execute('INSERT INTO journal (card_id,recipe_id,event,at,payload_json) VALUES (?,?,?,?,?)',
                       (card_id, card['recipe_id'], 'outcome', at.isoformat(), json.dumps({
                           'pnl_usd': str(Decimal(str(pnl_usd))),
                           'premium_in_usd': str(_dec(premium_in_usd)), 'premium_out_usd': str(_dec(premium_out_usd)),
                           'excess_vs_cash': None if excess_vs_cash is None else str(excess_vs_cash),
                           'expired_worthless': bool(expired_worthless)})))

    def view(self, limit=100):
        with self.connect() as db:
            cards = [dict(r) for r in db.execute('SELECT * FROM cards ORDER BY created_at DESC LIMIT ?', (limit,))]
            answers = {r['card_id']: dict(r) for r in db.execute('SELECT * FROM answers')}
            journal = [dict(r) for r in db.execute('SELECT * FROM journal ORDER BY id DESC LIMIT 200')]
            acks = [dict(r) for r in db.execute('SELECT * FROM copy_acks ORDER BY id DESC LIMIT 50')]
        for c in cards:
            c['facts'] = json.loads(c.pop('facts_json'))
            c['record'] = json.loads(c.pop('record_json'))
            c['answer'] = answers.get(c['id'])
        return {'cards': cards, 'journal': journal, 'acks': acks}


def default_path(official_db):
    """robinhood-diagnostics/cards/cards.db beside the runtime folder (same convention as research outputs)."""
    return Path(official_db).resolve().parents[2] / 'robinhood-diagnostics' / 'cards' / 'cards.db'


def read_view(path, limit=100):
    """Read-only view for the dashboard; a missing database is an empty inbox, never created here."""
    path = Path(path)
    if not path.is_file():
        return {'cards': [], 'journal': [], 'acks': [], 'exists': False}
    db = sqlite3.connect(f'file:{path.resolve()}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        cards = [dict(r) for r in db.execute('SELECT * FROM cards ORDER BY created_at DESC LIMIT ?', (limit,))]
        answers = {r['card_id']: dict(r) for r in db.execute('SELECT * FROM answers')}
        journal = [dict(r) for r in db.execute('SELECT * FROM journal ORDER BY id DESC LIMIT 200')]
        acks = [dict(r) for r in db.execute('SELECT * FROM copy_acks ORDER BY id DESC LIMIT 50')]
    finally:
        db.close()
    for c in cards:
        c['facts'] = json.loads(c.pop('facts_json'))
        c['record'] = json.loads(c.pop('record_json'))
        c['answer'] = answers.get(c['id'])
    return {'cards': cards, 'journal': journal, 'acks': acks, 'exists': True}
