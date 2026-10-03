from decimal import Decimal as D
import pytest


def test_geometry_and_true_range():
    from firm_lab.research_features.ohlcv import geometry,true_range
    g=geometry(D(10),D(14),D(9),D(12))
    assert (g['body'],g['upper_wick'],g['lower_wick'])==(D(2),D(2),D(1))
    assert g['clv']==D('.2')
    assert true_range(D(14),D(9),D(8))==D(6)
    assert geometry(D(10),D(10),D(10),D(10))['clv'] is None
    with pytest.raises(ValueError):
        geometry(D(10),D(9),D(8),D(12))


def test_atr_seed_and_recursion():
    from firm_lab.research_features.ohlcv import atr
    assert atr([D(2)]*14)==D(2)
    assert atr([D(2)]*14+[D(16)])==D(3)
    assert atr([D(2)]*13) is None


def test_volume_prior_window_and_zero():
    from firm_lab.research_features.ohlcv import volume_metrics
    m=volume_metrics([D(10)]*20+[D(30)])
    assert m['volume_mean20']==D(10)
    assert m['rvol20']==D(3)
    assert volume_metrics([D(0)]*21)['rvol20'] is None
    assert volume_metrics([D(0)]*20+[D(1)])['volume_change'] is None
    with pytest.raises(ValueError):
        volume_metrics([D(-1)])


def test_close_only_snapshot_has_no_synthetic_ohlcv():
    from firm_lab.research_features.ohlcv import ohlcv_features
    from firm_lab.research_features.types import Request
    rows=ohlcv_features({'closes':[],'ohlcv':[],'missing_reasons':[]},Request('VTI','2026-09-30','2026-10-03T20:00:00Z'))
    assert rows and all(r.value is None for r in rows)
    assert {r.missing_reason for r in rows}=={'NO_VALIDATED_OHLCV'}


def test_validated_bars_generate_geometry_and_interactions():
    from firm_lab.research_features.ohlcv import ohlcv_features
    from firm_lab.research_features.types import Request,SourceRef
    bars=[dict(open='10',high='12',low='9',close='11',volume='100',session=str(i),
        known_at='2026-10-03T20:00:00+00:00',ref=SourceRef('intraday_bar_observations',str(i),f'{i:064x}','2026-10-03T20:00:00+00:00')) for i in range(21)]
    bars[-1]['volume']='300'
    rows={r.name:r for r in ohlcv_features({'closes':[],'ohlcv':bars,'missing_reasons':[]},Request('VTI','2026-09-30','2026-10-03T20:00:00Z'))}
    assert D(rows['atr14'].value)==3
    assert D(rows['rvol20'].value)==3
    assert D(rows['return_rvol'].value)==0
    assert rows['body'].refs[0].table=='intraday_bar_observations'
