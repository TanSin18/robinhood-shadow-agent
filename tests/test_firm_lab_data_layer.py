"""Checkpoint 2: the data-source capability layer. Interfaces, provenance, data-quality checks, the registry rules,
the final 70/30 definition and the Data Readiness view. No provider is connected and nothing here can affect a decision."""
import ast
import copy
import hashlib
import json
import re
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from agents.desk import firm_lab_page
from firm_lab import baseline, benchmarks, boundary, capabilities, cli, features, ingest, official, providers, quality, schemas, view
from firm_lab.errors import CapabilityUnavailable, FirmLabError, NoFillInBuildObserve
from firm_lab.provenance import Provenance, content_hash
from firm_lab.store import FORBIDDEN_TABLE_WORDS, FirmLabStore
from test_firm_lab_features import KNOWN, _bars, _official_with_capsule

ROOT = Path(__file__).resolve().parents[1]
NOW = '2026-10-01T20:30:00+00:00'
D = __import__('decimal').Decimal


def _lab(tmp_path, official_db=None):
    return FirmLabStore(tmp_path / 'diag' / 'firm_lab' / 'firm_lab.db', official_db)


def _prov(**over):
    base = dict(provider='example-vendor', source_id='resp-001', source_timestamp='2026-10-01T16:05:03.123456789-04:00',
                ingested_at='2026-10-01T20:06:00+00:00', known_at='2026-10-01T20:05:04+00:00', schema_version=schemas.SCHEMA_VERSION,
                content_hash=content_hash({'x': 1}))
    base.update(over)
    return Provenance(**base)


class _Fixture:
    """Turns an interface into a connected test double: it returns whatever records and provenance it was given."""
    name = 'example-vendor'

    def __init__(self, records, provenance):
        self.records, self.prov, self.requests = records, provenance, []

    def _fetch(self, method, **request):
        self.requests.append((method, request))
        return self.records, self.prov


def _connected(interface, records, provenance):
    return type('Connected' + interface.__name__, (_Fixture, interface), {})(records, provenance)


ESTIMATE = {'instrument': 'AAPL', 'fiscal_period': '2026Q4', 'metric': 'eps', 'consensus_estimate': '2.31', 'prior_consensus': '2.28',
            'revision_magnitude': '0.03', 'analyst_count': 31, 'dispersion': '0.07', 'currency': 'USD',
            'effective_timestamp': '2026-09-30T21:00:00Z', 'snapshot_timestamp': '2026-10-01T04:00:00Z'}
BAR = {'instrument': 'SPY', 'bar_start': '2026-10-01T13:30:00Z', 'interval': '1m', 'open': '762.10', 'high': '762.40', 'low': '761.95',
       'close': '762.30', 'volume': 184223, 'session': 'regular', 'exchange_session_date': '2026-10-01'}
OPTION = {'contract_id': 'SPY261016C00765000', 'underlying': 'SPY', 'option_type': 'call', 'strike': '765', 'expiration': '2026-10-16',
          'bid': '4.10', 'ask': '4.14', 'quote_timestamp': '2026-10-01T19:59:58Z', 'volume': 1203, 'open_interest': 18844,
          'provider_implied_volatility': '0.142', 'provider_delta': '0.41'}
TBILL = {'series_id': 'EXAMPLE-3M-TR', 'measure': 'TOTAL_RETURN_INDEX', 'observation_date': '2026-09-30', 'value': '1432.8812',
         'published_timestamp': '2026-10-01T12:00:00Z'}


# ---------------------------------------------------------------- provider interfaces
def test_every_interface_returns_unavailable_when_no_provider_is_connected():
    calls = {
        'fundamentals': [lambda p: p.financial_statements('AAPL', known_at=NOW, now=NOW), lambda p: p.valuation_inputs('AAPL', known_at=NOW, now=NOW),
                         lambda p: p.profitability('AAPL', known_at=NOW, now=NOW), lambda p: p.leverage('AAPL', known_at=NOW, now=NOW),
                         lambda p: p.cash_flow('AAPL', known_at=NOW, now=NOW)],
        'estimates': [lambda p: p.consensus('AAPL', 'eps', '2026Q4', known_at=NOW, now=NOW),
                      lambda p: p.revisions('AAPL', 'eps', '2026Q4', start=NOW, end=NOW, now=NOW)],
        'earnings': [lambda p: p.events('AAPL', start=NOW, end=NOW, now=NOW), lambda p: p.release('AAPL', '2026Q3', now=NOW),
                     lambda p: p.transcript('AAPL', '2026Q3', now=NOW), lambda p: p.guidance('AAPL', '2026Q3', now=NOW)],
        'filings': [lambda p: p.filings('AAPL', start=NOW, end=NOW, now=NOW)],
        'news': [lambda p: p.headlines(start=NOW, end=NOW, instrument='AAPL', now=NOW)],
        'intraday_bars': [lambda p: p.bars_1m('SPY', session_date='2026-10-01', now=NOW), lambda p: p.quote_snapshots('SPY', start=NOW, end=NOW, now=NOW),
                          lambda p: p.trades('SPY', start=NOW, end=NOW, now=NOW)],
        'options_chain': [lambda p: p.chain('SPY', as_of=NOW, now=NOW), lambda p: p.quotes(['SPY261016C00765000'], as_of=NOW, now=NOW)],
        'risk_free': [lambda p: p.total_return_series(start='2026-01-01', end='2026-09-30', known_at=NOW, now=NOW)],
        'corporate_actions': [lambda p: p.actions('AAPL', start=NOW, end=NOW, now=NOW)],
    }
    assert {i.domain for i in providers.INTERFACES} == set(calls) and len(providers.INTERFACES) == 9
    for interface in providers.INTERFACES:
        provider = interface()
        assert provider.connected is False and provider.name is None
        for call in calls[interface.domain]:
            result = call(provider)
            assert result.status == 'UNAVAILABLE' and result.available is False and result.reason == 'no provider is connected'
            assert result.summary()['records'] == 0 and result.provenance is None
            with pytest.raises(CapabilityUnavailable):
                result.records()                           # no empty list that could be read as "nothing happened"
    # the interface layer contains no number, URL or network call it could fall back on
    source = (ROOT / 'firm_lab' / 'providers.py').read_text()
    assert 'http' not in source and not re.search(r'\b\d+\.\d+\b', source)


def test_a_valid_response_passes_through_unchanged_with_timestamps_and_provenance_preserved():
    prov = _prov()
    records = [dict(ESTIMATE)]
    before = copy.deepcopy(records)
    provider = _connected(providers.EstimatesProvider, records, prov)
    result = provider.consensus('AAPL', 'eps', '2026Q4', known_at=NOW, now=NOW)
    assert result.status == 'OK' and result.available and result.issues == ()
    assert list(result.records()) == before and records == before                       # nothing rewritten, nothing rounded
    assert result.records()[0]['snapshot_timestamp'] == '2026-10-01T04:00:00Z'          # exactly as the provider wrote it
    assert result.provenance is prov and result.provenance.source_timestamp == '2026-10-01T16:05:03.123456789-04:00'
    assert result.provenance.as_dict() == {'provider': 'example-vendor', 'source_id': 'resp-001',
                                           'source_timestamp': '2026-10-01T16:05:03.123456789-04:00', 'ingested_at': '2026-10-01T20:06:00+00:00',
                                           'known_at': '2026-10-01T20:05:04+00:00', 'schema_version': 'firm-lab-data-v1',
                                           'exchange_session_date': None, 'content_hash': content_hash({'x': 1})}
    assert provider.requests == [('consensus', {'instrument': 'AAPL', 'metric': 'eps', 'fiscal_period': '2026Q4', 'known_at': NOW})]
    assert content_hash(b'abc') == hashlib.sha256(b'abc').hexdigest() == content_hash('abc')


@pytest.mark.parametrize('label, interface, call, records, code', [
    ('not a list', providers.NewsProvider, lambda p: p.headlines(start=NOW, end=NOW, now=NOW), 'breaking: stocks up', 'NOT_A_RECORD'),
    ('empty', providers.FilingsProvider, lambda p: p.filings('AAPL', start=NOW, end=NOW, now=NOW), [], 'NOT_A_RECORD'),
    ('record is text', providers.NewsProvider, lambda p: p.headlines(start=NOW, end=NOW, now=NOW), ['headline only'], 'NOT_A_RECORD'),
    ('missing field', providers.EstimatesProvider, lambda p: p.consensus('AAPL', 'eps', '2026Q4', known_at=NOW, now=NOW),
     [{k: v for k, v in ESTIMATE.items() if k != 'analyst_count'}], 'MISSING_FIELD'),
    ('only today’s consensus', providers.EstimatesProvider, lambda p: p.consensus('AAPL', 'eps', '2026Q4', known_at=NOW, now=NOW),
     [{k: v for k, v in ESTIMATE.items() if k != 'snapshot_timestamp'}], 'NOT_POINT_IN_TIME'),
    ('wrong instrument', providers.EstimatesProvider, lambda p: p.consensus('MSFT', 'eps', '2026Q4', known_at=NOW, now=NOW), [dict(ESTIMATE)],
     'CONFLICTING_INSTRUMENT_IDENTITY'),
    ('money without currency', providers.EstimatesProvider, lambda p: p.consensus('AAPL', 'eps', '2026Q4', known_at=NOW, now=NOW),
     [{k: v for k, v in ESTIMATE.items() if k != 'currency'}], 'MISSING_UNITS_OR_CURRENCY'),
    ('future bar', providers.IntradayMarketDataProvider, lambda p: p.bars_1m('SPY', session_date='2026-10-01', now=NOW),
     [{**BAR, 'bar_start': '2026-10-02T13:30:00Z'}], 'FUTURE_TIMESTAMP'),
    ('no timezone', providers.IntradayMarketDataProvider, lambda p: p.bars_1m('SPY', session_date='2026-10-01', now=NOW),
     [{**BAR, 'bar_start': '2026-10-01T09:30:00'}], 'TIMEZONE_MISSING'),
    ('high below low', providers.IntradayMarketDataProvider, lambda p: p.bars_1m('SPY', session_date='2026-10-01', now=NOW),
     [{**BAR, 'high': '761.00'}], 'IMPOSSIBLE_VALUE'),
    ('negative volume', providers.IntradayMarketDataProvider, lambda p: p.bars_1m('SPY', session_date='2026-10-01', now=NOW),
     [{**BAR, 'volume': -5}], 'IMPOSSIBLE_VALUE'),
    ('duplicate bar', providers.IntradayMarketDataProvider, lambda p: p.bars_1m('SPY', session_date='2026-10-01', now=NOW),
     [dict(BAR), dict(BAR)], 'DUPLICATE_RECORD'),
    ('bars out of order', providers.IntradayMarketDataProvider, lambda p: p.bars_1m('SPY', session_date='2026-10-01', now=NOW),
     [{**BAR, 'bar_start': '2026-10-01T13:31:00Z'}, dict(BAR)], 'NON_MONOTONIC_TIMESTAMPS'),
    ('five-minute bar offered as one-minute', providers.IntradayMarketDataProvider, lambda p: p.bars_1m('SPY', session_date='2026-10-01', now=NOW),
     [{**BAR, 'interval': '5m'}], 'VALUE_NOT_ALLOWED'),
    ('ask below bid', providers.OptionsMarketDataProvider, lambda p: p.chain('SPY', as_of=NOW, now=NOW), [{**OPTION, 'ask': '4.00'}], 'IMPOSSIBLE_VALUE'),
    ('bare greek', providers.OptionsMarketDataProvider, lambda p: p.chain('SPY', as_of=NOW, now=NOW), [{**OPTION, 'delta': '0.41'}], 'UNNAMESPACED_GREEK'),
    ('contract without id', providers.OptionsMarketDataProvider, lambda p: p.chain('SPY', as_of=NOW, now=NOW),
     [{k: v for k, v in OPTION.items() if k != 'contract_id'}], 'MISSING_IDENTIFIER'),
    ('yield offered as total return', providers.RiskFreeBenchmarkProvider,
     lambda p: p.total_return_series(start='2026-01-01', end='2026-09-30', known_at=NOW, now=NOW), [{**TBILL, 'measure': 'YIELD', 'value': '3.92'}],
     'YIELD_IS_NOT_TOTAL_RETURN'),
    ('discount rate offered as total return', providers.RiskFreeBenchmarkProvider,
     lambda p: p.total_return_series(start='2026-01-01', end='2026-09-30', known_at=NOW, now=NOW), [{**TBILL, 'measure': 'DISCOUNT_RATE'}],
     'YIELD_IS_NOT_TOTAL_RETURN'),
])
def test_malformed_responses_are_rejected_whole_and_never_repaired(label, interface, call, records, code):
    before = copy.deepcopy(records)
    result = call(_connected(interface, records, _prov()))
    assert result.status == 'REJECTED', label
    assert code in {i.code for i in result.issues}, (label, [i.code for i in result.issues])
    assert records == before                                                           # the questionable data is left exactly as sent
    with pytest.raises(CapabilityUnavailable):
        result.records()                                                               # not even the good-looking records are handed over


def test_incomplete_or_impossible_provenance_rejects_the_response():
    call = lambda prov: _connected(providers.EstimatesProvider, [dict(ESTIMATE)], prov).consensus('AAPL', 'eps', '2026Q4', known_at=NOW, now=NOW)
    assert call(_prov()).status == 'OK'
    for missing in ('provider', 'source_id', 'source_timestamp', 'ingested_at', 'known_at', 'schema_version'):
        result = call(_prov(**{missing: ''}))
        assert result.status == 'REJECTED' and 'INCOMPLETE_PROVENANCE' in {i.code for i in result.issues}, missing
    assert 'INCOMPLETE_PROVENANCE' in {i.code for i in call(None).issues}
    assert 'KNOWN_BEFORE_SOURCE' in {i.code for i in call(_prov(known_at='2026-10-01T19:00:00+00:00')).issues}      # known before it existed
    assert 'TIMEZONE_MISSING' in {i.code for i in call(_prov(known_at='2026-10-01T20:05:04')).issues}
    # a connected provider that is not told the time, or does not supply the method, never produces records
    provider = _connected(providers.EstimatesProvider, [dict(ESTIMATE)], _prov())
    assert provider.consensus('AAPL', 'eps', '2026Q4', known_at=NOW).status == 'REJECTED'
    partial = type('OnlyBars', (providers.IntradayMarketDataProvider,), {'name': 'bars-only'})()
    assert partial.trades('SPY', start=NOW, end=NOW, now=NOW).status == 'UNAVAILABLE'


def test_stale_data_and_incomplete_windows_are_flagged():
    stale = quality.validate('intraday_bars', [dict(BAR)], now='2026-10-03T13:30:00Z', provenance=_prov(), max_age=timedelta(hours=1))
    assert stale.codes() == ['STALE_TIMESTAMP'] and not stale.passed
    fresh = quality.validate('intraday_bars', [dict(BAR)], now=NOW, provenance=_prov(), max_age=timedelta(hours=12))
    assert fresh.passed and fresh.records_checked == 1
    window = quality.validate('intraday_bars', [dict(BAR)], now=NOW, provenance=_prov(), expected_window=['2026-09-30', '2026-10-01'])
    assert window.codes() == ['INCOMPLETE_HISTORICAL_WINDOW'] and '1 of 2' in window.issues[0].detail
    assert quality.validate('weather', [{}], now=NOW, provenance=_prov()).codes() == ['UNKNOWN_DOMAIN']
    assert not quality.validate('intraday_bars', [], now=NOW, provenance=_prov()).passed                 # nothing checked is not a pass
    every = {quality.STALE_TIMESTAMP, quality.FUTURE_TIMESTAMP, quality.MISSING_IDENTIFIER, quality.DUPLICATE_RECORD, quality.IMPOSSIBLE_VALUE,
             quality.CONFLICTING_INSTRUMENT_IDENTITY, quality.MISSING_UNITS_OR_CURRENCY, quality.NON_MONOTONIC_TIMESTAMPS,
             quality.INCOMPLETE_HISTORICAL_WINDOW}
    assert len(every) == 9                                                              # the nine checks the order lists, each with its own code
    source = (ROOT / 'firm_lab' / 'quality.py').read_text()
    assert not re.search(r'\br\[[^\]]+\]\s*=[^=]', source) and '.update(' not in source and '.pop(' not in source      # no record is ever modified


def test_each_domain_schema_carries_the_minimum_fields():
    need = {
        'fundamentals': {'required': {'instrument', 'fiscal_period', 'filing_timestamp', 'known_at', 'currency'},
                         'optional': {'revenue', 'operating_income', 'ebitda', 'eps_diluted', 'gross_margin', 'operating_margin', 'free_cash_flow',
                                      'total_debt', 'cash_and_equivalents', 'shares_outstanding', 'invested_capital', 'tax_expense',
                                      'market_capitalization', 'enterprise_value'}},
        'estimates': {'required': {'instrument', 'fiscal_period', 'metric', 'consensus_estimate', 'analyst_count', 'effective_timestamp',
                                   'snapshot_timestamp'}, 'optional': {'prior_consensus', 'revision_magnitude', 'dispersion'}},
        'earnings': {'required': {'instrument', 'event_timestamp', 'session_timing', 'release_source_url'},
                     'optional': {'transcript_source_url', 'transcript_timestamp', 'guidance_sections', 'prior_fiscal_period'}},
        'news': {'required': {'source', 'headline', 'published_timestamp', 'ingestion_timestamp', 'url', 'deduplication_key'},
                 'optional': {'snippet', 'body', 'instruments', 'entities', 'event_type', 'duplicate_group'}},
        'intraday_bars': {'required': {'instrument', 'bar_start', 'open', 'high', 'low', 'close', 'volume', 'session', 'exchange_session_date'},
                          'optional': set()},
        'options_chain': {'required': {'contract_id', 'underlying', 'option_type', 'strike', 'expiration', 'bid', 'ask', 'quote_timestamp', 'volume',
                                       'open_interest', 'provider_implied_volatility'},
                          'optional': {'provider_delta', 'provider_gamma', 'provider_theta', 'provider_vega', 'underlying_bid',
                                       'provider_theoretical_price'}},
        'risk_free': {'required': {'series_id', 'measure', 'observation_date', 'value', 'published_timestamp'}, 'optional': set()},
        'corporate_actions': {'required': {'instrument', 'action_type', 'effective_date', 'announced_timestamp'}, 'optional': {'cash_amount', 'split_ratio'}},
    }
    for domain, fields in need.items():
        schema = schemas.SCHEMAS[domain]
        assert fields['required'] <= set(schema.required), domain
        assert fields['optional'] <= set(schema.optional) | set(schema.required), domain
    assert schemas.SCHEMAS['estimates'].point_in_time == 'snapshot_timestamp'                    # point-in-time history is mandatory
    assert set(schemas.SCHEMAS['corporate_actions'].allowed['action_type']) == {'cash_dividend', 'split', 'spin_off', 'symbol_change', 'merger',
                                                                                 'delisting'}
    assert schemas.SCHEMAS['risk_free'].allowed['measure'] == ('TOTAL_RETURN_INDEX', 'PERIOD_TOTAL_RETURN')
    assert set(schemas.SCHEMAS['intraday_bars'].allowed['session']) == {'pre_market', 'regular', 'post_market'}


def test_greeks_always_say_where_they_came_from(tmp_path):
    assert schemas.greek_field('delta', 'provider') == 'provider_delta' and schemas.greek_field('delta', 'model') == 'model_estimated_delta'
    for name in ('gamma', 'theta', 'vega', 'implied_volatility'):
        assert schemas.greek_field(name, 'provider') == f'provider_{name}' and schemas.greek_field(name, 'model') == f'model_estimated_{name}'
    for bad in (('delta', 'vendor'), ('delta', ''), ('charm', 'provider')):
        with pytest.raises(ValueError):
            schemas.greek_field(*bad)
    both = [{**OPTION, 'model_estimated_delta': '0.43'}]                                # two separate fields may sit side by side
    assert quality.check_greek_namespaces(both) == []
    for bare in ('delta', 'gamma', 'theta', 'vega', 'iv', 'implied_volatility'):
        assert [i.code for i in quality.check_greek_namespaces([{**OPTION, bare: '0.1'}])] == ['UNNAMESPACED_GREEK'], bare
    with _lab(tmp_path).connect() as db:
        columns = [r[1] for r in db.execute('PRAGMA table_info(option_chain_observations)')]
    assert not set(columns) & schemas.BARE_GREEK_NAMES and not [c for c in columns if c.startswith('model_estimated_')]   # nothing is estimated yet


# ---------------------------------------------------------------- capability registry
def test_unavailable_stays_unavailable_and_available_needs_validated_stored_data(tmp_path):
    lab = _lab(tmp_path)
    capabilities.seed(lab)
    capabilities.seed(lab)                                                              # re-seeding changes nothing
    status = lambda: {c['capability']: c['status'] for c in lab.capabilities()}
    assert 'AVAILABLE' not in status().values()                                         # an empty store has nothing available
    for name in ('fundamentals', 'analyst_revisions', 'intraday_bars', 'trade_flow', 'treasury_total_return', 'corporate_actions', 'options_greeks'):
        assert status()[name] == 'UNAVAILABLE'
    # no route to AVAILABLE without a named source, stored records and a passed validation
    for attempt in (lambda: lab.set_capability('fundamentals', 'AVAILABLE'),
                    lambda: lab.set_capability('fundamentals', 'AVAILABLE', 'some vendor', 'trust me'),
                    lambda: capabilities.set_status(lab, 'fundamentals', 'AVAILABLE', 'v', evidence={'provider': 'v', 'records': 0,
                                                                                                      'validation_passed': True, 'validated_at': NOW}),
                    lambda: capabilities.set_status(lab, 'fundamentals', 'AVAILABLE', 'v', evidence={'provider': 'v', 'records': 10,
                                                                                                      'validation_passed': False, 'validated_at': NOW}),
                    lambda: capabilities.set_status(lab, 'fundamentals', 'AVAILABLE', 'v', evidence={'provider': '', 'records': 10,
                                                                                                      'validation_passed': True, 'validated_at': NOW}),
                    lambda: capabilities.promote(lab, 'fundamentals', 'v', 'd', records=10,
                                                 report=quality.validate('fundamentals', [{}], now=NOW, provenance=_prov())),
                    lambda: capabilities.promote(lab, 'fundamentals', 'v', 'd', records=10, report='passed, honest')):
        with pytest.raises(FirmLabError):
            attempt()
    assert status()['fundamentals'] == 'UNAVAILABLE'
    for name in ('fundamentals', 'treasury_total_return', 'live_quotes'):
        with pytest.raises(CapabilityUnavailable):
            capabilities.require(lab, name)
    # the daily data follows the store: closes that validate make it AVAILABLE, with the evidence recorded
    features.ingest_provider_daily_bars(lab, 'VTI', _bars([D(300) + D(i) for i in range(5)]), known_at=KNOWN)
    assert capabilities.confirm_daily_data(lab) == {'daily_closes': 'AVAILABLE', 'daily_baseline_features': 'UNAVAILABLE'}   # no derived value yet
    with lab.connect() as db:
        event = json.loads(db.execute("SELECT payload_json FROM events WHERE kind='CAPABILITY_STATUS' ORDER BY id DESC LIMIT 1").fetchone()[0])
    assert event['capability'] == 'daily_closes' and (event['from'], event['to']) == ('UNAVAILABLE', 'AVAILABLE')
    assert event['evidence']['records'] == 5 and event['evidence']['validation_passed'] is True and event['evidence']['provider']
    # ...and a stored close that cannot be true takes the status away again
    with lab.connect() as db:
        db.execute("INSERT INTO feature_observations (instrument, feature_name, value, source, known_at, ingested_at, exchange_session_date, "
                   "feature_version) VALUES ('VTI','close','-1','test', ?, ?, '2026-09-22', 'baseline-v1')", (KNOWN, KNOWN))
    assert capabilities.confirm_daily_data(lab)['daily_closes'] == 'UNAVAILABLE' and status()['daily_closes'] == 'UNAVAILABLE'
    assert 'IMPOSSIBLE_VALUE' in [c for c in lab.capabilities() if c['capability'] == 'daily_closes'][0]['detail']


def test_an_existing_checkpoint_1_database_is_upgraded_without_touching_deliberate_edits(tmp_path):
    lab = _lab(tmp_path)
    with lab.connect() as db:                                                           # the registry exactly as Checkpoint 1 left it
        for name, state in (('daily_closes', 'AVAILABLE'), ('fundamentals', 'UNAVAILABLE'), ('news_catalysts', 'NOT_STARTED'),
                            ('sec_filings', 'BUILD_ONLY'), ('options_chain', 'BUILD_ONLY')):
            db.execute('INSERT INTO data_capabilities VALUES (?,?,?,?,?)', (name, state, None, 'old', KNOWN))
    capabilities.seed(lab)
    status = {c['capability']: c['status'] for c in lab.capabilities()}
    assert status['news_catalysts'] == 'PARTIAL_EXISTING'                               # upgraded: the existing source is now documented
    assert status['sec_filings'] == 'BUILD_ONLY'                                        # a row someone had edited is left alone
    assert status['daily_closes'] == 'UNAVAILABLE'                                      # it claimed AVAILABLE with nothing stored
    assert status['live_quotes'] == 'PARTIAL_EXISTING' and status['treasury_total_return'] == 'UNAVAILABLE' and len(status) == len(capabilities.INITIAL)
    assert lab.meta('capability_registry_version') == '2'
    capabilities.seed(lab)
    assert {c['capability']: c['status'] for c in lab.capabilities()} == status


def test_no_capability_is_a_silent_stand_in_for_another():
    names = [c for c, *_ in capabilities.INITIAL]
    assert len(names) == len(set(names)) and set(capabilities.READINESS_KEYS) <= set(names) and len(capabilities.DATA_READINESS) == 13
    assert not [c for c, s, *_ in capabilities.INITIAL if s == 'AVAILABLE']             # availability is earned from stored data, never declared
    source = (ROOT / 'firm_lab' / 'capabilities.py').read_text() + (ROOT / 'firm_lab' / 'providers.py').read_text()
    for word in ('fallback', 'default_value', 'estimate_from', 'proxy_for', 'substitute('):
        assert word not in source.lower(), word


# ---------------------------------------------------------------- 70/30 benchmark
def test_the_70_30_ruler_is_exactly_70_30_rebalanced_monthly_and_cannot_be_computed_yet(tmp_path):
    lab = _lab(tmp_path)
    capabilities.seed(lab)
    benchmarks.seed(lab)
    row = {d['benchmark_id']: d for d in benchmarks.definitions(lab)}['FIXED_70_30']
    definition = json.loads(row['definition_json'])
    assert definition['weights'] == {'VTI': '0.70', 'US_TREASURY_BILL_3M_TOTAL_RETURN': '0.30'}
    assert sum(D(w) for w in definition['weights'].values()) == D('1.00') and definition['allocation'] == 'fixed'
    assert definition['rebalancing'] == {'frequency': 'monthly', 'on': 'the first NYSE trading session of each calendar month', 'calendar': 'XNYS'}
    assert definition['rules'] == ['fixed weights', 'no tactical changes', 'the Firm cannot trade, optimize or alter this benchmark',
                                   'no retroactive asset substitution',
                                   'while no clean Treasury-bill total-return data exists, the computation is unavailable']
    assert definition['treasury_bill_series'] is None and row['implementation_status'] == 'DATA_SOURCE_PENDING'
    assert row['name'] == '70% VTI + 30% 3-month U.S. Treasury-bill total return'
    with pytest.raises(CapabilityUnavailable, match='treasury_total_return: UNAVAILABLE'):
        benchmarks.compute_fixed_70_30(lab)
    features.ingest_provider_daily_bars(lab, 'VTI', _bars([D(300) + D(i) for i in range(5)]), known_at=KNOWN)
    benchmarks.record_vti(lab, known_at=KNOWN)
    with lab.connect() as db:                                                           # VTI data alone computes nothing for the 70/30 ruler
        assert db.execute("SELECT COUNT(*) FROM benchmark_observations WHERE benchmark_id='FIXED_70_30'").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM benchmark_observations WHERE benchmark_id='VTI_100'").fetchone()[0] == 5
    text = (ROOT / 'firm_lab' / 'benchmarks.py').read_text()
    for proxy in ('BIL', 'SGOV', 'SHV', 'TBIL', 'DTB3', 'DGS3MO'):                      # no proxy asset and no yield series is wired in
        assert not re.search(rf'(?<![A-Za-z_]){proxy}(?![A-Za-z_])', text), proxy


def test_a_checkpoint_1_definition_is_replaced_once_and_a_ruler_with_history_is_locked(tmp_path):
    lab = _lab(tmp_path)
    benchmarks.seed(lab)
    old = {'weights': {'VTI': '0.70', 'US_TREASURY_BILL_3M_TOTAL_RETURN': '0.30'}, 'allocation': 'fixed', 'rebalancing': 'NOT_SPECIFIED_BY_OPERATOR'}
    with lab.connect() as db:
        db.execute("UPDATE benchmark_definitions SET definition_json=? WHERE benchmark_id='FIXED_70_30'", (json.dumps(old, sort_keys=True),))
    benchmarks.seed(lab)
    benchmarks.seed(lab)
    with lab.connect() as db:
        events = [json.loads(r[0]) for r in db.execute("SELECT payload_json FROM events WHERE kind='BENCHMARK_DEFINITION_CHANGED'")]
        stored = json.loads(db.execute("SELECT definition_json FROM benchmark_definitions WHERE benchmark_id='FIXED_70_30'").fetchone()[0])
    assert len(events) == 1 and events[0]['before']['definition']['rebalancing'] == 'NOT_SPECIFIED_BY_OPERATOR'
    assert events[0]['after']['definition']['rebalancing']['frequency'] == 'monthly' and stored['rebalancing']['frequency'] == 'monthly'
    # once a ruler has observations its definition can no longer be changed
    features.ingest_provider_daily_bars(lab, 'VTI', _bars([D(300) + D(i) for i in range(5)]), known_at=KNOWN)
    benchmarks.record_vti(lab, known_at=KNOWN)
    with lab.connect() as db:
        db.execute("UPDATE benchmark_definitions SET definition_json='{}' WHERE benchmark_id='VTI_100'")
    with pytest.raises(FirmLabError, match='BENCHMARK_DEFINITION_LOCKED'):
        benchmarks.seed(lab)


# ---------------------------------------------------------------- Firm safety (unchanged by this checkpoint)
def test_firm_lab_still_cannot_fill_and_the_official_database_is_still_read_only(tmp_path):
    off = _official_with_capsule(tmp_path)
    before = hashlib.sha256(off.read_bytes()).hexdigest()
    lab = _lab(tmp_path, off)
    report = ingest.ingest_official(lab, off)
    assert report['capsules_ingested'] == 1 and report['daily_data'] == {'daily_closes': 'AVAILABLE', 'daily_baseline_features': 'AVAILABLE'}
    assert lab.mode() == 'BUILD_OBSERVE' and lab.active_experiments() == [] and lab.counts()['experiment_registry'] == 0
    gate = boundary.ExecutionBoundary(lab)
    for order in (dict(instrument='AAPL', asset_class='stock', side='buy', quantity='1'), dict(instrument='SOXX', asset_class='etf', side='buy', quantity='1'),
                  dict(instrument='SPY261016C00765000', asset_class='option', side='buy', quantity='1'),
                  dict(instrument='SOXX', asset_class='etf', side='sell', quantity='1')):
        with pytest.raises(NoFillInBuildObserve):
            gate.submit(**order)
    assert not [t for t in lab.tables() for w in FORBIDDEN_TABLE_WORDS if w in t]       # still no order, fill, position or cash table
    state = view.load(path=lab.path)
    assert state['fills'] == 0 and state['firm_trading_trial'] == 'NOT REGISTERED' and state['refused_fill_attempts'] == 4
    with official.open_official(off) as db:
        for statement in ("INSERT INTO fills (payload_json) VALUES ('{}')", "UPDATE decision_capsules SET cycle_id='x'", 'DELETE FROM decision_capsules'):
            with pytest.raises(sqlite3.Error):
                db.execute(statement)
    assert hashlib.sha256(off.read_bytes()).hexdigest() == before
    assert lab.latest_counterfactual(baseline.STRATEGY_ID)['selected_instrument'] == 'BBB'   # the baseline is exactly what it was


def test_the_data_layer_imports_no_trading_code_and_no_decision_code_reads_it():
    trading = {'agents', 'broker', 'broker_proxy', 'risk', 'data', 'research', 'eval', 'scripts', 'config', 'prompts'}
    network = {'socket', 'urllib', 'http', 'ssl', 'requests', 'subprocess', 'asyncio', 'importlib'}
    for name in ('providers', 'quality', 'schemas', 'provenance', 'capabilities', 'benchmarks'):
        tree = ast.parse((ROOT / 'firm_lab' / f'{name}.py').read_text())
        for node in ast.walk(tree):
            roots = ([a.name.split('.')[0] for a in node.names] if isinstance(node, ast.Import)
                     else [(node.module or '').split('.')[0]] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
            assert not set(roots) & (trading | network), (name, roots)
    # the provider and quality layer is read by no ranking, selection or execution module
    for consumer in ('baseline', 'features', 'boundary', 'official', 'sessions', 'store'):
        tree = ast.parse((ROOT / 'firm_lab' / f'{consumer}.py').read_text())
        imported = {a.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level == 1 for a in node.names}
        modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level == 1}
        assert not ({'providers', 'schemas', 'provenance'} & (imported | modules)), consumer
    assert 'providers' not in (ROOT / 'firm_lab' / 'ingest.py').read_text() and 'providers' not in (ROOT / 'firm_lab' / 'view.py').read_text()


# ---------------------------------------------------------------- UI: Data Readiness
def _ready_rows(html):
    section = html[html.index('id="fl-readiness"'):html.index('id="fl-capabilities"')]
    return section, {m[0]: m[1:] for m in re.findall(
        r'<tr><td data-label="Data"><b>([^<]+)</b></td><td data-label="State"><span class="cat cat-\w+">([^<]+)</span></td>'
        r'<td data-label="Current source">([^<]*)</td><td data-label="Limitation" class="small">([^<]*)</td>'
        r'<td data-label="Required next" class="small">([^<]*)</td></tr>', section)}


def test_data_readiness_renders_truthfully_from_the_registry(tmp_path, capsys):
    off = _official_with_capsule(tmp_path)
    assert cli.main(['ingest', '--official-database', str(off)]) == 0
    capsys.readouterr()
    html = firm_lab_page.render({'firm_lab': firm_lab_page.load(off)})
    section, rows = _ready_rows(html)
    assert '<h2>Data Readiness</h2>' in section and list(rows) == [label for label, *_ in capabilities.DATA_READINESS]
    assert '<th>Data</th><th>State</th><th>Current source</th><th>Limitation</th><th>Required next</th>' in section
    expect = {'Daily closes': 'AVAILABLE', 'Fundamentals': 'UNAVAILABLE', 'Analyst estimates and revisions': 'UNAVAILABLE',
              'Earnings and transcripts': 'UNAVAILABLE', 'SEC filings': 'PARTIAL_EXISTING', 'General news': 'PARTIAL_EXISTING',
              'Intraday 1-minute bars': 'UNAVAILABLE', 'Live quotes and trades': 'PARTIAL_EXISTING', 'Order flow and microstructure': 'UNAVAILABLE',
              'Options chains': 'BUILD_ONLY', 'Options Greeks': 'UNAVAILABLE', 'T-bill total return': 'UNAVAILABLE',
              'Corporate actions and dividends': 'UNAVAILABLE'}
    assert {k: v[0] for k, v in rows.items()} == expect
    for label, (state, source, limitation, required) in rows.items():
        assert limitation and required, label                                           # every row says what is wrong and what is needed
        if state == 'UNAVAILABLE':
            assert source == 'none', label                                              # a missing provider is shown as missing
    assert rows['Daily closes'][1].startswith('Robinhood read gateway') and 'Control A' in rows['Daily closes'][1]
    assert 'yield' in rows['T-bill total return'][2] and 'Infrastructure readiness only' in section
    # it is not a trading feature and shows no intraday anything
    for forbidden in ('<svg', '<canvas', 'chart', 'VWAP', 'signal', 'buy ', 'sell '):
        assert forbidden not in section, forbidden
    assert '<svg' not in html and '<canvas' not in html and 'data-range=' not in html and '<form' not in html
    assert 'Firm trading trial</dt><dd><b>NOT REGISTERED</b>' in html and 'Trial 18' not in html and 'Trial 20' not in html


def test_data_readiness_before_the_database_exists_and_with_an_unknown_status():
    html = firm_lab_page.render({'firm_lab': view.load(path='/nonexistent/firm_lab.db')})
    section, rows = _ready_rows(html)
    assert rows['Daily closes'][0] == 'UNAVAILABLE' and 'AVAILABLE</span>' not in section.replace('UNAVAILABLE</span>', '')
    assert 'not created on this machine yet' in section and len(rows) == 13
    odd = dict(view.load(path='/nonexistent/x.db'), exists=True, mode='BUILD_OBSERVE',
               capabilities=[{'capability': 'fundamentals', 'status': 'LOOKS_GREAT', 'provider': 'x', 'detail': 'd'}])
    section, rows = _ready_rows(firm_lab_page.render({'firm_lab': odd}))
    assert rows['Fundamentals'][0] == 'UNAVAILABLE' and rows['Intraday 1-minute bars'][0] == 'UNAVAILABLE'      # unknown or absent is never better


def test_the_design_documents_exist_and_cover_every_domain():
    sources = (ROOT / 'docs' / 'firm_lab' / 'data_sources.md').read_text()
    matrix = (ROOT / 'docs' / 'firm_lab' / 'provider_matrix.md').read_text()
    for domain in ('Fundamentals', 'Analyst estimates', 'Earnings', 'SEC filings', 'General news', 'Intraday bars', 'Live quotes', 'Order flow',
                   'Options chains', 'Options Greeks', 'Risk-free', 'Corporate actions'):
        assert domain.lower() in sources.lower(), domain
    for heading in ('What Firm Lab needs', 'Minimum required fields', 'Point-in-time', 'Update frequency', 'Historical depth', 'Live requirements',
                    'Licensing', 'Current status'):
        assert heading.lower() in sources.lower(), heading
    assert 'buyer count vs seller count is not a valid concept' in sources.lower().replace('**', '')
    for label in ('STRONG FIT', 'PARTIAL FIT', 'WEAK FIT', 'NOT SUITABLE'):
        assert label in matrix, label
    assert 'yield series is not' in matrix.lower() and 'provider_delta' in sources and 'model_estimated_delta' in sources
