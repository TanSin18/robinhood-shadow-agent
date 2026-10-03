"""Checkpoint 4: VTI total return and the 70/30 total-return ruler. Fixture issuer answers only; no test opens a network
connection. What is proven here: a distribution is reinvested at the close of its ex-dividend session and never before
it was known; nothing is computed from distributions that did not validate; the price-return series and the legacy
ruler are left exactly as they were; and a ruler is a ruler."""
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from agents.desk import firm_lab_page
from firm_lab import benchmarks, capabilities, quality, total_return, treasury, view
from firm_lab.errors import FirmLabError
from firm_lab.providers import OK, REJECTED, UNAVAILABLE
from firm_lab.store import FORBIDDEN_TABLE_WORDS
from firm_lab.total_return import Distribution, Split
from firm_lab_collectors import cli, distributions, runner
from test_firm_lab_collectors import CLOCK, NOW, Fake, _codes, _lab, _rows
from test_firm_lab_treasury import _sample, body, with_vti, weekdays

EARLY = datetime(2026, 1, 2, tzinfo=timezone.utc)
LATER = NOW + timedelta(hours=3)


def day(text):
    return date.fromisoformat(text)


def cash(ex_date, amount, known=EARLY, currency='USD'):
    return Distribution(day(ex_date), D(amount), currency, known)


SESSIONS = [(day('2026-06-24'), D('100')), (day('2026-06-25'), D('101')), (day('2026-06-26'), D('99')), (day('2026-06-29'), D('102'))]


# ====================================================================================================== the arithmetic
def test_a_distribution_is_reinvested_at_the_close_of_its_ex_dividend_session():
    out = total_return.total_return_index(SESSIONS, [cash('2026-06-26', '1.00')], as_of=NOW)
    assert out.status == 'OK' and out.applied == [(day('2026-06-26'), D('1.00'), D('1.00'))]
    assert out.total_return[day('2026-06-24')] == 100 and out.total_return[day('2026-06-25')] == 101          # nothing before the ex-date
    assert out.total_return[day('2026-06-26')] == D(101) * (D(99) + 1) / 101 == 100                           # TR(t) = TR(t-1) x (P + D) / P(t-1)
    assert abs(out.total_return[day('2026-06-29')] - D(100) * 102 / 99) < D('1e-20')                          # afterwards it moves with the price
    # the price-return index is its own series and carries no dividend
    assert [out.price_return[d] for d, _ in SESSIONS] == [D(100), D(101), D(99), D(102)]
    assert out.total_return[day('2026-06-29')] > out.price_return[day('2026-06-29')]
    # with no distribution the two series are identical
    plain = total_return.total_return_index(SESSIONS, [], as_of=NOW)
    assert plain.total_return == plain.price_return and plain.applied == []
    # a distribution on the first stored session, or outside the stored sessions, is not applied: the base day has no earlier close
    edge = total_return.total_return_index(SESSIONS, [cash('2026-06-24', '1.00'), cash('2026-07-15', '1.00')], as_of=NOW)
    assert edge.applied == [] and edge.total_return == plain.total_return


def test_a_distribution_is_never_used_before_it_was_known():
    late = cash('2026-06-26', '1.00', known=NOW + timedelta(days=1))
    blind = total_return.total_return_index(SESSIONS, [late], as_of=NOW)
    assert blind.applied == [] and blind.total_return == blind.price_return                    # computed "as of" a time before it was known
    seen = total_return.total_return_index(SESSIONS, [late], as_of=NOW + timedelta(days=2))
    assert len(seen.applied) == 1
    # every observation says when it could first have been computed: after the ex-date that is the distribution's known-at
    assert seen.known_at[day('2026-06-25')] is None and seen.known_at[day('2026-06-26')] == late.known_at == seen.known_at[day('2026-06-29')]


def test_the_series_stops_rather_than_guess():
    off_session = total_return.total_return_index(SESSIONS, [cash('2026-06-27', '1.00')], as_of=NOW)      # a Saturday
    assert off_session.status == 'DATA_GAP' and off_session.gap_date == day('2026-06-27') and 'EX_DATE_NOT_A_SESSION' in off_session.gap_reason
    assert max(off_session.total_return) == day('2026-06-26')                                  # nothing from the gap on
    holed = total_return.total_return_index(SESSIONS + [(day('2026-07-08'), D('103'))], [], as_of=NOW)
    assert holed.status == 'DATA_GAP' and 'SESSION_GAP' in holed.gap_reason and day('2026-07-08') not in holed.total_return
    euros = total_return.total_return_index(SESSIONS, [cash('2026-06-26', '1.00', currency='EUR')], as_of=NOW)
    assert euros.status == 'DATA_GAP' and 'CURRENCY_NOT_USD' in euros.gap_reason and day('2026-06-26') not in euros.total_return
    negative = total_return.total_return_index(SESSIONS, [cash('2026-06-26', '-1.00')], as_of=NOW)
    assert negative.status == 'DATA_GAP' and 'AMOUNT_NOT_POSITIVE' in negative.gap_reason


def test_a_distribution_paid_before_a_split_is_put_on_the_share_basis_of_the_closes():
    split = Split(day('2026-06-29'), D(2))
    paid = cash('2026-06-26', '1.00')
    assert total_return.per_adjusted_share(paid, [split], day('2026-06-29')) == D('0.5')       # closes adjusted for the later 2-for-1 split
    assert total_return.per_adjusted_share(paid, [split], day('2026-06-26')) == D('1.00')      # closes not yet adjusted for it
    assert total_return.per_adjusted_share(cash('2026-06-29', '1.00'), [split], day('2026-06-29')) == D('1.00')      # paid on the new share basis
    out = total_return.total_return_index(SESSIONS, [paid], [split], as_of=NOW)
    assert out.applied == [(day('2026-06-26'), D('1.00'), D('0.5'))] and out.total_return[day('2026-06-26')] == D(101) * (D(99) + D('0.5')) / 101


def test_two_sources_must_agree_exactly_or_the_history_is_not_trusted():
    issuer = [cash('2026-03-27', '0.9982'), cash('2026-06-26', '1.0437'), cash('2026-09-28', '0.9555')]
    start, end = day('2026-01-02'), day('2026-09-30')
    assert total_return.compare_sources(issuer, list(issuer), start, end) == []
    codes = lambda other, **kw: [c for c, _ in total_return.compare_sources(issuer, other, start, end, **kw)]
    assert codes([issuer[0], cash('2026-06-26', '1.0438'), issuer[2]]) == ['AMOUNT_MISMATCH']
    assert codes(issuer[:2]) == ['MISSING_IN_INDEPENDENT_SOURCE'] and codes(issuer + [cash('2026-08-03', '0.2')]) == ['MISSING_IN_PRIMARY_SOURCE']
    assert codes([]) == ['NO_INDEPENDENT_RECORDS'] + ['MISSING_IN_INDEPENDENT_SOURCE'] * 3
    assert [c for c, _ in total_return.compare_sources([issuer[0], issuer[2]], [issuer[0], issuer[2]], start, end)] == ['CADENCE_GAP']      # a missing quarter


# ====================================================================================================== the issuer source
def feed(*items, frequency='Quarterly'):
    rows = [{'type': kind, 'perShareAmount': amount, 'isPerShareAmtPct': False, 'recordDate': f'{ex}T00:00:00-04:00',
             'reinvestmentDate': f'{ex}T00:00:00-04:00', 'payableDate': f'{pay}T00:00:00-04:00', 'reinvestPrice': price,
             'yield': {'hasDisclaimer': False}} for kind, amount, ex, pay, price in items]
    return {'divCapGain': {'distributionFrequency': frequency, 'item': rows}, 'realizedUnrealizedGain': {}, 'dailyDividendRate': {}}


LIVE = (('Dividend', '$0.955500', '2026-09-28', '2026-09-30', '375.82'), ('Dividend', '$1.043700', '2026-06-26', '2026-06-30', '363.02'),
        ('Dividend', '$0.998200', '2026-03-27', '2026-03-31', '313.12'))


def _issuer(payload, status=200):
    provider = distributions.VanguardDistributionsProvider(Fake([('/vmf/api/VTI/distribution', status, payload)]))
    return provider, provider.actions('VTI', start=None, end='2026-10-02', now=CLOCK)


def test_issuer_distributions_are_stored_as_published_with_the_ex_date_the_issuer_states():
    provider, result = _issuer(feed(*LIVE))
    assert result.status == OK and provider.frequency == 'Quarterly'
    first = result.records()[0]
    assert first['instrument'] == 'VTI' and first['action_type'] == 'cash_dividend' and first['provider_action'] == 'Dividend'
    assert first['effective_date'] == '2026-09-28' and 'reinvestmentDate' in first['effective_date_basis'] and 'Ex-dividend date' in first['effective_date_basis']
    assert first['value'] == '0.955500' and first['currency'] == 'USD' and first['value_meaning'] == 'cash per share, as paid'      # the text as published
    assert first['record_date'] == '2026-09-28' and first['pay_date'] == '2026-09-30' and first['distribution_type'] == 'income_dividend'
    assert first['announcement_timestamp'] == 'UNAVAILABLE'                                   # the feed gives none; none is made up
    kept = json.loads(first['source_record'])
    assert kept['perShareAmount'] == '$0.955500' and kept['reinvestPrice'] == '375.82' and 'yield' not in kept
    assert result.provenance.provider == 'Vanguard' and result.provenance.source_id == 'https://investor.vanguard.com/vmf/api/VTI/distribution'
    assert not result.provenance.missing() and [r['effective_date'] for r in result.records()] == ['2026-09-28', '2026-06-26', '2026-03-27']
    call = provider.transport.calls[0]
    assert call[0].startswith('https://investor.vanguard.com/') and '@' not in json.dumps(call)      # no contact address goes to the issuer
    assert distributions.RESEARCH_AGENT.startswith('FirmLabResearch/') and '@' not in distributions.RESEARCH_AGENT


def test_the_issuer_answer_is_refused_whole_when_it_is_not_what_was_documented():
    assert _codes(_issuer('<html><body>To see the profile for a specific Vanguard fund</body></html>')[1]) == ['MALFORMED_RESPONSE']      # a web page, not data
    assert _codes(_issuer({'divCapGain': {'item': []}})[1]) == ['MALFORMED_RESPONSE']
    gain = LIVE + (('LT Cap Gain', '$0.100000', '2025-12-22', '2025-12-24', '337.66'),)
    assert _codes(_issuer(feed(*gain))[1]) == ['UNKNOWN_DISTRIBUTION_TYPE']                   # not skipped: a rule must be written first
    assert _codes(_issuer(feed(('Dividend', '0.955500', '2026-09-28', '2026-09-30', '375.82')))[1]) == ['MALFORMED_RESPONSE']      # no currency stated
    assert _codes(_issuer(feed(('Dividend', '$0.95.5', '2026-09-28', '2026-09-30', '375.82')))[1]) == ['MALFORMED_RESPONSE']
    percent = feed(*LIVE)
    percent['divCapGain']['item'][0]['isPerShareAmtPct'] = True
    assert _codes(_issuer(percent)[1]) == ['MALFORMED_RESPONSE']
    assert _codes(_issuer(feed(('Dividend', '$0.955500', '2026-09-28', '2026-09-25', '375.82')))[1]) == ['IMPOSSIBLE_VALUE']       # paid before the ex-date
    assert _codes(_issuer(feed(('Dividend', '$0.955500', 'soon', '2026-09-30', '375.82')))[1]) == ['MALFORMED_RESPONSE']
    for status in (403, 429, 500):
        assert _issuer(feed(*LIVE), status)[1].status == UNAVAILABLE                         # refused or down: not retried, not worked around
    good = _issuer(feed(*LIVE))[1]
    made_up = dict(good.records()[0], announcement_timestamp='2026-09-28')                    # a date dressed up as an announcement time
    assert not quality.validate('corporate_actions', [made_up], now=NOW, provenance=good.provenance).passed
    assert quality.validate('corporate_actions', list(good.records()), now=NOW, provenance=good.provenance).passed
    scored = dict(good.records()[0], dividend_growth_score=1)
    assert 'SIGNAL_FIELD_NOT_ALLOWED' in quality.validate('corporate_actions', [scored], now=NOW, provenance=good.provenance).codes()


# ====================================================================================================== the run
def _ready(tmp_path):
    """A lab with VTI closes from 2026-06-29 to 2026-09-30 and the bill index and legacy ruler already computed."""
    lab, days, closes, rows = _sample(tmp_path)
    assert runner.run_treasury(lab, transport=Fake([('auctions_query', 200, body(rows))]), clock=CLOCK)['benchmark']['status'] == 'OK'
    capabilities.confirm_daily_data(lab, NOW)
    benchmarks.record_vti(lab, known_at=NOW)                                                  # the stored closes, as the price-return ruler keeps them
    return lab, days, closes


def _feed_for(closes, *, price_factor=D('1'), extra=()):
    ex = day('2026-09-28')
    items = (('Dividend', '$0.955500', '2026-09-28', '2026-09-30', str((closes[ex] * price_factor).quantize(D('0.01')))),
             ('Dividend', '$1.043700', '2026-06-26', '2026-06-30', '363.02')) + tuple(extra)
    return feed(*items)


def _observations(lab, kind):
    return {o['exchange_session_date']: o for o in _rows(lab, 'benchmark_observations', where=f"WHERE kind='{kind}'")}


def test_validated_distributions_become_the_total_return_series_and_the_legacy_series_are_untouched(tmp_path, capsys):
    lab, days, closes = _ready(tmp_path)
    legacy_before = _rows(lab, 'benchmark_observations')
    assert lab.capability('vti_total_return') == 'UNAVAILABLE' and lab.capability('total_return_ruler') == 'UNAVAILABLE'
    net = Fake([('/vmf/api/VTI/distribution', 200, _feed_for(closes))], at=LATER)
    report = runner.run_distributions(lab, transport=net, clock=lambda: LATER)
    assert net.requests == 1 and report['runs'][0]['status'] == OK and report['runs'][0]['stored'] == 2 and report['connection'] == 'ACTIVE'
    made = report['total_return']
    assert made['status'] == 'OK' and made['ruler_status'] == 'OK' and made['issues'] == [] and made['base_date'] == '2026-06-29'
    assert made['distributions_applied'] == [{'ex_date': '2026-09-28', 'amount': '0.955500'}]
    assert made['distributions_before_window'] == ['2026-06-26']                              # before the first stored session: not applied, not hidden
    assert made['independent_confirmation'] == 'NONE_STORED' and any('No independent distribution source' in n for n in made['notes'])
    assert made['observations'] == {'price_return': len(days), 'total_return': len(days), 'ruler': len(days)} and made['stored'] == 3 * len(days)
    # the arithmetic, independently
    ex = day('2026-09-28')
    level, previous = D(100), closes[days[0]]
    for d in days[1:]:
        level = level * (closes[d] + (D('0.955500') if d == ex else 0)) / previous
        previous = closes[d]
    tr, pr = _observations(lab, 'vti_total_return_index'), _observations(lab, 'vti_price_return_index')
    assert D(tr['2026-06-29']['value']) == 100 == D(pr['2026-06-29']['value'])
    assert abs(D(tr['2026-09-30']['value']) - level) < D('0.000001') and D(pr['2026-09-30']['value']) == treasury.q6(D(100) * closes[days[-1]] / closes[days[0]])
    before_ex = max(d for d in days if d < ex).isoformat()
    assert tr[before_ex]['value'] == pr[before_ex]['value'] and D(tr['2026-09-28']['value']) > D(pr['2026-09-28']['value'])
    # each observation says when it could first have been computed: from the ex-date on, when the distribution was fetched
    assert tr['2026-09-28']['known_at'] == LATER.isoformat() == tr['2026-09-30']['known_at'] and tr[before_ex]['known_at'] < NOW.isoformat()
    # the 70/30 total-return ruler: the same construction as the legacy ruler, fed the total-return index and the frozen bill index
    bill = {k: D(v['value']) for k, v in _observations(lab, 'tbill_13w_accrual_index').items()}
    ruler = _observations(lab, 'index_70_30_vti_total_return')
    exact = total_return.total_return_index([(d, closes[d]) for d in days], [Distribution(ex, D('0.955500'), 'USD', EARLY)], as_of=LATER).total_return
    value, vti_units, bill_units, month = D(100), D('0.7') * 100 / exact[days[0]], D('0.3'), days[0].month
    for d in days[1:]:
        value = vti_units * exact[d] + bill_units * bill[d.isoformat()]
        if d.month != month:
            vti_units, bill_units, month = D('0.7') * value / exact[d], D('0.3') * value / bill[d.isoformat()], d.month
    assert D(ruler['2026-06-29']['value']) == 100 and abs(D(ruler['2026-09-30']['value']) - value) < D('0.00001') and len(ruler) == len(days)
    legacy = _observations(lab, 'index_70_30_vti_price_return_basis')
    assert D(ruler['2026-09-30']['value']) > D(legacy['2026-09-30']['value']) and ruler[before_ex]['value'] == legacy[before_ex]['value']
    assert {o['benchmark_id'] for o in tr.values()} == {'VTI_TOTAL_RETURN'} and {o['benchmark_id'] for o in ruler.values()} == {'FIXED_70_30_TOTAL_RETURN'}
    assert all('reinvested at the ex-date close' in o['source'] for o in tr.values())
    assert all(benchmarks.TREASURY_METHODOLOGY['sha256'][:16] in o['source'] for o in ruler.values())
    # nothing that existed before was changed: same rows, same values, same known-at
    assert [o for o in _rows(lab, 'benchmark_observations') if o['benchmark_id'] in ('FIXED_70_30', 'VTI_100')] == legacy_before and legacy_before
    assert benchmarks.LABELS == {'FIXED_70_30': 'LEGACY_PRICE_RETURN_RULER', 'FIXED_70_30_TOTAL_RETURN': 'TOTAL_RETURN_RULER'}
    # capabilities follow the evidence; corporate actions as a whole stay partial, and say why
    assert lab.capability('vti_total_return') == 'AVAILABLE' and lab.capability('total_return_ruler') == 'AVAILABLE'
    assert lab.capability('corporate_actions') == 'PARTIAL_EXISTING'
    details = {c['capability']: c['detail'] for c in lab.capabilities()}
    assert 'VTI cash distributions only' in details['corporate_actions'] and 'Independent confirmation of the amounts: none stored' in details['vti_total_return']
    stored = _rows(lab, 'corporate_action_observations')
    assert [(r['instrument'], r['effective_date'], r['value'], r['currency'], r['provider'], r['announcement_timestamp']) for r in stored] == \
           [('VTI', '2026-09-28', '0.955500', 'USD', 'Vanguard', 'UNAVAILABLE'), ('VTI', '2026-06-26', '1.043700', 'USD', 'Vanguard', 'UNAVAILABLE')]
    assert all(r['known_at'] == LATER.isoformat() and r['content_hash'] and r['source_id'].endswith('/vmf/api/VTI/distribution') for r in stored)
    # again: nothing is duplicated and nothing is rewritten
    again = runner.run_distributions(lab, transport=Fake([('/vmf/api/VTI/distribution', 200, _feed_for(closes))], at=LATER + timedelta(hours=1)),
                                     clock=lambda: LATER + timedelta(hours=1))
    assert again['runs'][0]['stored'] == 0 and again['runs'][0]['duplicates'] == 2 and again['total_return']['stored'] == 0
    assert again['total_return']['unchanged'] == 3 * len(days) and _observations(lab, 'vti_total_return_index') == tr
    # the page
    html = firm_lab_page.render({'firm_lab': view.load(path=lab.path)})
    section = html[html.index('id="fl-benchready"'):html.index('id="fl-benchmarks"')]
    for label in ('VTI price return', 'VTI total return', 'Treasury total return', '70/30 legacy', '70/30 total-return'):
        assert f'<b>{label}</b>' in section, label
    assert section.count('>AVAILABLE</span>') == 5 and section.count('>PASS</span>') == 5 and 'LEGACY_PRICE_RETURN_RULER' in section
    assert 'TOTAL_RETURN_RULER' in section and '2026-09-28: $0.955500 per share' in section and 'No independent distribution source' in section
    cards = html[html.index('id="fl-benchmarks"'):html.index('id="fl-warning"')]
    assert '<h3>VTI total return</h3>' in cards and '<h3>70/30 total return</h3>' in cards and '<h3>70/30</h3>' in cards and '<h3>VTI</h3>' in cards
    assert '>LEGACY_PRICE_RETURN_RULER</span>' in cards and '>TOTAL_RETURN_RULER</span>' in cards and '1 distributions reinvested' in cards
    for word in ('outperform', 'alpha', 'beat', 'excess return', '<form', '<button'):
        assert word not in (section + cards).lower().replace('no outperformance figure is reported', ''), word
    assert cli.main(['distributions', '--path', str(lab.path)], environ={},
                    transport=Fake([('/vmf/api/VTI/distribution', 200, _feed_for(closes))], at=LATER + timedelta(hours=2))) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed['run']['total_return']['status'] == 'OK' and printed['status']['fills'] == 0 and printed['status']['firm_trading_trial'] == 'NOT REGISTERED'


def test_nothing_is_computed_from_distributions_that_do_not_validate(tmp_path):
    lab, days, closes = _ready(tmp_path)
    count = len(_rows(lab, 'benchmark_observations'))

    def attempt(payload, at=LATER):
        report = runner.run_distributions(lab, transport=Fake([('/vmf/api/VTI/distribution', 200, payload)], at=at), clock=lambda: at)
        return report, [i['code'] for i in report['total_return']['issues']]

    # the issuer's reinvestment price is twice the stored close: a wrong date or a different share basis (a split) cannot be ruled out
    report, codes = attempt(_feed_for(closes, price_factor=D('2')))
    assert report['runs'][0]['status'] == OK and report['total_return']['status'] == 'VALIDATION_FAILED' and codes == ['REINVESTMENT_PRICE_MISMATCH']
    assert len(_rows(lab, 'benchmark_observations')) == count                                   # the rows are stored; no series is computed from them
    assert lab.capability('vti_total_return') == 'UNAVAILABLE' and lab.capability('total_return_ruler') == 'UNAVAILABLE'
    assert lab.capability('corporate_actions') == 'PARTIAL_EXISTING'
    html = firm_lab_page.render({'firm_lab': view.load(path=lab.path)})
    section = html[html.index('id="fl-benchready"'):html.index('id="fl-benchmarks"')]
    assert 'REINVESTMENT_PRICE_MISMATCH' in section and 'Nothing was computed from data that did not validate' in section
    assert section.count('>AVAILABLE</span>') == 3 and '>FAIL</span>' in section                # the three earlier series stay as they were
    # a later issuer record with the same amount and a reinvestment price that does agree is a further row, not an overwrite; the amount
    # is unchanged, so there is no conflict, and the distribution keeps the known-at of the first record
    report, codes = attempt(_feed_for(closes), LATER + timedelta(hours=1))
    assert codes == [] and report['total_return']['status'] == 'OK' and len(_rows(lab, 'corporate_action_observations')) == 3
    assert _observations(lab, 'vti_total_return_index')['2026-09-28']['known_at'] == LATER.isoformat()
    assert lab.capability('vti_total_return') == 'AVAILABLE'


def test_a_missing_quarter_an_off_session_ex_date_and_a_changed_amount_each_stop_the_computation(tmp_path):
    lab, days, closes = _ready(tmp_path)
    count = len(_rows(lab, 'benchmark_observations'))
    run = lambda payload, at: [i['code'] for i in runner.run_distributions(
        lab, transport=Fake([('/vmf/api/VTI/distribution', 200, payload)], at=at), clock=lambda: at)['total_return']['issues']]
    assert run(feed(('Dividend', '$1.043700', '2026-06-26', '2026-06-30', '363.02')), LATER) == ['NO_PRIMARY_RECORDS']      # nothing inside the window
    saturday = feed(('Dividend', '$0.955500', '2026-09-26', '2026-09-30', '375.82'))
    assert run(saturday, LATER + timedelta(hours=1)) == ['EX_DATE_NOT_A_SESSION']
    assert len(_rows(lab, 'benchmark_observations')) == count and benchmarks.total_return_status(lab)['status'] == 'VALIDATION_FAILED'
    # a longer history with a quarter missing from the issuer's list
    long_lab = _lab(tmp_path / 'long')
    long_days = weekdays('2026-01-05', '2026-09-30')
    long_closes = with_vti(long_lab, long_days)
    only_september = feed(('Dividend', '$0.955500', '2026-09-28', '2026-09-30', str(long_closes[day('2026-09-28')])))
    report = runner.run_distributions(long_lab, transport=Fake([('/vmf/api/VTI/distribution', 200, only_september)], at=LATER), clock=lambda: LATER)
    assert [i['code'] for i in report['total_return']['issues']] == ['CADENCE_GAP'] and not _rows(long_lab, 'benchmark_observations')
    # the same source publishing a different amount for a distribution already stored
    lab2, _, closes2 = _ready(tmp_path / 'two')
    assert runner.run_distributions(lab2, transport=Fake([('/vmf/api/VTI/distribution', 200, _feed_for(closes2))], at=LATER),
                                    clock=lambda: LATER)['total_return']['status'] == 'OK'
    changed = _feed_for(closes2)
    changed['divCapGain']['item'][0]['perShareAmount'] = '$0.965500'
    at = LATER + timedelta(hours=1)
    report = runner.run_distributions(lab2, transport=Fake([('/vmf/api/VTI/distribution', 200, changed)], at=at), clock=lambda: at)
    assert [i['code'] for i in report['total_return']['issues']] == ['CONFLICTING_DISTRIBUTION_RECORDS']
    assert report['total_return']['status'] == 'VALIDATION_FAILED' and report['capabilities']['vti_total_return'] == 'UNAVAILABLE'
    tr = _observations(lab2, 'vti_total_return_index')
    assert len(tr) == len(closes2)                                                             # what was stored stays stored, unchanged


def test_a_distribution_learned_late_never_rewrites_a_stored_observation(tmp_path):
    lab, days, closes = _ready(tmp_path)
    with lab.connect() as db:                                                                 # as if an earlier run had stored a series without the distribution
        for d in days:
            db.execute('INSERT INTO benchmark_observations (benchmark_id, exchange_session_date, value, kind, source, known_at, ingested_at) '
                       'VALUES (?,?,?,?,?,?,?)', ('VTI_TOTAL_RETURN', d.isoformat(), str(treasury.q6(D(100) * closes[d] / closes[days[0]])),
                                                  'vti_total_return_index', 'firm_lab.total_return EX_DATE_REINVESTMENT_V1; base 2026-06-29 = 100 '
                                                  '(development base); distributions from Vanguard, reinvested at the ex-date close', NOW.isoformat(), NOW.isoformat()))
    before = _observations(lab, 'vti_total_return_index')
    with pytest.raises(FirmLabError, match='BENCHMARK_OBSERVATION_CONFLICT'):
        runner.run_distributions(lab, transport=Fake([('/vmf/api/VTI/distribution', 200, _feed_for(closes))], at=LATER), clock=lambda: LATER)
    assert _observations(lab, 'vti_total_return_index') == before


def test_the_total_return_rulers_are_rulers_only(tmp_path):
    lab, days, closes = _ready(tmp_path)
    runner.run_distributions(lab, transport=Fake([('/vmf/api/VTI/distribution', 200, _feed_for(closes))], at=LATER), clock=lambda: LATER)
    state = view.load(path=lab.path)
    assert state['mode'] == 'BUILD_OBSERVE' and state['fills'] == 0 and state['experiments'] == [] and not state['has_execution_tables']
    assert state['firm_trading_trial'] == 'NOT REGISTERED' and state['october_research_stop_superseded'] == 'NO'
    with lab.connect() as db:
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert not [t for t in tables if any(word in t for word in FORBIDDEN_TABLE_WORDS)]
    for name in ('ml_ranker', 'sector_engine', 'portfolio_optimizer', 'options_strategy'):
        assert lab.capability(name) == 'NOT_STARTED'
    # the two earlier definitions are exactly what they were, and locked; the new ones are separate benchmarks
    ids = [b['benchmark_id'] for b in benchmarks.definitions(lab)]
    assert ids == ['VTI_100', 'FIXED_70_30', 'VTI_TOTAL_RETURN', 'FIXED_70_30_TOTAL_RETURN']
    old = {d[0]: d for d in benchmarks.DEFINITIONS}
    assert old['FIXED_70_30'][3]['vti_leg'] == 'price return; dividends are not included until a validated dividend source exists'
    assert old['FIXED_70_30_TOTAL_RETURN'][3]['treasury_bill_series']['methodology_sha256'] == benchmarks.TREASURY_METHODOLOGY['sha256']
    with pytest.raises(FirmLabError, match='TREASURY_METHODOLOGY_FILE_MISSING'):               # no bill leg without the frozen methodology file
        benchmarks.compute_total_return(lab, LATER, root=tmp_path / 'nowhere')
    source = (__import__('pathlib').Path(benchmarks.__file__).parent / 'total_return.py').read_text()
    for banned in ('import urllib', 'import socket', 'requests', 'sqlite3', 'open('):
        assert banned not in source, banned                                                    # pure arithmetic: no network, no file
