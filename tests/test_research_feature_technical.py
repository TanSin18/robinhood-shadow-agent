from decimal import Decimal as D
import pytest


def test_sma_return_and_rsi():
    from firm_lab.research_features.technical import sma, simple_return, rsi_wilder
    assert sma([D(1), D(2), D(3)], 3) == D(2)
    assert simple_return([D(10), D(11)], 1) == D('.1')
    assert rsi_wilder([D(10)] * 15) == D(50)
    assert rsi_wilder(list(map(D, range(1, 16)))) == D(100)
    assert rsi_wilder(list(map(D, range(16, 1, -1)))) == D(0)
    assert rsi_wilder([D(10)] * 14) is None
    assert simple_return([D(10)] * 20, 20) is None


def test_ema_seeding_and_volatility():
    from firm_lab.research_features.technical import ema, realized_vol
    assert ema(list(map(D, range(1, 14))), 12) == D('7.5')
    assert ema([D(1)] * 11, 12) is None
    assert realized_vol([D(100)] * 21, 20) == D(0)
    # log(2), log(1/2): sample variance=2*log(2)^2.
    assert abs(realized_vol([D(1), D(2), D(1)], 2) - D('15.561115609581902')) < D('.00000001')


def test_tied_percentile_and_missing_values():
    from firm_lab.research_features.technical import percentile
    assert percentile([D(7)] * 252) == D(50)
    assert percentile([D(7)] * 251) is None
    assert abs(percentile([D(1)] * 251 + [D(2)]) - D('99.80158730158730158730158730')) < D('1e-25')


@pytest.mark.parametrize('values', [[D('NaN')], [D(0)], [D(-1)]])
def test_invalid_prices_fail(values):
    from firm_lab.research_features.technical import sma
    with pytest.raises(ValueError):
        sma(values, 1)


def snapshot(n=300):
    from firm_lab.research_features.types import SourceRef
    return {'closes': [{'session': str(i), 'value': '100', 'known_at': '2026-10-03T20:00:00+00:00',
        'ref': SourceRef('feature_observations', str(i), f'{i:064x}', '2026-10-03T20:00:00+00:00')}
        for i in range(n)], 'missing_reasons': []}


def test_flat_family_outputs_and_provenance():
    from firm_lab.research_features.technical import technical_features
    from firm_lab.research_features.types import Request
    rows = {r.name: r for r in technical_features(snapshot(), Request('VTI', '2026-09-30', '2026-10-03T20:00:00Z'))}
    assert rows['sma200'].value == '100'
    assert D(rows['macd_histogram'].value) == 0
    assert D(rows['realized_vol20'].value) == 0
    assert D(rows['return252'].value) == 0
    assert rows['sma200'].refs
    assert rows['sma_ordering'].value['groups'] == [['C', 'SMA20', 'SMA50', 'SMA100', 'SMA200']]
    assert all('signal' not in r.name for r in rows.values())


def test_short_history_reports_unavailable_not_zero():
    from firm_lab.research_features.technical import technical_features
    from firm_lab.research_features.types import Request
    rows = {r.name: r for r in technical_features(snapshot(3), Request('VTI', '2026-09-30', '2026-10-03T20:00:00Z'))}
    assert rows['sma200'].value is None
    assert rows['sma200'].missing_reason == 'INSUFFICIENT_HISTORY'
