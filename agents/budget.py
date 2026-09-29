from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo


ET = ZoneInfo("America/New_York")
D = Decimal


class BudgetUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class AIInvocationDecision:
    invoke: bool
    reason: str
    candidate_ids: tuple[str, ...]
    reserved_cost_usd: Decimal = D("0")


class AIInvocationGate:
    def evaluate(self, discovery: list[dict], holdings: list[dict]) -> AIInvocationDecision:
        candidates = tuple(
            str(row["candidate_id"])
            for row in discovery
            if row.get("qualified") is True and row.get("asset_class") == "stock"
        )
        if candidates:
            return AIInvocationDecision(True, "QUALIFIED_AI_ELIGIBLE_CANDIDATE", candidates)
        positions = tuple(
            str(row["position_id"])
            for row in holdings
            if row.get("qualitative_review_required") is True
        )
        if positions:
            return AIInvocationDecision(True, "HOLDING_QUALITATIVE_REVIEW_REQUIRED", positions)
        return AIInvocationDecision(False, "AI_NOT_NEEDED", ())


class BudgetAllocator:
    run_ceiling = D("0.40")
    monthly_credit = D("1.65")
    carry_cap = D("5.00")
    annual_ceiling = D("19.80")
    stage_reservations = {
        "research": D("0.03"),
        "portfolio": D("0.05"),
        "critic": D("0.11"),
    }
    degradation_order = (
        "drop_news_sources_after_second_corroboration",
        "drop_research_candidates_ranked_6_through_8",
        "drop_research_candidate_ranked_5",
        "drop_optional_cross_candidate_narrative_and_optional_insider_enrichment",
        "drop_all_new_entry_research_and_run_holdings_plus_deterministic_baselines_only",
    )

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS ai_budget_months (
                lane TEXT NOT NULL, month TEXT NOT NULL, opening TEXT NOT NULL,
                PRIMARY KEY(lane,month))"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS ai_budget_reservations (
                id TEXT PRIMARY KEY, lane TEXT NOT NULL, stage TEXT NOT NULL,
                day TEXT NOT NULL, month TEXT NOT NULL, amount TEXT NOT NULL,
                settled INTEGER NOT NULL DEFAULT 0)"""
            )

    def _month(self, now: datetime) -> tuple[str, str, str]:
        if now.tzinfo is None:
            raise ValueError("budget timestamp must be timezone-aware")
        local = now.astimezone(ET)
        return local.date().isoformat(), f"{local.year:04d}-{local.month:02d}", str(local.year)

    def _ensure_month(self, db, lane: str, month: str) -> Decimal:
        row = db.execute(
            "SELECT opening FROM ai_budget_months WHERE lane=? AND month=?", (lane, month)
        ).fetchone()
        if row:
            return D(row[0])
        year = month[:4]
        prior = db.execute(
            """SELECT month,opening FROM ai_budget_months
            WHERE lane=? AND substr(month,1,4)=? AND month<? ORDER BY month DESC LIMIT 1""",
            (lane, year, month),
        ).fetchone()
        carry = D("0")
        if prior:
            spent = sum(
                (D(row[0]) for row in db.execute(
                    "SELECT amount FROM ai_budget_reservations WHERE lane=? AND month=?",
                    (lane, prior[0]),
                )),
                D("0"),
            )
            carry = min(self.carry_cap, max(D("0"), D(prior[1]) - spent))
        opening = carry + self.monthly_credit
        db.execute("INSERT INTO ai_budget_months VALUES (?,?,?)", (lane, month, str(opening)))
        return opening

    def available(self, now: datetime, *, lane: str) -> Decimal:
        if lane not in {"A", "B"}:
            raise ValueError("unknown lane")
        _, month, _ = self._month(now)
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            opening = self._ensure_month(db, lane, month)
            spent = sum(
                (D(row[0]) for row in db.execute(
                    "SELECT amount FROM ai_budget_reservations WHERE lane=? AND month=?",
                    (lane, month),
                )),
                D("0"),
            )
            return opening - spent

    def reserve(self, now: datetime, *, lane: str, stage: str, amount: Decimal) -> str:
        amount = D(amount)
        if not amount.is_finite() or amount <= 0:
            raise ValueError("invalid budget reservation")
        day, month, year = self._month(now)
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            opening = self._ensure_month(db, lane, month)
            month_spend = sum(
                (D(row[0]) for row in db.execute(
                    "SELECT amount FROM ai_budget_reservations WHERE lane=? AND month=?",
                    (lane, month),
                )), D("0")
            )
            day_spend = sum(
                (D(row[0]) for row in db.execute(
                    "SELECT amount FROM ai_budget_reservations WHERE lane=? AND day=?",
                    (lane, day),
                )), D("0")
            )
            year_spend = sum(
                (D(row[0]) for row in db.execute(
                    "SELECT amount FROM ai_budget_reservations WHERE lane=? AND substr(month,1,4)=?",
                    (lane, year),
                )), D("0")
            )
            if day_spend + amount > self.run_ceiling:
                raise BudgetUnavailable("official daily AI ceiling is unavailable")
            if month_spend + amount > opening:
                raise BudgetUnavailable("monthly AI allowance is unavailable")
            if year_spend + amount > self.annual_ceiling:
                raise BudgetUnavailable("annual AI cost target is unavailable")
            key = uuid4().hex
            db.execute(
                "INSERT INTO ai_budget_reservations VALUES (?,?,?,?,?,?,0)",
                (key, lane, stage, day, month, str(amount)),
            )
            return key

    def settle(self, reservation_id: str, *, actual: Decimal) -> None:
        actual = D(actual)
        if not actual.is_finite() or actual < 0:
            raise ValueError("invalid actual cost")
        with sqlite3.connect(self.path) as db:
            changed = db.execute(
                "UPDATE ai_budget_reservations SET amount=?,settled=1 WHERE id=? AND settled=0",
                (str(actual), reservation_id),
            ).rowcount
            if changed != 1:
                raise BudgetUnavailable("budget reservation is missing or already settled")

    def settle_attempts(self, cycle_id, reservations, attempts):
        """Atomic, replay-safe settlement of this cycle; historical rows untouched."""
        from agents.cost_allocation import _exact_sum
        unique = {}
        for row in attempts:
            key = (row['role'], row['attempt_id'])
            encoded = json.dumps(row, sort_keys=True)
            if key in unique and unique[key] != encoded:
                raise ValueError('ALLOCATION_CONFLICT')
            unique[key] = encoded
        pairs = {(r['stage'],r['lane']) for r in reservations}
        totals = {pair:[] for pair in pairs}
        for encoded in unique.values():
            row = json.loads(encoded)
            for lane, value in row['allocations'].items():
                amount = D(value)
                if not amount.is_finite() or amount < 0 or (row['role'],lane) not in pairs:
                    raise ValueError('INVALID_ATTEMPT_ALLOCATION')
                totals[(row['role'],lane)].append(amount)
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS ai_cost_settlements (cycle_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            payload = json.dumps({'reservations':sorted(r['id'] for r in reservations),
                                  'attempts':sorted(unique.values())}, sort_keys=True)
            prior = db.execute('SELECT payload FROM ai_cost_settlements WHERE cycle_id=?',(cycle_id,)).fetchone()
            if prior:
                if prior[0] != payload: raise ValueError('ALLOCATION_CONFLICT')
                return
            for row in reservations:
                actual = _exact_sum([D(0), *totals[(row['stage'],row['lane'])]])
                existing = db.execute('SELECT lane,stage,amount,settled FROM ai_budget_reservations WHERE id=?',(row['id'],)).fetchone()
                if not existing or existing[0:2] != (row['lane'],row['stage']) or existing[3]:
                    raise BudgetUnavailable('budget reservation is missing or already settled')
                if actual > D(existing[2]): raise BudgetUnavailable('allocation exceeds reserved lane bound')
                db.execute('UPDATE ai_budget_reservations SET amount=?,settled=1 WHERE id=?',(str(actual),row['id']))
            db.execute('INSERT INTO ai_cost_settlements VALUES (?,?)',(cycle_id,payload))
