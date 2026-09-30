"""Three-arm desk-policy ETF issuance (v1.5, inert until byte-pinned activation)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from broker.models import Quote
from config.loader import load_config

NOW = datetime(2026, 10, 1, 14, 0, 30, tzinfo=timezone.utc)  # 10:00:30 EDT, a session day
SIGNAL = {'instrument': 'SOXX', 'side': 'buy', 'strategy': 'momentum_rotation_126d_trend200_top1',
          'strength': '0.73', 'thesis': 'Top 126-session momentum above its 200-session average.',
          'good_if': 'Stays above the 200-session average.', 'invalidation': 'Closes at or below the 200-session average.'}


def runtime(tmp_path):
    from agents.inbox import PaperInbox
    config = load_config('config/settings.yaml')
    risk = config.risk.model_copy(update={'agentic_account_id': 'agentic-1',
                                          'instrument_whitelist': sorted({*config.risk.instrument_whitelist, 'SOXX'})})
    config = config.model_copy(update={'risk': risk})
    return PaperInbox(tmp_path / 'paper.db', config), config


def snapshot(bid='560.50', ask='560.90', at=NOW, volume=D('200000000')):
    return {'quotes': {'SOXX': Quote(ticker='SOXX', bid=D(bid), ask=D(ask), timestamp=at)},
            'vols': {'SOXX': (D('0.30'), at - timedelta(hours=18))},
            'contracts': {}, 'median_dollar_volume_20d': {'SOXX': volume}}


@pytest.fixture
def interim(monkeypatch):
    import agents.etf_issuer as issuer
    monkeypatch.setattr(issuer, 'LIQUIDITY_INTERIM_LIVE_SPREAD', True)


def issue(inbox, config, snap, **kw):
    from agents.etf_issuer import issue_desk_entry
    return issue_desk_entry(inbox, config, signal=SIGNAL, snapshot=snap, evaluated_at=NOW, now=NOW,
                            cycle_id='cyc1', **kw)


def test_three_arms_fractional_fills_and_desk_card(tmp_path, interim):
    inbox, config = runtime(tmp_path)
    results = {r['arm']: r for r in issue(inbox, config, snapshot())}
    assert results['agent_alone']['status'] == 'filled'
    assert results['deterministic_no_ai']['status'] == 'filled'
    assert results['with_approvals']['status'] == 'PENDING'
    qty = D(results['agent_alone']['quantity'])
    assert qty.as_tuple().exponent == -6 and 0 < qty < 1          # fractional slice of a $560 ETF
    assert qty * D('560.90') <= D('125')                          # never above the 25% position cap
    for arm in ('agent_alone', 'deterministic_no_ai'):
        pos = inbox.state('A', arm)['positions']['SOXX']
        assert D(pos['quantity']) == qty
    assert inbox.state('A', 'with_approvals')['positions'] == {}   # approval arm waits for YES
    card = inbox.cards()[0]
    assert card['author'] == 'Desk rule (no AI)' and 'Not an AI pick' in card['body']
    assert card['fill_policy'] == 'fresh_quote_at_approval'
    assert card['expires'] == '2026-10-01T19:30:00+00:00'          # 15:30 ET cutoff


def test_yes_waits_for_fresh_quote_then_fills_within_limit(tmp_path, interim):
    inbox, config = runtime(tmp_path)
    issue(inbox, config, snapshot())
    card = inbox.cards()[0]
    later = NOW + timedelta(minutes=30)
    assert inbox.decide(card['id'], 'YES', later)['status'] == 'APPROVED_AWAITING_FILL'
    assert inbox.state('A', 'with_approvals')['positions'] == {}   # never filled at the stale 10:00 quote
    # Stale quote: keep waiting.
    stale = {'SOXX': Quote(ticker='SOXX', bid=D('560.5'), ask=D('560.9'), timestamp=later - timedelta(minutes=5))}
    assert inbox.fill_approved_desk_cards(stale, later)[0]['reason'] == 'NO_FRESH_QUOTE'
    # Fresh but above the registered limit: keep waiting, never chase.
    high = {'SOXX': Quote(ticker='SOXX', bid=D('566'), ask=D('566.5'), timestamp=later)}
    assert inbox.fill_approved_desk_cards(high, later)[0]['reason'] == 'ABOVE_LIMIT'
    fresh = {'SOXX': Quote(ticker='SOXX', bid=D('559.9'), ask=D('560.1'), timestamp=later)}
    assert inbox.fill_approved_desk_cards(fresh, later)[0]['status'] == 'YES'
    filled = inbox.cards()[0]
    assert filled['approval_fill']['origin'] == 'approval_fresh_quote'
    assert D(inbox.state('A', 'with_approvals')['positions']['SOXX']['average_cost']) == D('560.1')


def test_approved_card_closes_unfilled_after_cutoff(tmp_path, interim):
    inbox, config = runtime(tmp_path)
    issue(inbox, config, snapshot())
    card = inbox.cards()[0]
    inbox.decide(card['id'], 'YES', NOW + timedelta(minutes=5))
    after = datetime(2026, 10, 1, 19, 31, tzinfo=timezone.utc)
    assert inbox.fill_approved_desk_cards({}, after)[0]['status'] == 'APPROVED_NOT_FILLED'
    assert inbox.state('A', 'with_approvals')['positions'] == {}


def test_without_interim_rule_or_history_liquidity_blocks_every_arm(tmp_path):
    inbox, config = runtime(tmp_path)
    results = issue(inbox, config, snapshot())
    assert {r['reason'] for r in results} == {'LIQUIDITY_EVIDENCE_MISSING'}
    assert inbox.cards() == []


def test_missing_dollar_volume_blocks(tmp_path, interim):
    inbox, config = runtime(tmp_path)
    snap = snapshot(); snap['median_dollar_volume_20d'] = {}
    assert {r['reason'] for r in issue(inbox, config, snap)} == {'LIQUIDITY_EVIDENCE_MISSING'}


def test_wide_live_spread_blocks(tmp_path, interim):
    inbox, config = runtime(tmp_path)
    assert {r['reason'] for r in issue(inbox, config, snapshot(bid='557', ask='561'))} == {'LIQUIDITY_BLOCKED'}


def test_ai_stock_pick_takes_the_slot(tmp_path, interim):
    inbox, config = runtime(tmp_path)
    results = issue(inbox, config, snapshot(), approved_ai_stock_pick=True, entry_slot_used=True)
    assert {r['reason'] for r in results} == {'AI_STOCK_SLOT_PRECEDENCE'}


def test_recorded_20_session_median_spread_is_used_when_available(tmp_path):
    from agents.etf_issuer import record_spreads, median_recorded_spread
    inbox, _ = runtime(tmp_path)
    with inbox.connect() as db:
        for i in range(20):
            day = (NOW - timedelta(days=30 - i)).date().isoformat()
            record_spreads(db, day, {'SOXX': Quote(ticker='SOXX', bid=D('100'), ask=D('100.10'), timestamp=NOW)}, NOW, 'c')
        assert median_recorded_spread(db, 'SOXX', NOW.date().isoformat()) < D('.003')
        # first observation of the day is never overwritten
        record_spreads(db, (NOW - timedelta(days=11)).date().isoformat(),
                       {'SOXX': Quote(ticker='SOXX', bid=D('90'), ask=D('100'), timestamp=NOW)}, NOW, 'c2')
        assert median_recorded_spread(db, 'SOXX', NOW.date().isoformat()) < D('.003')


def test_activation_is_byte_pinned_signed_amendment_over_unchanged_base(tmp_path):
    import yaml
    from agents.v15_activation import v15_active, registration_sha256, AMENDMENT_NAME
    base = tmp_path / 'preregistration.yaml'
    base.write_text('registration: {version: 1.4.2}\n')
    def amendment(status, base_sha):
        path = tmp_path / AMENDMENT_NAME
        path.write_text(yaml.safe_dump({'amendment': {'base_sha256': base_sha,
                                                      'operator_signature': {'status': status}}}))
        return registration_sha256(path)
    digest = amendment('SIGNED', registration_sha256(base))
    assert not v15_active(tmp_path, NOW)                                              # constants unset
    assert v15_active(tmp_path, NOW, approved_sha256=digest, effective_from=NOW)
    assert not v15_active(tmp_path, NOW, approved_sha256=digest, effective_from=NOW + timedelta(days=1))
    unsigned = amendment('PENDING', registration_sha256(base))
    assert not v15_active(tmp_path, NOW, approved_sha256=unsigned, effective_from=NOW)
    wrong_base = amendment('SIGNED', '0' * 64)
    assert not v15_active(tmp_path, NOW, approved_sha256=wrong_base, effective_from=NOW)
    digest = amendment('SIGNED', registration_sha256(base))
    base.write_text('registration: {version: 1.4.2} # edited\n')                     # base changed
    assert not v15_active(tmp_path, NOW, approved_sha256=digest, effective_from=NOW)


def test_repository_amendment_is_signed_pinned_and_effective_thursday():
    from pathlib import Path
    from agents.v15_activation import v15_active
    root = Path(__file__).resolve().parents[1]
    thursday = datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc)
    assert v15_active(root, thursday)
    assert not v15_active(root, datetime(2026, 10, 1, 13, 29, tzinfo=timezone.utc))   # before 09:30 ET
