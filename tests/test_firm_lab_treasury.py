"""The 13-week Treasury-bill accrual index and the fixed 70/30 ruler, under the frozen methodology (construction A).
Fixture auction records only; no test opens a network connection. The ruler is a ruler: nothing here can trade."""
import hashlib
import json
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal as D
from pathlib import Path

import pytest

from agents.desk import firm_lab_page
from firm_lab import benchmarks, capabilities, features, quality, rawstore, treasury, view
from firm_lab.errors import FirmLabError
from firm_lab.providers import OK, REJECTED, UNAVAILABLE
from firm_lab.store import FORBIDDEN_TABLE_WORDS
from firm_lab_collectors import cli, runner
from firm_lab_collectors import treasury as source
from test_firm_lab_collectors import CLOCK, NOW, Fake, _cells, _lab, _rows

ROOT = Path(__file__).resolve().parents[1]
SIX = D('0.000001')
EARLY = datetime(2026, 1, 2, tzinfo=timezone.utc)                    # a known-at long before anything in these tests


def price(rate, days, rounding=ROUND_HALF_UP):
    return (D(100) * (1 - D(rate) / 100 * days / D(360))).quantize(SIX, rounding=rounding)


def record(issue, *, days=91, rate='4.110', cusip=None, auction=None, **over):
    """One auction result the way Fiscal Data publishes it: every value is text."""
    issue = date.fromisoformat(issue)
    auction = date.fromisoformat(auction) if auction else issue - timedelta(days=3)
    row = {'record_date': auction.isoformat(), 'cusip': cusip or '912797' + issue.strftime('%m%d')[1:] + 'X', 'security_type': 'Bill',
           'security_term': '13-Week', 'auction_date': auction.isoformat(), 'issue_date': issue.isoformat(),
           'maturity_date': (issue + timedelta(days=days)).isoformat(), 'high_discnt_rate': f'{D(rate):.6f}', 'price_per100': str(price(rate, days)),
           'closing_time_comp': '11:30 AM', 'reopening': 'Yes', 'original_security_term': '26-Week', 'high_investment_rate': '4.230000'}
    row.update(over)
    return row


def bill(issue, *, days=91, rate='4.110', known=EARLY, cusip=None):
    issue = date.fromisoformat(issue)
    return treasury.Bill(cusip or 'C' + issue.strftime('%m%d'), issue - timedelta(days=3), issue, issue + timedelta(days=days), price(rate, days), D(rate), known)


def ladder(*issues, **kw):
    return {b.issue: b for b in (bill(i, **kw) for i in issues)}


def body(rows, pages=1):
    return {'data': rows, 'meta': {'count': len(rows), 'total-count': len(rows), 'total-pages': pages}, 'links': {}}


def stored(row, ingested=EARLY):
    """A record as it sits in the raw table."""
    return {'cusip': row['cusip'], 'security_type': row['security_type'], 'security_term': row['security_term'], 'auction_date': row['auction_date'],
            'issue_date': row['issue_date'], 'maturity_date': row['maturity_date'], 'high_discount_rate': row['high_discnt_rate'],
            'price_per100': row['price_per100'], 'result_known_at': treasury.result_known_at(row['auction_date']).isoformat(),
            'ingested_at': ingested.isoformat()}


def weekdays(first, last, skip=()):
    day, out = date.fromisoformat(first), []
    while day <= date.fromisoformat(last):
        if day.weekday() < 5 and day.isoformat() not in skip:
            out.append(day)
        day += timedelta(days=1)
    return out


def thursdays(first, last):
    day, out = date.fromisoformat(first), []
    while day <= date.fromisoformat(last):
        out.append(day.isoformat())
        day += timedelta(days=7)
    return out


def with_vti(lab, days, start=D('350')):
    bars = [{'begins_at': f'{d.isoformat()}T00:00:00Z', 'close_price': str(start + D(i) / 4), 'interpolated': False} for i, d in enumerate(days)]
    features.ingest_provider_daily_bars(lab, 'VTI', bars, known_at='2026-10-01T14:00:00+00:00')
    return {d: start + D(i) / 4 for i, d in enumerate(days)}


# ====================================================================================================== frozen methodology
def test_the_methodology_is_frozen_at_the_approved_hash_and_nothing_computes_from_any_other_file(tmp_path):
    frozen = benchmarks.TREASURY_METHODOLOGY
    path = ROOT / frozen['document']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == frozen['sha256'] == 'c954c81b330aa3d43d97f4e19184321cf9f1c67fb974458f82443185d5fe40c4'
    assert frozen['status'] == 'APPROVED_AND_FROZEN' and frozen['version'] == 1 and frozen['approved_at'] == '2026-10-02T10:31:00-04:00'
    assert benchmarks.require_frozen_methodology() == frozen['sha256']
    approval = (ROOT / 'docs' / 'firm_lab' / 'treasury_bill_total_return_methodology.APPROVAL.md').read_text()
    for needed in (frozen['sha256'], '2026-10-02', '10:31', 'APPROVED_AND_FROZEN', 'Construction A', 'never edited'):
        assert needed in approval, needed
    lab = _lab(tmp_path)
    with_vti(lab, weekdays('2026-06-29', '2026-07-10'))
    for change in ('one more word\n', ' '):                                             # any edit at all, even one space
        root = tmp_path / ('edited' + str(len(change)))
        (root / 'docs' / 'firm_lab').mkdir(parents=True)
        (root / frozen['document']).write_bytes(path.read_bytes() + change.encode())
        with pytest.raises(FirmLabError, match='TREASURY_METHODOLOGY_HASH_MISMATCH'):
            benchmarks.compute_fixed_70_30(lab, NOW, root=root)
    with pytest.raises(FirmLabError, match='TREASURY_METHODOLOGY_FILE_MISSING'):
        benchmarks.compute_fixed_70_30(lab, NOW, root=tmp_path / 'nowhere')
    good = tmp_path / 'copy'
    (good / 'docs' / 'firm_lab').mkdir(parents=True)
    shutil.copy(path, good / frozen['document'])
    assert benchmarks.require_frozen_methodology(good) == frozen['sha256']                # the identical bytes are accepted wherever they are
    assert lab.counts()['benchmark_observations'] == 0 and benchmarks.index_status(lab) == {}      # the refused attempts stored nothing
    source_text = (ROOT / 'firm_lab' / 'benchmarks.py').read_text()
    assert source_text.index('require_frozen_methodology(root)') < source_text.index("SELECT * FROM treasury_auction_observations")      # checked first


# ====================================================================================================== price formula, selection
def test_the_published_price_is_checked_against_the_official_formula():
    assert treasury.q6(treasury.official_price(D('4.110'), 91)) == D('98.961083')       # the auction of 2026-09-28, as published
    assert treasury.q6(treasury.official_price(D('5.18'), 91)) == D('98.690611')
    good = stored(record('2026-10-01'))
    assert treasury.check_record(good) == [] and good['price_per100'] == '98.961083'
    off = dict(good, price_per100='98.961084')
    assert [c for c, _ in treasury.check_record(off)] == ['PRICE_FORMULA_MISMATCH']
    assert [c for c, _ in treasury.check_record(dict(good, high_discount_rate='4.120000'))] == ['PRICE_FORMULA_MISMATCH']
    assert [c for c, _ in treasury.check_record(dict(good, maturity_date='2026-12-30'))] == ['PRICE_FORMULA_MISMATCH']      # one day fewer
    # the formula rounded half-up or truncated is "the formula at six decimals"; nothing looser is accepted
    exact = treasury.official_price(D('4.135'), 91)                                     # 98.954763888...: the two roundings differ
    up, down = exact.quantize(SIX, rounding=ROUND_HALF_UP), exact.quantize(SIX, rounding=ROUND_DOWN)
    assert up != down and treasury.price_rounding(up, D('4.135'), 91) == 'half_up' and treasury.price_rounding(down, D('4.135'), 91) == 'down'
    assert treasury.price_rounding(up + SIX, D('4.135'), 91) is None and treasury.price_rounding(down - SIX, D('4.135'), 91) is None
    assert [c for c, _ in treasury.check_record(dict(good, maturity_date='2026-12-10', price_per100=str(price('4.110', 70))))] == ['TERM_OUT_OF_RANGE']
    assert [c for c, _ in treasury.check_record(dict(good, maturity_date='2026-10-01'))] == ['ISSUE_NOT_BEFORE_MATURITY']
    assert [c for c, _ in treasury.check_record(dict(good, issue_date='October 1'))] == ['UNPARSEABLE_DATE']
    assert [c for c, _ in treasury.check_record(dict(good, price_per100='n/a'))] == ['UNPARSEABLE_NUMBER']
    assert [c for c, _ in treasury.check_record(dict(good, result_known_at='2026-09-28T15:33:00+00:00'))] == ['KNOWN_AT_RULE_MISMATCH']
    # the same check is what validation runs on a provider response
    report = quality.validate('treasury_auctions', [{k: v for k, v in off.items() if k != 'ingested_at'}], now=NOW, require_provenance=False)
    assert report.codes() == ['PRICE_FORMULA_MISMATCH']


def test_only_thirteen_week_bills_are_selected_and_a_refused_record_stores_nothing(tmp_path):
    rows = [record(i) for i in thursdays('2026-09-17', '2026-10-01')]
    provider = source.FiscalDataAuctionsProvider(Fake([('auctions_query', 200, body(rows))]))
    result = provider.auctions(start='2026-09-01', now=CLOCK)
    assert result.status == OK and [r['issue_date'] for r in result.records()] == ['2026-09-17', '2026-09-24', '2026-10-01']
    url = provider.transport.calls[0][0]
    assert 'security_type:eq:Bill' in url and 'security_term:eq:13-Week' in url and 'issue_date:gte:2026-09-01' in url and 'api.fiscaldata.treasury.gov' in url
    first = result.records()[0]
    assert first['price_per100'] == rows[0]['price_per100'] and first['high_discount_rate'] == '4.110000'              # text exactly as published
    assert first['reopening'] == 'Yes' and first['original_security_term'] == '26-Week' and first['feed'] == 'fiscaldata:auctions_query'      # a reopening is a 13-week bill
    for odd in (dict(record('2026-09-24'), security_term='4-Week'), dict(record('2026-09-24'), security_type='CMB'),
                dict(record('2026-09-24'), security_term='26-Week')):
        refused = source.FiscalDataAuctionsProvider(Fake([('auctions_query', 200, body([rows[0], odd]))])).auctions(start='2026-09-01', now=CLOCK)
        assert refused.status == REJECTED and [i.code for i in refused.issues] == ['CONFLICTING_INSTRUMENT_IDENTITY']
    cases = (([dict(rows[0], price_per100='98.961090')], 'PRICE_FORMULA_MISMATCH'), ([dict(rows[0], price_per100='null')], 'MISSING_FIELD'),
             ([dict(rows[0], high_discnt_rate='null')], 'MISSING_FIELD'), ([rows[0], rows[0]], 'DUPLICATE_RECORD'),
             ([dict(rows[0], cusip='null')], 'MALFORMED_RESPONSE'), ([dict(rows[0], maturity_date='2027-03-18')], 'TERM_OUT_OF_RANGE'), ([], 'NOT_A_RECORD'))
    lab = _lab(tmp_path)
    with_vti(lab, weekdays('2026-09-21', '2026-09-30'))
    for data, code in cases:
        report = runner.run_treasury(lab, transport=Fake([('auctions_query', 200, body(rows[1:] + data if code != 'NOT_A_RECORD' else data))]),
                                     clock=CLOCK, start='2026-09-01')
        assert report['runs'][0]['status'] == REJECTED and code in report['runs'][0]['issues'], code
    assert not _rows(lab, 'treasury_auction_observations') and lab.counts()['benchmark_observations'] == 0             # good records in a bad response are not kept
    assert lab.capability('treasury_total_return') == 'UNAVAILABLE' and benchmarks.index_status(lab)['status'] == 'DATA_GAP'
    for status in (403, 429, 500):
        down = runner.run_treasury(lab, transport=Fake([('auctions_query', status, b'')]), clock=CLOCK, start='2026-09-01')
        assert down['runs'][0]['status'] == UNAVAILABLE and down['connection'] == 'ERROR'
    assert source.FiscalDataAuctionsProvider(Fake([('auctions_query', 200, '<html>')])).auctions(start='2026-09-01', now=CLOCK).status == REJECTED
    many = source.FiscalDataAuctionsProvider(Fake([('auctions_query', 200, body(rows, pages=9))])).auctions(start='2026-09-01', now=CLOCK)
    assert [i.code for i in many.issues] == ['INCOMPLETE_HISTORICAL_WINDOW']


# ====================================================================================================== accrual and roll
def test_a_bill_accretes_in_a_straight_line_from_its_auction_price_to_par():
    b = bill('2026-06-25')                                                               # 91 days at 4.110%: 98.961083
    assert b.price == D('98.961083') and b.maturity == date(2026, 9, 24)
    assert b.value(b.issue) == b.price and b.value(b.maturity) == D(100)
    step = (D(100) - b.price) / 91
    assert b.value(date(2026, 6, 26)) - b.value(date(2026, 6, 25)) == pytest.approx(step) and treasury.q6(b.value(date(2026, 6, 26))) == D('98.972500')
    assert treasury.q6(b.value(date(2026, 8, 9))) == treasury.q6(b.price + step * 45)
    out = treasury.accrual_index({b.issue: b}, {}, b.issue, date(2026, 9, 23))
    assert out.status == 'OK' and out.values[b.issue] == D(100) and len(out.values) == 91        # every calendar day, weekends included
    assert treasury.q6(out.values[date(2026, 9, 23)]) == treasury.q6(D(100) * b.value(date(2026, 9, 23)) / b.price)
    saturday, sunday, monday = (out.values[date(2026, 6, d)] for d in (27, 28, 29))
    assert monday - sunday == pytest.approx(sunday - saturday) and sunday > saturday            # interest accrues on days with no session
    assert set(out.holdings.values()) == {b.cusip} and out.uninvested_days == []
    # the whole holding period earns exactly the realised hold-to-maturity return, 100 / price
    held = treasury.accrual_index(ladder('2026-06-25', '2026-09-24'), {}, date(2026, 6, 25), date(2026, 9, 24))
    assert treasury.q6(held.values[date(2026, 9, 24)]) == treasury.q6(D(100) * D(100) / b.price) == D('101.049824')


def test_at_maturity_everything_rolls_into_the_bill_issued_that_day_at_its_auction_price():
    bills = {b.issue: b for b in (bill('2026-03-26', rate='4.000'), bill('2026-06-25', rate='4.110'), bill('2026-09-24', rate='3.950'))}
    a, b, c = (bills[k] for k in sorted(bills))
    start = date(2026, 6, 1)                                                             # mid-life: entered at the accrued value
    out = treasury.accrual_index(bills, {}, start, date(2026, 10, 30))
    assert out.status == 'OK' and out.values[start] == D(100) and out.holdings[start] == a.cusip
    at_first_roll = D(100) * D(100) / a.value(start)
    assert out.values[date(2026, 6, 25)] == pytest.approx(at_first_roll) and out.holdings[date(2026, 6, 25)] == b.cusip      # continuous: par, reinvested the same day
    assert out.values[date(2026, 6, 24)] < out.values[date(2026, 6, 25)] < out.values[date(2026, 6, 26)]
    assert out.values[date(2026, 7, 15)] == pytest.approx(at_first_roll * b.value(date(2026, 7, 15)) / b.price)
    at_second_roll = at_first_roll * D(100) / b.price
    assert out.values[date(2026, 9, 24)] == pytest.approx(at_second_roll) and out.holdings[date(2026, 9, 24)] == c.cusip
    assert out.values[date(2026, 10, 30)] == pytest.approx(at_second_roll * c.value(date(2026, 10, 30)) / c.price)
    assert [(d.isoformat(), cusip) for d, cusip, _ in out.rolls] == [('2026-06-01', a.cusip), ('2026-06-25', b.cusip), ('2026-09-24', c.cusip)]
    assert out.rolls[1][2] == b.price and out.uninvested_days == []
    days = sorted(out.values)
    assert all(out.values[x] < out.values[y] for x, y in zip(days, days[1:]))            # a bill only accretes; the level never falls
    # a bill issued in between is never bought: one bill at a time, held to maturity
    crowded = {**bills, **ladder('2026-07-02', '2026-07-09')}
    assert treasury.accrual_index(crowded, {}, start, date(2026, 10, 30)).values == out.values


def test_with_no_bill_issued_on_the_maturity_date_the_money_earns_nothing_until_the_next_issue():
    a = bill('2026-03-26', rate='4.000')                                                 # matures Thursday 2026-06-25
    late = bill('2026-06-29', days=87, rate='4.110')                                     # the next 13-week bill is issued the following Monday
    out = treasury.accrual_index({a.issue: a, late.issue: late}, {}, date(2026, 6, 1), date(2026, 7, 10))
    par = out.values[date(2026, 6, 25)]
    assert out.status == 'OK' and par == pytest.approx(D(100) * D(100) / a.value(date(2026, 6, 1)))
    for day in (25, 26, 27, 28):
        assert out.values[date(2026, 6, day)] == par and out.holdings[date(2026, 6, day)] == 'UNINVESTED'      # zero return, not a made-up rate
    assert out.uninvested_days == [date(2026, 6, d) for d in (25, 26, 27, 28)]            # each such day is recorded
    assert out.values[date(2026, 6, 29)] == par and out.holdings[date(2026, 6, 29)] == late.cusip
    assert out.values[date(2026, 6, 30)] > par and out.values[date(2026, 7, 10)] == pytest.approx(par * late.value(date(2026, 7, 10)) / late.price)
    # no other tenor or instrument is substituted: the function has nothing but 13-week bills to look at
    assert set(out.holdings.values()) == {a.cusip, 'UNINVESTED', late.cusip}


def test_a_missing_or_unusable_needed_bill_stops_the_series_and_nothing_is_filled_forward():
    a = bill('2026-03-26', rate='4.000')
    alone = treasury.accrual_index({a.issue: a}, {}, date(2026, 6, 1), date(2026, 7, 10))        # nothing stored after the held bill
    assert alone.status == 'DATA_GAP' and alone.gap_date == date(2026, 6, 25) and alone.gap_reason.startswith('NO_AUCTION_RECORD')
    assert max(alone.values) == date(2026, 6, 24) and date(2026, 6, 25) not in alone.values       # the series ends; no value is carried on
    before = treasury.accrual_index({a.issue: a}, {}, date(2026, 3, 2), date(2026, 3, 20))        # no bill issued on or before the start
    assert before.status == 'DATA_GAP' and before.gap_date == date(2026, 3, 2) and before.values == {}
    broken = treasury.accrual_index({a.issue: a}, {date(2026, 6, 25): 'PRICE_FORMULA_MISMATCH'}, date(2026, 6, 1), date(2026, 7, 10))
    assert broken.status == 'DATA_GAP' and broken.gap_date == date(2026, 6, 25) and 'PRICE_FORMULA_MISMATCH' in broken.gap_reason
    first = treasury.accrual_index(ladder('2026-06-25'), {date(2026, 5, 28): 'RECORDS_DISAGREE'}, date(2026, 6, 1), date(2026, 7, 10))
    assert first.status == 'DATA_GAP' and first.gap_date == date(2026, 6, 1) and 'RECORDS_DISAGREE' in first.gap_reason
    # an unusable bill that is never needed does not stop anything
    spare = treasury.accrual_index(ladder('2026-05-28', '2026-08-27'), {date(2026, 6, 11): 'TERM_OUT_OF_RANGE'}, date(2026, 6, 1), date(2026, 9, 10))
    assert spare.status == 'OK' and len(spare.values) == 102
    # stored rows: a mismatching price, two versions that disagree, two bills on one issue date
    good, bad = stored(record('2026-06-25')), stored(dict(record('2026-03-26', rate='4.000'), price_per100='98.000000'))
    bills, unusable = treasury.bills_from_rows([good, bad], NOW)
    assert list(bills) == [date(2026, 6, 25)] and unusable == {date(2026, 3, 26): 'PRICE_FORMULA_MISMATCH'}
    republished = stored(record('2026-06-25', rate='4.120'))
    republished['cusip'] = good['cusip']
    bills, unusable = treasury.bills_from_rows([good, republished], NOW)
    assert bills == {} and unusable == {date(2026, 6, 25): 'RECORDS_DISAGREE'}             # neither version is chosen
    twin = stored(record('2026-06-25', cusip='912797ZZ9'))
    bills, unusable = treasury.bills_from_rows([good, twin], NOW)
    assert bills == {} and unusable[date(2026, 6, 25)].startswith('AMBIGUOUS_ISSUE_DATE')
    assert treasury.bills_from_rows([good, dict(good)], NOW)[0][date(2026, 6, 25)].price == D('98.961083')      # an identical copy is the same record


# ====================================================================================================== known-at
def test_an_auction_result_is_known_from_five_pm_new_york_on_its_auction_date_or_from_ingestion_if_later(tmp_path):
    assert treasury.result_known_at('2026-09-28').isoformat() == '2026-09-28T21:00:00+00:00'      # 17:00 in New York, summer
    assert treasury.result_known_at('2026-12-21').isoformat() == '2026-12-21T22:00:00+00:00'      # 17:00 in New York, winter
    row = stored(record('2026-10-01'), ingested=datetime(2026, 9, 28, 15, 40, tzinfo=timezone.utc))        # fetched minutes after the 11:30 close
    assert treasury.bills_from_rows([row], datetime(2026, 9, 28, 20, 59, tzinfo=timezone.utc)) == ({}, {})   # not known before 17:00, though published
    known = treasury.bills_from_rows([row], datetime(2026, 9, 28, 21, 0, tzinfo=timezone.utc))[0][date(2026, 10, 1)]
    assert known.known_at.isoformat() == '2026-09-28T21:00:00+00:00' and known.known_at < datetime(2026, 10, 1, tzinfo=timezone.utc)      # before its first use
    late = stored(record('2026-06-25'), ingested=NOW)                                    # history ingested today is known today, not in June
    assert treasury.bills_from_rows([late], NOW - timedelta(seconds=1)) == ({}, {})
    assert treasury.bills_from_rows([late], NOW)[0][date(2026, 6, 25)].known_at == NOW
    # the collector leaves out a result that does not count as known yet, and counts it
    rows = [record('2026-09-24'), record('2026-10-01'), record('2026-10-08', auction='2026-10-02', price_per100='98.970000'),
            record('2026-10-15', auction='2026-10-05', price_per100='null', high_discnt_rate='null')]
    provider = source.FiscalDataAuctionsProvider(Fake([('auctions_query', 200, body(rows))]))
    result = provider.auctions(start='2026-09-01', now=CLOCK)                            # NOW is 10:00 New York on 2026-10-02
    assert result.status == OK and [r['issue_date'] for r in result.records()] == ['2026-09-24', '2026-10-01'] and provider.skipped == {'not_yet_known': 2}
    assert {r['result_known_at'] for r in result.records()} == {'2026-09-21T21:00:00+00:00', '2026-09-28T21:00:00+00:00'}
    evening = datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc)                          # 17:00 that day: the auction of 2026-10-02 now counts
    rows[2]['price_per100'] = str(price('4.110', 91))
    after = source.FiscalDataAuctionsProvider(Fake([('auctions_query', 200, body(rows))], at=evening)).auctions(start='2026-09-01', now=lambda: evening)
    assert [r['issue_date'] for r in after.records()] == ['2026-09-24', '2026-10-01', '2026-10-08']
    # a stored observation carries the later of the session close and the moment its bills were known
    lab = _lab(tmp_path)
    with_vti(lab, weekdays('2026-06-29', '2026-07-10'))
    runner.run_treasury(lab, transport=Fake([('auctions_query', 200, body([record(i) for i in thursdays('2026-06-18', '2026-10-01')]))]), clock=CLOCK,
                        start='2026-06-01')
    observations = _rows(lab, 'benchmark_observations', where="WHERE kind='tbill_13w_accrual_index'")
    assert len(observations) == 10 and {o['known_at'] for o in observations} == {NOW.isoformat()}       # ingested on 2026-10-02: known then, not in July
    assert benchmarks.compute_fixed_70_30(lab, NOW - timedelta(days=1))['gap_reason'].startswith('NO_AUCTION_RECORD')      # as of yesterday nothing was known


# ====================================================================================================== 70/30
def test_the_ruler_resets_to_70_30_at_the_close_of_the_first_stored_session_of_each_month():
    days = [date(2026, 5, 28), date(2026, 5, 29), date(2026, 6, 1), date(2026, 6, 2)]
    index = {days[0]: D(100), days[1]: D(100), days[2]: D(101), days[3]: D(101)}
    out = treasury.fixed_70_30(list(zip(days, [D(100), D(110), D(110), D(121)])), index)
    assert out.status == 'OK' and out.values[days[0]] == D(100)
    assert out.values[days[1]] == D('107.0')                                             # 0.7 x 110 + 0.3 x 100: weights drift inside a month
    assert out.values[days[2]] == D('107.3') and out.rebalances == [days[2]]             # Monday 1 June: valued, then reset to 70/30
    assert treasury.q6(out.values[days[3]]) == D('114.811000')                           # 107.3 x (0.7 x 1.10 + 0.3 x 1.00); without the reset it would be 115.0
    # the first session of the month is the first one actually stored, whatever its calendar date
    later = [date(2026, 5, 28), date(2026, 5, 29), date(2026, 6, 2), date(2026, 6, 3)]   # 1 June not a session
    out = treasury.fixed_70_30(list(zip(later, [D(100), D(110), D(110), D(121)])), {d: D(100) for d in later})
    assert out.rebalances == [date(2026, 6, 2)] and treasury.q6(out.values[date(2026, 6, 3)]) == treasury.q6(D(107) * (D('0.7') * D('1.1') + D('0.3')))
    # a full year: exactly one reset per month after the first, never on the start date itself
    year = weekdays('2026-01-02', '2026-12-31')
    out = treasury.fixed_70_30([(d, D(300)) for d in year], {d: D(100) for d in year})
    assert len(out.rebalances) == 11 and [d.month for d in out.rebalances] == list(range(2, 13)) and all(d == min(x for x in year if x.month == d.month)
                                                                                                    for d in out.rebalances)
    assert {treasury.q6(v) for v in out.values.values()} == {D('100.000000')}                                          # flat inputs, flat ruler: no cost, no lag, no drift invented
    assert (treasury.WEIGHT_VTI, treasury.WEIGHT_BILL) == (D('0.70'), D('0.30'))
    # it stops rather than guess: a hole in the stored sessions, or no index value for a session
    holed = [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 9)]
    out = treasury.fixed_70_30([(d, D(100)) for d in holed], {d: D(100) for d in holed})
    assert out.status == 'DATA_GAP' and out.gap_date == date(2026, 6, 9) and out.gap_reason.startswith('VTI_SESSION_GAP') and len(out.values) == 2
    out = treasury.fixed_70_30([(d, D(100)) for d in days], {days[0]: D(100), days[1]: D(100)})
    assert out.status == 'DATA_GAP' and out.gap_date == days[2] and out.gap_reason.startswith('INDEX_NOT_AVAILABLE') and len(out.values) == 2


# ====================================================================================================== end to end
def _sample(tmp_path):
    lab = _lab(tmp_path)
    days = weekdays('2026-06-29', '2026-09-30', skip=('2026-07-03', '2026-09-07'))
    closes = with_vti(lab, days)
    rows = [record(i, rate=str(D('4.300') - D(n) / 100)) for n, i in enumerate(thursdays('2026-03-05', '2026-10-01'))]
    rows.append(record('2026-10-08', auction='2026-10-05', price_per100='null', high_discnt_rate='null'))      # announced, not held yet
    return lab, days, closes, rows


def test_auction_records_become_the_bill_index_and_the_monthly_70_30_ruler(tmp_path, capsys):
    lab, days, closes, rows = _sample(tmp_path)
    assert lab.capability('treasury_total_return') == 'UNAVAILABLE'
    net = Fake([('auctions_query', 200, body(rows))])
    report = runner.run_treasury(lab, transport=net, clock=CLOCK)
    assert 'issue_date:gte:2026-03-01' in net.calls[0][0] and net.requests == 1          # from 120 days before the first stored VTI session
    run, made = report['runs'][0], report['benchmark']
    assert run['status'] == OK and run['stored'] == 31 and report['connection'] == 'ACTIVE'
    assert json.loads(_rows(lab, 'provider_runs')[0]['diagnostics_json'])['left_out'] == {'not_yet_known': 1}
    assert made['status'] == 'OK' and made['gap_date'] is None and made['stored'] == 2 * len(days) and made['base_date'] == '2026-06-29'
    assert made['last_session'] == '2026-09-30' and made['uninvested_days'] == [] and made['rolls'] == 2 and made['rebalances'] == 3
    assert made['vti_leg'] == 'price return; dividends not included'
    assert lab.capability('treasury_total_return') == 'AVAILABLE' and report['capabilities']['treasury_total_return'] == 'AVAILABLE'
    # independent arithmetic for the bill leg: entered 2026-06-29 in the bill issued 06-25, rolled 09-24
    by_issue = {r['issue_date']: r for r in rows}
    first, second = by_issue['2026-06-25'], by_issue['2026-09-24']
    p1, p2 = D(first['price_per100']), D(second['price_per100'])
    v = lambda p, n: p + (100 - p) * D(n) / 91
    expected_end = D(100) / v(p1, 4) * 100 / p2 * v(p2, 6)
    bill_obs = {o['exchange_session_date']: D(o['value']) for o in _rows(lab, 'benchmark_observations', where="WHERE kind='tbill_13w_accrual_index'")}
    assert bill_obs['2026-06-29'] == D('100.000000') and bill_obs['2026-09-30'] == treasury.q6(expected_end) and len(bill_obs) == len(days)
    assert bill_obs['2026-09-24'] == treasury.q6(D(100) / v(p1, 4) * 100)
    # ... and for the ruler: units reset on the first stored session of July, August and September
    level, vti_units, bill_units, month = D(100), D('0.7') * 100 / closes[days[0]], D('0.3'), days[0].month
    for day in days[1:]:
        level = vti_units * closes[day] + bill_units * bill_obs[day.isoformat()]
        if day.month != month:
            vti_units, bill_units, month = D('0.7') * level / closes[day], D('0.3') * level / bill_obs[day.isoformat()], day.month
    ruler = {o['exchange_session_date']: D(o['value']) for o in _rows(lab, 'benchmark_observations', where="WHERE kind='index_70_30_vti_price_return_basis'")}
    assert ruler['2026-06-29'] == D('100.000000') and abs(ruler['2026-09-30'] - level) < D('0.00001') and len(ruler) == len(days)
    state = benchmarks.index_status(lab)
    assert state['rebalances'] == ['2026-07-01', '2026-08-03', '2026-09-01']
    assert [(b['date'], b['cusip']) for b in state['bills_used']] == [('2026-06-29', first['cusip']), ('2026-09-24', second['cusip'])]
    for row in _rows(lab, 'benchmark_observations'):
        assert row['benchmark_id'] == 'FIXED_70_30' and 'construction A' in row['source'] and 'base 2026-06-29 = 100' in row['source']
        assert benchmarks.TREASURY_METHODOLOGY['sha256'][:16] in row['source']
    # run again: identical records and identical observations are recognised, nothing is duplicated or rewritten
    again = runner.run_treasury(lab, transport=Fake([('auctions_query', 200, body(rows))], at=NOW + timedelta(hours=2)),
                                clock=lambda: NOW + timedelta(hours=2))
    assert again['runs'][0]['stored'] == 0 and again['runs'][0]['duplicates'] == 31 and again['benchmark']['stored'] == 0
    assert again['benchmark']['unchanged'] == 2 * len(days) and len(_rows(lab, 'benchmark_observations')) == 2 * len(days)
    # the page: a ruler with levels, the frozen methodology, and no claim beyond that
    html = firm_lab_page.render({'firm_lab': view.load(path=lab.path)})
    row = _cells(html, 'T-bill total return')
    assert row['Capability'] == 'AVAILABLE' and row['Provider'] == 'U.S. Treasury Fiscal Data' and row['Validation'].startswith('PASS') and row['Stored'].startswith('31 ')
    card = html[html.index('<h3>70/30</h3>'):html.index('The Firm cannot trade a ruler')]
    assert '>APPROVED_AND_FROZEN</span>' in card and '<span class="cat cat-good">OK</span> through the 2026-09-30 session' in card
    assert f'{bill_obs["2026-09-30"]:,.6f} on the 2026-09-30 session (base 2026-06-29 = 100; {len(days)} sessions)' in card
    assert 'Price return. Dividends are not included' in card and 'accrual, not a market price' in card and 'rebased when a Firm trading trial' in card
    for word in ('outperform', 'alpha', 'beat', 'excess return', '<form'):
        assert word not in card.lower(), word
    assert cli.main(['treasury', '--path', str(lab.path)], environ={}, transport=Fake([('auctions_query', 200, body(rows))], at=NOW + timedelta(hours=3))) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed['run']['benchmark']['status'] == 'OK' and printed['status']['firm_trading_trial'] == 'NOT REGISTERED' and printed['status']['fills'] == 0


def test_a_stored_observation_is_never_recomputed_to_a_different_value_and_a_gap_takes_the_capability_back(tmp_path):
    lab, days, _, rows = _sample(tmp_path)
    runner.run_treasury(lab, transport=Fake([('auctions_query', 200, body(rows))]), clock=CLOCK)
    before = _rows(lab, 'benchmark_observations')
    with lab.connect() as db:                                                            # someone alters one stored level
        db.execute("UPDATE benchmark_observations SET value='100.500000' WHERE kind='tbill_13w_accrual_index' AND exchange_session_date='2026-07-15'")
    with pytest.raises(FirmLabError, match='BENCHMARK_OBSERVATION_CONFLICT:tbill_13w_accrual_index:2026-07-15'):
        benchmarks.compute_fixed_70_30(lab, NOW)
    with lab.connect() as db:
        db.execute("UPDATE benchmark_observations SET value=? WHERE kind='tbill_13w_accrual_index' AND exchange_session_date='2026-07-15'",
                   (next(o['value'] for o in before if o['kind'] == 'tbill_13w_accrual_index' and o['exchange_session_date'] == '2026-07-15'),))
    assert benchmarks.compute_fixed_70_30(lab, NOW)['status'] == 'OK' and _rows(lab, 'benchmark_observations') == before
    # the Treasury republishes the 2026-09-24 auction with another rate: both versions are kept, the series stops there
    changed = [dict(r, **({'high_discnt_rate': '4.000000', 'price_per100': str(price('4.000', 91))} if r['issue_date'] == '2026-09-24' else {})) for r in rows]
    later = NOW + timedelta(hours=1)
    report = runner.run_treasury(lab, transport=Fake([('auctions_query', 200, body(changed))], at=later), clock=lambda: later)
    assert report['runs'][0]['stored'] == 1 and len(_rows(lab, 'treasury_auction_observations', where="WHERE issue_date='2026-09-24'")) == 2
    assert report['benchmark']['status'] == 'DATA_GAP' and report['benchmark']['gap_date'] == '2026-09-24' and 'RECORDS_DISAGREE' in report['benchmark']['gap_reason']
    assert _rows(lab, 'benchmark_observations') == before                                # what was stored is not silently recomputed or removed
    assert lab.capability('treasury_total_return') == 'UNAVAILABLE'                      # a stopped series is not an available total return
    html = firm_lab_page.render({'firm_lab': view.load(path=lab.path)})
    assert '<span class="cat cat-stop">DATA_GAP</span> stopped from 2026-09-24' in html and 'Nothing is filled in.' in html
    assert _cells(html, 'T-bill total return')['Capability'] == 'UNAVAILABLE'


def test_the_benchmark_is_a_ruler_only(tmp_path):
    lab, _, _, rows = _sample(tmp_path)
    runner.run_treasury(lab, transport=Fake([('auctions_query', 200, body(rows))]), clock=CLOCK)
    assert lab.mode() == 'BUILD_OBSERVE' and not lab.active_experiments() and lab.counts()['experiment_registry'] == 0
    assert not [t for t in lab.tables() for word in FORBIDDEN_TABLE_WORDS if word in t] and lab.counts()['counterfactual_decisions'] == 0
    # nothing that ranks, selects or executes reads the benchmark: only the benchmark code, the registry and the read-only view mention it
    readers = {p.name for p in (ROOT / 'firm_lab').glob('*.py') if re.search(r'benchmark_observations|treasury_auction_observations|compute_fixed_70_30',
                                                                             p.read_text())}
    assert readers <= {'benchmarks.py', 'capabilities.py', 'view.py', 'store.py', 'rawstore.py', 'treasury.py'}, readers
    for name in ('baseline.py', 'boundary.py', 'features.py', 'ingest.py', 'official.py'):
        text = (ROOT / 'firm_lab' / name).read_text()
        assert 'compute_fixed_70_30' not in text and 'treasury' not in text.lower().replace('us_treasury_bill', ''), name
    for path in (ROOT / 'agents').rglob('*.py'):                                         # the registered system and the dashboard never import it
        if path.name != 'firm_lab_page.py':
            assert not re.search(r'firm_lab\.(benchmarks|treasury)|from firm_lab import', path.read_text()), path
    assert 'import' not in ''.join(line for line in (ROOT / 'firm_lab' / 'treasury.py').read_text().splitlines() if 'urllib' in line or 'socket' in line)
    state = view.load(path=lab.path)
    assert state['fills'] == 0 and state['firm_trading_trial'] == 'NOT REGISTERED' and state['october_research_stop_superseded'] == 'NO'
    assert state['real_execution'] == 'DISABLED' and state['official_lane_b'] == 'PAUSED' and state['has_execution_tables'] is False
