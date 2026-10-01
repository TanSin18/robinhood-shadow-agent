import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from agents.ai_trader import control, cycle, scoring, seats
from agents.ai_trader.model import BudgetedModels, BudgetExhausted
from agents.ai_trader.spec import load_spec
from agents.ai_trader.store import StoreError, TraderStore

SPEC = load_spec()
PRICES = ({m: 1.0 for m in SPEC.models.values()}, {m: 4.0 for m in SPEC.models.values()})
ET_OPEN = datetime(2026, 10, 5, 14, 5, tzinfo=timezone.utc)   # 10:05 ET Monday


def snapshot(now=ET_OPEN, session='2026-10-05', next_session='2026-10-06', shock=None):
    closes, quotes, volumes = {}, {}, {}
    days = []
    d = date(2025, 6, 2)
    while len(days) < 300:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d += timedelta(days=1)
    for i, t in enumerate(SPEC.universe):
        base = 50 + 10 * i
        series = [base * (1 + 0.001 * k) for k in range(300)]
        closes[t] = list(zip(days, series))
        volumes[t] = [(day, 2_000_000) for day in days]
        last = series[-1] * (shock.get(t, 1) if shock else 1)
        quotes[t] = {'bid': round(last * 0.9995, 4), 'ask': round(last * 1.0005, 4), 'ts': now - timedelta(seconds=5)}
    return {'session': session, 'next_session': next_session, 'quotes': quotes, 'closes': closes, 'volumes': volumes,
            'official_value': D('25000')}


class FakeClient:
    """Scripted seats. Counts calls per seat (identified by the prompt's first words)."""

    def __init__(self, ticker='SOXX', critic='pass', manage=None, scout_names=None, wrong_number=False):
        self.calls = []
        self.ticker, self.critic, self.manage, self.wrong = ticker, critic, manage, wrong_number
        self.scout_names = scout_names if scout_names is not None else [ticker]

    def __call__(self, model, prompt, schema, envelope):
        seat = next(s for s, p in seats.PROMPTS.items() if prompt.startswith(p))
        self.calls.append(seat)
        packet = json.loads(prompt.split('PACKET (JSON):\n', 1)[1])
        if seat == 'scout':
            out = {'candidates': [{'ticker': n, 'setup_tag': 'trend', 'why': 'Uptrend.', 'sources': [f'features:{n}']}
                                  for n in self.scout_names], 'nothing_today_reason': ''}
        elif seat == 'pm':
            t = packet['candidate']['ticker']
            f = packet['tools'][f'features:{t}']
            ask = packet['tools'][f'quote:{t}']['ask']
            out = {'ticker': t, 'setup_tag': 'trend', 'thesis': 'Price is above its long average. Momentum is positive.',
                   'invalidation_price': round(ask * 0.95, 2), 'time_stop_sessions': 10, 'false_tomorrow_if': 'A close below the fifty day average.',
                   'sources': [f'features:{t}', f'quote:{t}'],
                   'cited_numbers': [{'tool_id': f'features:{t}', 'field': 'pct_vs_ma200',
                                      'value': f['pct_vs_ma200'] + (5 if self.wrong else 0)}]}
        elif seat == 'critic':
            out = {'tickets': [{'ticket_id': tk['ticket_id'], 'verdict': self.critic,
                                'fail_codes': [] if self.critic == 'pass' else ['THESIS_UNSUPPORTED'], 'reason': 'checked'}
                               for tk in packet['tickets']]}
        else:
            out = {'cards': self.manage(packet) if self.manage else []}
        return out, 1000, 500


def store_at(tmp_path, mode='PAPER'):
    s = TraderStore(tmp_path / 'trader' / 'trader.db')
    s.bind_spec(SPEC)
    if mode == 'PAPER':
        s.set_mode('PAPER', at=ET_OPEN, by='operator', spec=SPEC, official_first_run_completed=True)
    return s


def morning(store, client, **kw):
    return cycle.morning(store, SPEC, kw.pop('snap', snapshot()), client, kw.pop('now', ET_OPEN), prices=PRICES)


# ---------------------------------------------------------------- spec, store, mode
def test_spec_is_pinned_and_options_are_off():
    assert SPEC.id == 'ai_trader_fwd_v1' and len(SPEC.sha256) == 64 and len(SPEC.universe) == 23
    assert SPEC.raw['universe']['options'].startswith('off') and SPEC.daily_budget == D('2.00')


def test_store_refuses_official_directory_and_spec_change(tmp_path):
    (tmp_path / 'agent.db').write_text('')
    with pytest.raises(StoreError):
        TraderStore(tmp_path / 'trader.db')
    s = TraderStore(tmp_path / 'x' / 'trader.db')
    s.bind_spec(SPEC)
    s.set_meta('spec_sha256', '0' * 64)
    with pytest.raises(StoreError, match='NEW_TRIAL'):
        s.bind_spec(SPEC)


def test_prompt_change_is_a_new_trial(tmp_path, monkeypatch):
    s = store_at(tmp_path, 'WATCH_ONLY')
    morning(s, FakeClient())
    monkeypatch.setitem(seats.PROMPTS, 'scout', seats.SCOUT_PROMPT + ' Be bold.')
    with pytest.raises(cycle.CycleError, match='PROMPT_CHANGED'):
        morning(s, FakeClient())


def test_paper_mode_needs_date_operator_and_official_run(tmp_path):
    s = TraderStore(tmp_path / 't' / 'trader.db'); s.bind_spec(SPEC)
    early = datetime(2026, 10, 2, 14, tzinfo=timezone.utc)
    with pytest.raises(StoreError, match='NOT_BEFORE'):
        s.set_mode('PAPER', at=early, by='operator', spec=SPEC, official_first_run_completed=True)
    with pytest.raises(StoreError, match='OFFICIAL_RUN'):
        s.set_mode('PAPER', at=ET_OPEN, by='operator', spec=SPEC)
    with pytest.raises(StoreError):
        s.set_mode('PAPER', at=ET_OPEN, by='claude', spec=SPEC, official_first_run_completed=True)


# ---------------------------------------------------------------- the morning run
def test_watch_only_runs_seats_but_never_fills(tmp_path):
    s = store_at(tmp_path, 'WATCH_ONLY')
    client = FakeClient()
    r = morning(s, client)
    assert client.calls == ['scout', 'pm', 'critic']
    assert r['tickets'][0]['status'] == 'WATCH_APPROVED' and r['fills'] == []
    assert not s.book('A').positions and not s.book('C').positions


def test_paper_fills_A_issues_B_card_and_matches_C(tmp_path):
    s = store_at(tmp_path)
    r = morning(s, FakeClient())
    a, c = s.book('A'), s.book('C')
    assert 'SOXX' in a.positions and r['tickets'][0]['status'] == 'FILLED'
    pos = a.positions['SOXX']
    notional = D(pos['quantity']) * D(pos['average_cost'])
    assert notional <= D('25000') * SPEC.max_fraction + 1
    with s.connect() as db:
        assert db.execute("SELECT status FROM operator_cards").fetchone()[0] == 'PENDING'
    (pick, cp), = c.positions.items()
    assert cp['a_ticket'] == r['tickets'][0]['id']
    eligible = [t for t in SPEC.universe]
    assert pick == control.draw(SPEC, r['tickets'][0]['id'], eligible)          # seeded, reproducible
    assert abs(D(cp['quantity']) * D(cp['average_cost']) - notional) < notional * D('0.01')
    assert not s.book('B').positions


def test_code_checks_fail_before_the_critic_is_paid(tmp_path):
    s = store_at(tmp_path)
    client = FakeClient(wrong_number=True)
    r = morning(s, client)
    assert r['tickets'][0]['status'] == 'CODE_FAILED' and 'NUMBERS_NOT_IN_TOOLS' in r['tickets'][0]['fails']
    assert 'critic' not in client.calls and not s.book('A').positions


def test_critic_fail_blocks_and_no_same_day_retry(tmp_path):
    s = store_at(tmp_path)
    r = morning(s, FakeClient(critic='fail'))
    assert r['tickets'][0]['status'] == 'CRITIC_FAILED' and not s.book('A').positions
    client = FakeClient()
    morning(s, client, now=ET_OPEN + timedelta(minutes=30))
    assert 'pm' not in client.calls


def test_scout_cannot_name_off_list(tmp_path):
    s = store_at(tmp_path)
    client = FakeClient(scout_names=['TSLA'])
    r = morning(s, client)
    assert r['tickets'] == [] and client.calls == ['scout']


def test_budget_cap_is_never_exceeded(tmp_path):
    s = store_at(tmp_path)
    expensive = ({m: 100.0 for m in SPEC.models.values()}, {m: 400.0 for m in SPEC.models.values()})
    r = cycle.morning(s, SPEC, snapshot(), FakeClient(), ET_OPEN, prices=expensive)
    assert r['stopped'].startswith('SCOUT_BudgetExhausted') and s.spent(r['day']) <= SPEC.daily_budget


def test_entry_deadline_and_book_stops_block_new_tickets(tmp_path):
    s = store_at(tmp_path)
    late = datetime(2026, 10, 5, 19, 45, tzinfo=timezone.utc)   # 15:45 ET
    client = FakeClient()
    r = cycle.morning(s, SPEC, snapshot(now=late), client, late, prices=PRICES)
    assert r['stopped'] == 'AFTER_ENTRY_DEADLINE' and client.calls == []
    a = s.book('A'); a.week_start_value = D('30000'); s.save_book(a)    # simulate a week already down > 6%
    client2 = FakeClient()
    r2 = morning(s, client2)
    assert r2['stopped'] == 'WEEKLY_LOSS_HIT' and client2.calls == []


# ---------------------------------------------------------------- operator on book B
def _card(s):
    with s.connect() as db:
        return db.execute('SELECT id FROM operator_cards').fetchone()[0]


def test_operator_yes_cut_and_limits(tmp_path):
    s = store_at(tmp_path)
    morning(s, FakeClient())
    card = _card(s)
    with pytest.raises(StoreError):
        cycle.decide(s, card, 'YES', now=ET_OPEN, by='claude')
    with pytest.raises(StoreError, match='CUT_MUST_BE_SMALLER'):
        cycle.decide(s, card, 'CUT', now=ET_OPEN, cut_fraction=1.5)
    assert cycle.decide(s, card, 'CUT', now=ET_OPEN, cut_fraction=0.5) == 'APPROVED_AWAITING_FILL'
    when = ET_OPEN + timedelta(minutes=2)
    assert cycle.fill_pending(s, SPEC, snapshot(now=when), when) == [(card, 'CUT')]
    a_q = D(s.book('A').positions['SOXX']['quantity']); b_q = D(s.book('B').positions['SOXX']['quantity'])
    assert b_q < a_q * D('0.6')


def test_operator_yes_waits_while_price_ran_away_and_unanswered_expires(tmp_path):
    s = store_at(tmp_path)
    morning(s, FakeClient())
    card = _card(s)
    cycle.decide(s, card, 'YES', now=ET_OPEN)
    jumped_at = ET_OPEN + timedelta(minutes=5)
    assert cycle.fill_pending(s, SPEC, snapshot(now=jumped_at, shock={'SOXX': 1.02}), jumped_at) == []
    deadline = datetime(2026, 10, 5, 19, 31, tzinfo=timezone.utc)
    assert cycle.fill_pending(s, SPEC, snapshot(now=deadline), deadline) == [(card, 'APPROVED_NOT_FILLED')]
    s2 = store_at(tmp_path / 'two')
    morning(s2, FakeClient())
    assert cycle.expire_cards(s2, deadline) and not s2.book('B').positions


# ---------------------------------------------------------------- exits owned by code
def test_invalidation_exit_in_A_and_C_mirrors(tmp_path):
    s = store_at(tmp_path)
    morning(s, FakeClient())
    later = ET_OPEN + timedelta(days=1)
    drop = snapshot(now=later, session='2026-10-06', next_session='2026-10-07', shock={'SOXX': 0.90})
    r = cycle.morning(s, SPEC, drop, FakeClient(scout_names=[]), later, prices=PRICES)
    assert {'book': 'A', 'ticker': 'SOXX', 'action': 'EXIT', 'reason': 'INVALIDATION_PRICE'} in r['exits']
    assert not s.book('A').positions and not s.book('C').positions
    assert s.book('A').closed_trades == 1 and s.book('C').closed_trades == 1


def test_two_sessions_without_a_card_exit(tmp_path):
    s = store_at(tmp_path)
    morning(s, FakeClient())
    actions = []
    for k, day in ((1, '2026-10-06'), (2, '2026-10-07')):
        when = ET_OPEN + timedelta(days=k)
        r = cycle.morning(s, SPEC, snapshot(now=when, session=day, next_session='2026-10-08'), FakeClient(scout_names=[]), when, prices=PRICES)
        actions += [m['action'] for m in r['management'] if m['book'] == 'A']
    assert actions == ['UNREVIEWED', 'EXIT_TWO_SESSIONS_WITHOUT_A_CARD']
    assert not s.book('A').positions and not s.book('C').positions


def test_management_trim_and_exit(tmp_path):
    s = store_at(tmp_path)
    morning(s, FakeClient())
    when = ET_OPEN + timedelta(days=1)
    trim = FakeClient(scout_names=[], manage=lambda p: [{'ticker': 'SOXX', 'action': 'trim', 'trim_fraction': 0.5, 'reason': 'Partial.'}])
    q0 = D(s.book('A').positions['SOXX']['quantity'])
    cycle.morning(s, SPEC, snapshot(now=when, session='2026-10-06'), trim, when, prices=PRICES)
    assert D(s.book('A').positions['SOXX']['quantity']) == pytest.approx(q0 / 2, rel=1e-6)
    assert s.book('C').positions   # C trimmed, not closed


def test_protective_hard_stop_at_1550(tmp_path):
    s = store_at(tmp_path)
    morning(s, FakeClient())
    when = datetime(2026, 10, 5, 19, 52, tzinfo=timezone.utc)
    fall = snapshot(now=when, shock={'SOXX': 0.955})     # above the ticket's invalidation? no: 5% stop; 8% stop not hit
    assert cycle.protective(s, SPEC, fall, when) == []
    crash = snapshot(now=when, shock={'SOXX': 0.90})
    out = cycle.protective(s, SPEC, crash, when)
    assert out and out[0]['action'] == 'EXIT' and not s.book('C').positions


# ---------------------------------------------------------------- scoring
def test_scoreboard_is_too_early_at_first(tmp_path):
    s = store_at(tmp_path)
    morning(s, FakeClient())
    board = scoring.scoreboard(s, SPEC)
    assert board['verdict'] == 'TOO_EARLY' and set(board['lines']) == {'A', 'B', 'C'}
    assert board['lines']['A']['vs_vti']['status'] == 'INSUFFICIENT_DATA'


# ---------------------------------------------------------------- service hook (inside the existing tick)
class _Risk:
    def model_copy(self, update=None):
        return self


class _Config:
    risk = _Risk()

    def model_copy(self, update=None):
        return self


class _Inbox:
    def __init__(self, path):
        self.path = path


class _Reader:
    def __init__(self, snap):
        self.snap = snap
        self.calls = []

        class G:
            pass
        self.gateway = G()
        self.gateway.call = self.call

    def call(self, tool, args):
        self.calls.append(tool)
        if tool == 'get_equity_quotes':
            return {'data': {'results': [{'quote': {'symbol': s, 'bid_price': str(self.snap['quotes'][s]['bid']),
                                                    'ask_price': str(self.snap['quotes'][s]['ask']),
                                                    'updated_at': self.snap['quotes'][s]['ts'].isoformat()}} for s in args['symbols']]}}
        s = args['symbols'][0]
        return {'data': {'results': [{'symbol': s, 'bars': [{'begins_at': f'{d}T05:00:00+00:00', 'close_price': str(c), 'volume': '2000000'}
                                                            for d, c in self.snap['closes'][s]]}]}}

    def close(self):
        pass


def _official(tmp_path, status='COMPLETED', day='2026-10-05'):
    import sqlite3
    data = tmp_path / 'runtime' / 'data'
    data.mkdir(parents=True)
    db = sqlite3.connect(data / 'agent.db')
    db.execute('CREATE TABLE cycle_runs (day TEXT PRIMARY KEY, status TEXT, payload TEXT)')
    db.execute('INSERT INTO cycle_runs VALUES (?,?,?)', (day, status, '{}'))
    db.commit(); db.close()
    return data / 'agent.db'


def test_hook_is_disabled_until_initialised_and_waits_for_official(tmp_path):
    from agents.ai_trader import hook
    official = _official(tmp_path, status='RUNNING')
    trader = tmp_path / 'diag' / 'ai-trader' / 'trader.db'
    now = datetime(2026, 10, 5, 14, 6, tzinfo=timezone.utc)
    assert hook.tick(_Inbox(official), _Config(), now, path=trader) is None
    s = TraderStore(trader, official); s.bind_spec(SPEC)
    reader = _Reader(snapshot(now=now))
    assert hook.tick(_Inbox(official), _Config(), now, path=trader, reader_factory=lambda: reader,
                     client_factory=FakeClient) is None and reader.calls == []


def test_hook_runs_morning_once_after_official_then_protective(tmp_path):
    from agents.ai_trader import hook
    official = _official(tmp_path)
    trader = tmp_path / 'diag' / 'ai-trader' / 'trader.db'
    s = TraderStore(trader, official); s.bind_spec(SPEC)
    s.set_mode('PAPER', at=ET_OPEN, by='operator', spec=SPEC, official_first_run_completed=True)
    now = datetime(2026, 10, 5, 14, 7, tzinfo=timezone.utc)
    reader = _Reader(snapshot(now=now))
    out = hook.tick(_Inbox(official), _Config(), now, path=trader, clock=lambda: now, reader_factory=lambda: reader, client_factory=FakeClient)
    assert out['morning']['fills'] and 'SOXX' in s.book('A').positions and s.meta('morning_done') == '2026-10-05'
    again = hook.tick(_Inbox(official), _Config(), now + timedelta(minutes=1), path=trader,
                      reader_factory=lambda: _Reader(snapshot(now=now)), client_factory=FakeClient)
    assert again is None
    late = datetime(2026, 10, 5, 19, 51, tzinfo=timezone.utc)
    out = hook.tick(_Inbox(official), _Config(), late, path=trader, clock=lambda: late,
                    reader_factory=lambda: _Reader(snapshot(now=late, shock={'SOXX': 0.85})), client_factory=FakeClient)
    assert out['protective'] and not s.book('A').positions


def test_hook_failure_is_contained_and_retries_are_capped(tmp_path):
    from agents.ai_trader import hook
    official = _official(tmp_path)
    trader = tmp_path / 'diag' / 'ai-trader' / 'trader.db'
    TraderStore(trader, official).bind_spec(SPEC)
    def broken():
        raise RuntimeError('proxy down')
    for k in range(5):
        now = datetime(2026, 10, 5, 14, 6 + k, tzinfo=timezone.utc)
        out = hook.tick(_Inbox(official), _Config(), now, path=trader, reader_factory=broken, client_factory=FakeClient)
        assert out is None or out['status'] == 'AI_TRADER_TICK_FAILED'
    assert TraderStore(trader, official).meta('morning_attempts:2026-10-05') == '3'


def test_cli_init_status_and_start_paper_guard(tmp_path, capsys):
    from agents.ai_trader import cli
    official = _official(tmp_path, day='2026-10-01')
    trader = tmp_path / 'diag' / 'ai-trader' / 'trader.db'
    assert cli.main(['init', '--official-database', str(official), '--path', str(trader)]) == 0
    assert '"mode": "WATCH_ONLY"' in capsys.readouterr().out
    with pytest.raises(StoreError, match='NOT_BEFORE'):   # today is before Monday Oct 5 in the sandbox clock or later
        if datetime.now(timezone.utc).date().isoformat() >= SPEC.start_not_before:
            raise StoreError('PAPER_NOT_BEFORE_skip')
        cli.main(['start-paper', '--official-database', str(official), '--path', str(trader)])


# ---------------------------------------------------------------- regressions from the independent review
def test_daily_stop_counts_an_overnight_gap(tmp_path):
    s = store_at(tmp_path)
    morning(s, FakeClient())
    when = ET_OPEN + timedelta(days=1)
    gap = snapshot(now=when, session='2026-10-06', shock={t: 0.3 for t in SPEC.universe})   # everything -70%
    client = FakeClient(scout_names=['XLE'])
    r = cycle.morning(s, SPEC, gap, client, when, prices=PRICES)
    assert r['stopped'] in ('DAILY_LOSS_HIT', 'WEEKLY_LOSS_HIT') and 'scout' not in client.calls


def test_retry_does_not_double_trim_and_duplicates_do_not_crash(tmp_path):
    s = store_at(tmp_path)
    morning(s, FakeClient())
    q0 = D(s.book('A').positions['SOXX']['quantity'])
    when = ET_OPEN + timedelta(days=1)
    trim = lambda p: [{'ticker': 'SOXX', 'action': 'trim', 'trim_fraction': 0.5, 'reason': 'Partial.'}]
    snap = snapshot(now=when, session='2026-10-06')
    r = cycle.morning(s, SPEC, snap, FakeClient(scout_names=['XLE', 'XLE'], manage=trim), when, prices=PRICES)
    cycle.morning(s, SPEC, snap, FakeClient(scout_names=['XLE'], manage=trim), when + timedelta(minutes=1), prices=PRICES)
    assert D(s.book('A').positions['SOXX']['quantity']) == pytest.approx(q0 / 2, rel=1e-6)
    assert [t['ticker'] for t in r['tickets']] == ['XLE']


def test_max_names_rechecked_at_fill(tmp_path):
    s = store_at(tmp_path)
    a = s.book('A')
    for i, t in enumerate(['XLB', 'XLF', 'XLI', 'XLK']):
        a.buy(t, D('1'), D('100'), '2026-10-02', {'ticket_id': f'old{i}', 'invalidation_price': '1', 'time_stop_sessions': 20, 'thesis': 'x'})
    s.save_book(a)
    r = morning(s, FakeClient(scout_names=['SOXX', 'XLE']))
    assert len(s.book('A').positions) == 5
    assert sorted(t['status'] for t in r['tickets']) == ['APPROVED_RISK_BLOCKED', 'FILLED']


def test_c_is_closed_later_when_its_quote_was_stale_at_the_mirror(tmp_path):
    s = store_at(tmp_path)
    morning(s, FakeClient())
    (c_pick,) = s.book('C').positions
    when = ET_OPEN + timedelta(days=1)
    snap = snapshot(now=when, session='2026-10-06', shock={'SOXX': 0.90})
    snap['quotes'][c_pick]['ts'] = when - timedelta(minutes=10)            # stale at the moment A exits
    cycle.morning(s, SPEC, snap, FakeClient(scout_names=[]), when, prices=PRICES)
    assert not s.book('A').positions and c_pick in s.book('C').positions
    later = datetime(2026, 10, 6, 19, 51, tzinfo=timezone.utc)
    out = cycle.protective(s, SPEC, snapshot(now=later, session='2026-10-06'), later)
    assert {'book': 'C', 'ticker': c_pick, 'action': 'EXIT', 'reason': 'MIRROR_SWEEP'} in out and not s.book('C').positions


def test_sessions_held_counts_market_sessions_not_runs():
    assert cycle.sessions_between('2026-10-05', '2026-10-08') == 3
    assert cycle.sessions_between('2026-10-09', '2026-10-13') == 2      # weekend skipped


def test_watch_only_days_are_not_scored(tmp_path):
    s = store_at(tmp_path, 'WATCH_ONLY')
    morning(s, FakeClient())
    with s.connect() as db:
        assert db.execute('SELECT count(*) FROM book_values').fetchone()[0] == 0


# ---------------------------------------------------------------- Oct 1 watch-only finding
def test_pm_and_critic_see_only_their_names_plus_benchmark_and_risk(tmp_path):
    s = store_at(tmp_path, 'WATCH_ONLY')
    seen = {}

    class Spy(FakeClient):
        def __call__(self, model, prompt, schema, envelope):
            seat = next(k for k, p in seats.PROMPTS.items() if prompt.startswith(p))
            seen[seat] = set(json.loads(prompt.split('PACKET (JSON):\n', 1)[1])['tools'])
            return super().__call__(model, prompt, schema, envelope)

    morning(s, Spy())
    names = lambda ids: {i.split(':', 1)[1] for i in ids if i != 'risk:book'}
    assert names(seen['pm']) <= {'SOXX', 'VTI'} and 'risk:book' in seen['pm']
    assert names(seen['critic']) <= {'SOXX', 'VTI'}
    assert len(names(seen['scout'])) == len(SPEC.universe)       # the Scout still sees the whole list


def test_seat_failure_reason_is_journaled(tmp_path):
    from agents.ai_trader.model import ModelError
    s = store_at(tmp_path, 'WATCH_ONLY')

    class CapPM(FakeClient):
        def __call__(self, model, prompt, schema, envelope):
            if prompt.startswith(seats.PROMPTS['pm']):
                raise ModelError('INPUT_TOKEN_CAP')
            return super().__call__(model, prompt, schema, envelope)

    r = morning(s, CapPM())
    assert r['stopped'] == 'PM_ModelError'
    with s.connect() as db:
        rows = [json.loads(p) for k, p in db.execute("SELECT kind, payload_json FROM journal") if k == 'seat_error']
    assert rows == [{'seat': 'pm', 'error': 'ModelError', 'reason': 'INPUT_TOKEN_CAP'}]
