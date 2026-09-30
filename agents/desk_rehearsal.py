"""Operator-run, read-only dress rehearsal of the v1.5 desk-policy ETF path.

Uses live read-only quotes/history via the existing proxy (approved reads only),
the official DB strictly mode=ro (paper-account states copied into memory), and
a brand-new disposable desk database under --output-dir for all issuance.
No official writes, no services, no model calls, no broker writes.

Rehearsal-only overrides, reported explicitly:
  * the 10:00-10:20 official-window check is treated as "market open now";
  * the v1.5 interim live-spread liquidity rule is on (operator-approved 11:28 ET),
    because v1.5 is not yet activated on the installed runtime.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


def run(official, config, output_dir, *, reader_factory=None, now=None, approve_card=True):
    from agents import rehearsal
    from agents.daily_cycle import market_snapshot, desk_policy_entry, ET
    from agents.inbox import PaperInbox, PAPER_TRACKS
    from agents.operator import MarketSchedule
    import agents.etf_issuer as issuer
    import agents.etf_desk_policy as policy
    from research.strategy_signals import ETF_UNIVERSE, evaluate_daily_signals

    before = rehearsal.official_digest(official)
    isolated = rehearsal.prepare(official, output_dir, config)          # fresh private dir, write-denied official copy
    now = now or datetime.now(timezone.utc)
    if not MarketSchedule().should_run(now, asset_class='etf', stage=1):
        return {'status': 'NOT_RUN', 'reason': 'MARKET_CLOSED', 'official_records_unchanged': True}
    reader = (reader_factory or (lambda p: __import__('agents.market_reader', fromlist=['LiveReader']).LiveReader(p, config)))(isolated.path)
    try:
        reads = reader.collect(now, {})
        snapshot = market_snapshot(reads, config, now, require_live_identity=True)
        collected_at = datetime.now(timezone.utc) if reader_factory is None else now
        closes = snapshot['session_closes']
        signals = evaluate_daily_signals(closes, ETF_UNIVERSE & config.risk.instrument_whitelist,
                                         now.astimezone(ET).date())
        fresh = {s for s, q in snapshot['quotes'].items()
                 if not q.halted and 0 <= (collected_at - q.timestamp).total_seconds() <= config.risk.max_quote_age_seconds}
        desk = PaperInbox(Path(output_dir) / 'desk.db', config)
        with desk.connect() as db:                                     # seed with official paper state copy
            for (lane, track), state in isolated._states.items():
                if track in PAPER_TRACKS:
                    db.execute('UPDATE paper_accounts SET payload=? WHERE lane=? AND track=?',
                               (json.dumps(state), lane, track))
        original_classify, original_interim = MarketSchedule.classify, issuer.LIQUIDITY_INTERIM_LIVE_SPREAD
        MarketSchedule.classify = lambda self, moment: MarketSchedule.State.TRADING_WINDOW
        issuer.LIQUIDITY_INTERIM_LIVE_SPREAD = True
        try:
            signal_map = {str(s['instrument']): s for s in signals['signals']}
            desk_results = desk_policy_entry(desk, config, snapshot, signal_map, fresh, collected_at,
                                             'rehearsal-' + collected_at.strftime('%H%M%S'), enabled=True) or []
            approval = []
            cards = [c for c in desk.cards() if c['status'] == 'PENDING']
            if approve_card and cards:
                decided = datetime.now(timezone.utc) if reader_factory is None else now
                desk.decide(cards[0]['id'], 'YES', decided)
                refreshed = issuer.quotes_from_reads(reader.refresh(decided, [cards[0]['proposal']['ticker']], []))
                approval = desk.fill_approved_desk_cards(refreshed, datetime.now(timezone.utc) if reader_factory is None else now)
        finally:
            MarketSchedule.classify, issuer.LIQUIDITY_INTERIM_LIVE_SPREAD = original_classify, original_interim
    finally:
        reader.close()
    arms = {track: {k: v for k, v in desk.state('A', track).items() if k in {'settled_cash', 'positions'}}
            for track in PAPER_TRACKS}
    report = {
        'status': 'COMPLETED', 'rehearsal': 'desk_policy_etf', 'collected_at': collected_at.isoformat(),
        'overrides': ['official_window_treated_as_open_now', 'interim_live_spread_rule_on'],
        'quote_count': len(snapshot['quotes']), 'fresh_quote_count': len(fresh),
        'etf_signals': [{k: s.get(k) for k in ('instrument', 'strategy', 'strength')} for s in signals['signals']
                        if str(s['instrument']) in ETF_UNIVERSE],
        'median_dollar_volume_20d': {k: str(v) for k, v in snapshot.get('median_dollar_volume_20d', {}).items()},
        'desk_results': desk_results, 'approval_fill': approval,
        'cards': [{k: c.get(k) for k in ('id', 'status', 'author', 'limit_price', 'expires')} for c in desk.cards()],
        'paper_arms_after': arms, 'model_calls': 0, 'api_cost_usd': '0',
        'real_orders': 'blocked', 'official_parent': isolated.parent_official_run_id,
    }
    report['official_records_unchanged'] = before == rehearsal.official_digest(official)
    if not report['official_records_unchanged']:
        report['status'] = 'ISOLATION_VERIFICATION_FAILED'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--official-database', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    from config.loader import load_config
    config = load_config(args.config)
    config.validate_runtime_ready()
    report = run(args.official_database, config, args.output_dir)
    text = json.dumps(report, indent=2, default=str)
    (Path(args.output_dir) / 'desk-report.json').write_text(text + '\n')
    print(text)
    return 0 if report['status'] == 'COMPLETED' and report['official_records_unchanged'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
