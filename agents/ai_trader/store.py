"""The AI trader's own database and paper books. Never the Official database or its directory."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

D = Decimal
BOOKS = ('A', 'B', 'C')
MODES = ('WATCH_ONLY', 'PAPER', 'RETIRED')

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)",
    "CREATE TABLE IF NOT EXISTS books (book TEXT PRIMARY KEY, payload TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS tickets (id TEXT PRIMARY KEY, day TEXT, created_at TEXT, ticker TEXT, status TEXT, "
    "payload_json TEXT, checks_json TEXT, critic_json TEXT)",
    "CREATE TABLE IF NOT EXISTS operator_cards (id TEXT PRIMARY KEY, ticket_id TEXT, issued_at TEXT, expires_at TEXT, "
    "status TEXT DEFAULT 'PENDING', cut_fraction TEXT, decided_at TEXT)",
    "CREATE TABLE IF NOT EXISTS fills (id INTEGER PRIMARY KEY, at TEXT, book TEXT, ticker TEXT, side TEXT, quantity TEXT, "
    "price TEXT, mark TEXT, ticket_id TEXT, reason TEXT, realized_usd TEXT)",
    "CREATE TABLE IF NOT EXISTS book_values (id INTEGER PRIMARY KEY, at TEXT, day TEXT, book TEXT, value TEXT, "
    "api_cost_cum TEXT, vti TEXT, official TEXT)",
    "CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY, at TEXT, day TEXT, seat TEXT, model TEXT, reserved TEXT, "
    "actual TEXT, status TEXT)",
    "CREATE TABLE IF NOT EXISTS journal (id INTEGER PRIMARY KEY, at TEXT, kind TEXT, payload_json TEXT)",
    "CREATE TABLE IF NOT EXISTS management (id INTEGER PRIMARY KEY, at TEXT, day TEXT, book TEXT, ticker TEXT, action TEXT, reason TEXT)",
    "CREATE TABLE IF NOT EXISTS watch_cards (id INTEGER PRIMARY KEY, at TEXT, day TEXT, ticker TEXT, payload_json TEXT)",
)


class StoreError(RuntimeError):
    pass


@dataclass
class Book:
    name: str
    start: Decimal
    settled: Decimal
    unsettled: list = field(default_factory=list)     # [[amount, settle_day]]
    positions: dict = field(default_factory=dict)     # ticker -> position dict (strings)
    peak: Decimal = D(0)
    day: str = ''
    day_start_value: Decimal = D(0)
    week: str = ''
    week_start_value: Decimal = D(0)
    realized: Decimal = D(0)
    closed_trades: int = 0
    last_value: Decimal | None = None      # last recorded value (morning or 15:50), the baseline for the stops
    last_value_day: str = ''

    def to_json(self):
        return json.dumps({'name': self.name, 'start': str(self.start), 'settled': str(self.settled),
                           'unsettled': [[str(a), d] for a, d in self.unsettled], 'positions': self.positions,
                           'peak': str(self.peak), 'day': self.day, 'day_start_value': str(self.day_start_value),
                           'week': self.week, 'week_start_value': str(self.week_start_value),
                           'realized': str(self.realized), 'closed_trades': self.closed_trades,
                           'last_value': None if self.last_value is None else str(self.last_value),
                           'last_value_day': self.last_value_day})

    @classmethod
    def from_json(cls, text):
        r = json.loads(text)
        return cls(r['name'], D(r['start']), D(r['settled']), [[D(a), d] for a, d in r['unsettled']], r['positions'],
                   D(r['peak']), r['day'], D(r['day_start_value']), r['week'], D(r['week_start_value']),
                   D(r['realized']), r['closed_trades'],
                   None if r.get('last_value') is None else D(r['last_value']), r.get('last_value_day', ''))

    # ---------------------------------------------------------------- accounting
    def settle(self, today: str):
        keep = []
        for amount, day in self.unsettled:
            if day <= today:
                self.settled += amount
            else:
                keep.append([amount, day])
        self.unsettled = keep

    def value(self, marks: dict) -> Decimal:
        total = self.settled + sum((a for a, _ in self.unsettled), D(0))
        for t, p in self.positions.items():
            mark = marks.get(t)
            total += D(p['quantity']) * (D(str(mark)) if mark is not None else D(p['average_cost']))
        return total

    def roll(self, today: str, value: Decimal):
        """Start-of-session bookkeeping. The daily stop is measured from the last value recorded in an
        earlier session (yesterday's 15:50 or morning value), the weekly stop from the last value of the
        previous week, so an overnight gap counts."""
        week = date.fromisoformat(today).strftime('%G-W%V')
        prior = self.last_value if (self.last_value is not None and self.last_value_day < today) else value
        if self.day != today:
            self.day, self.day_start_value = today, prior
        if self.week != week:
            self.week, self.week_start_value = week, prior
        self.peak = max(self.peak, value)

    def mark(self, today: str, value: Decimal):
        self.last_value, self.last_value_day = value, today

    def buy(self, ticker, quantity: Decimal, price: Decimal, today: str, extra: dict):
        cost = quantity * price
        if cost > self.settled + D('0.000001'):
            raise StoreError('INSUFFICIENT_SETTLED_CASH')
        if ticker in self.positions:
            raise StoreError('PYRAMIDING_FORBIDDEN')
        self.settled -= cost
        self.positions[ticker] = {'quantity': str(quantity), 'average_cost': str(price), 'entry_day': today,
                                  'sessions_held': 0, 'unreviewed_days': 0, **{k: str(v) if isinstance(v, Decimal) else v for k, v in extra.items()}}

    def sell(self, ticker, quantity: Decimal, price: Decimal, settle_day: str):
        p = self.positions[ticker]
        held = D(p['quantity'])
        quantity = min(quantity, held)
        proceeds = quantity * price
        realized = quantity * (price - D(p['average_cost']))
        self.unsettled.append([proceeds, settle_day])
        self.realized += realized
        left = held - quantity
        if left <= D('0.000001'):
            del self.positions[ticker]
            self.closed_trades += 1
        else:
            p['quantity'] = str(left)
        return realized


class TraderStore:
    def __init__(self, path, official=None):
        self.path = Path(path).resolve()
        if official is not None:
            off = Path(official).resolve()
            if self.path == off or self.path.parent == off.parent:
                raise StoreError('AI_TRADER_MUST_HAVE_ITS_OWN_DIRECTORY')
        if (self.path.parent / 'agent.db').exists():
            raise StoreError('AI_TRADER_MUST_HAVE_ITS_OWN_DIRECTORY')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            for s in SCHEMA:
                db.execute(s)
            db.execute("INSERT OR IGNORE INTO meta VALUES ('role','ai_trader_paper_not_official')")
            db.execute("INSERT OR IGNORE INTO meta VALUES ('mode','WATCH_ONLY')")

    def connect(self):
        db = sqlite3.connect(self.path, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    # ---------------------------------------------------------------- meta / mode
    def meta(self, key, default=None):
        with self.connect() as db:
            row = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return row[0] if row else default

    def set_meta(self, key, value):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, value))

    def bind_spec(self, spec):
        pinned = self.meta('spec_sha256')
        if pinned and pinned != spec.sha256:
            raise StoreError('SPEC_CHANGED_THIS_IS_A_NEW_TRIAL')
        if not pinned:
            self.set_meta('spec_sha256', spec.sha256)
            self.set_meta('spec_id', spec.id)
            with self.connect() as db:
                for b in BOOKS:
                    db.execute('INSERT OR IGNORE INTO books VALUES (?,?)',
                               (b, Book(b, spec.capital, spec.capital, peak=spec.capital).to_json()))

    def mode(self):
        return self.meta('mode', 'WATCH_ONLY')

    def set_mode(self, mode, *, at: datetime, by: str, spec=None, official_first_run_completed=False):
        if mode not in MODES:
            raise StoreError('MODE_INVALID')
        if by != 'operator':
            raise StoreError('ONLY_THE_OPERATOR_CHANGES_MODE')
        if mode == 'PAPER':
            if spec is not None and at.date().isoformat() < spec.start_not_before:
                raise StoreError('PAPER_NOT_BEFORE_' + spec.start_not_before)
            if not official_first_run_completed:
                raise StoreError('START_CONDITION_OFFICIAL_RUN_NOT_CONFIRMED')
        self.set_meta('mode', mode)
        if mode == 'PAPER' and not self.meta('paper_started_at'):
            self.set_meta('paper_started_at', at.isoformat())
        self.journal('mode_changed', {'mode': mode, 'by': by}, at)

    # ---------------------------------------------------------------- books
    def book(self, name) -> Book:
        with self.connect() as db:
            row = db.execute('SELECT payload FROM books WHERE book=?', (name,)).fetchone()
        if row is None:
            raise StoreError('BOOKS_NOT_INITIALIZED')
        return Book.from_json(row[0])

    def save_book(self, book: Book):
        with self.connect() as db:
            db.execute('UPDATE books SET payload=? WHERE book=?', (book.to_json(), book.name))

    # ---------------------------------------------------------------- records
    def journal(self, kind, payload, at: datetime):
        with self.connect() as db:
            db.execute('INSERT INTO journal (at,kind,payload_json) VALUES (?,?,?)', (at.isoformat(), kind, json.dumps(payload, default=str)))

    def record_fill(self, at, book, ticker, side, qty, price, mark, ticket_id, reason, realized=None):
        with self.connect() as db:
            db.execute('INSERT INTO fills (at,book,ticker,side,quantity,price,mark,ticket_id,reason,realized_usd) VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (at.isoformat(), book, ticker, side, str(qty), str(price), str(mark), ticket_id, reason,
                        None if realized is None else str(realized)))

    def save_ticket(self, ticket_id, day, at, ticker, status, payload, checks=None, critic=None):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO tickets VALUES (?,?,?,?,?,?,?,?)',
                       (ticket_id, day, at.isoformat(), ticker, status, json.dumps(payload, default=str),
                        json.dumps(checks, default=str) if checks is not None else None,
                        json.dumps(critic, default=str) if critic is not None else None))

    def tickets(self, day=None):
        with self.connect() as db:
            q = 'SELECT * FROM tickets' + (' WHERE day=?' if day else '') + ' ORDER BY created_at'
            return [dict(r) for r in db.execute(q, (day,) if day else ())]

    def record_value(self, at, day, book, value, api_cost_cum, vti, official=None):
        with self.connect() as db:
            db.execute('INSERT INTO book_values (at,day,book,value,api_cost_cum,vti,official) VALUES (?,?,?,?,?,?,?)',
                       (at.isoformat(), day, book, str(value), str(api_cost_cum), None if vti is None else str(vti),
                        None if official is None else str(official)))

    def spent(self, day=None, since=None):
        with self.connect() as db:
            if day:
                rows = db.execute("SELECT actual, reserved, status FROM budget WHERE day=?", (day,)).fetchall()
            elif since:
                rows = db.execute("SELECT actual, reserved, status FROM budget WHERE at>=?", (since,)).fetchall()
            else:
                rows = db.execute("SELECT actual, reserved, status FROM budget").fetchall()
        total = D(0)
        for actual, reserved, status in rows:
            total += D(actual) if actual is not None else (D(reserved) if status == 'RESERVED' else D(0))
        return total
