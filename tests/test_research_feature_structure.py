from decimal import Decimal as D


def bars(values):
    from firm_lab.research_features.types import SourceRef
    return [dict(session=f'2026-09-{i+1:02}', value=str(v), known_at=f'2026-09-{i+1:02}T20:00:00+00:00',
        ref=SourceRef('feature_observations',str(i),f'{i:064x}',f'2026-09-{i+1:02}T20:00:00+00:00')) for i,v in enumerate(values)]


def test_pivot_waits_three_confirmations_and_ties_reject():
    from firm_lab.research_features.structure import confirmed_pivots
    rows=bars([1,2,3,9,3,2,1])
    assert confirmed_pivots(rows[:6]) == ()
    p=confirmed_pivots(rows)
    assert len(p)==1 and p[0]['type']=='HIGH'
    assert p[0]['confirmed_session']=='2026-09-07'
    assert p[0]['known_at']=='2026-09-07T20:00:00+00:00'
    assert confirmed_pivots(bars([1,2,3,9,9,2,1])) == ()


def test_pending_replacement_does_not_rewrite_completed_legs():
    from firm_lab.research_features.structure import completed_legs
    p=lambda i,t,v: dict(id=str(i),type=t,value=str(v),session=str(i),known_at=str(i),confirmed_session=str(i),refs=())
    initial=[p(1,'LOW',10),p(2,'HIGH',20),p(3,'HIGH',25)]
    first=completed_legs(initial[:2])
    extended=completed_legs(initial+[p(4,'LOW',15)])
    assert extended[0]==first[0]
    assert extended[1]['start']['value']=='25'
    assert extended[1]['end']['value']=='15'


def test_bounded_clusters_cannot_bridge():
    from firm_lab.research_features.structure import cluster_levels
    groups=cluster_levels([D('100'),D('100.4'),D('100.8')])
    assert groups==((D('100'),D('100.4')),(D('100.8'),))


def test_breakouts_exclude_current_close():
    from firm_lab.research_features.structure import structure_features
    from firm_lab.research_features.types import Request
    snap={'closes':bars([100]*20+[110]),'missing_reasons':[]}
    rows={r.name:r for r in structure_features(snap,Request('VTI','2026-09-21','2026-09-21T20:00:00Z'))}
    assert rows['close_new_high20'].value is True
    assert D(rows['close_distance_high20'].value)==D('.1')


def test_retest_expires_and_requires_prior_cross():
    from firm_lab.research_features.structure import break_retest
    assert break_retest([D(99),D(102),D('100.2')],D(100),'up') == {'broken':True,'age':1,'retest':True}
    assert break_retest([D(99),D(102)]+[D(103)]*5+[D('100.2')],D(100),'up')['retest'] is False
    assert break_retest([D(102),D('100.2')],D(100),'up')['broken'] is False


def test_pivots_sort_and_delayed_capture():
    from firm_lab.research_features.structure import confirmed_pivots
    rows=bars([1,2,3,9,3,2,1])
    assert confirmed_pivots(rows)==confirmed_pivots(list(reversed(rows)))
    rows[-1]['known_at']='2026-10-03T20:00:00+00:00'
    assert confirmed_pivots(rows)[0]['known_at']=='2026-10-03T20:00:00+00:00'


def test_resistance_retest_keeps_crossed_level_not_new_side():
    from firm_lab.research_features.structure import structure_features
    from firm_lab.research_features.types import Request
    values=[105,104,103,100,101,102,103,110,108,106,104,111,'110.3']
    req=Request('VTI','2026-09-13','2026-09-13T20:00:00Z')
    rows={r.name:r for r in structure_features({'closes':bars(values),'missing_reasons':[]},req)}
    state=rows['close_prior_resistance_break_retest'].value
    assert state['retest'] is True and state['age']==1
    assert state['level']=='110'
def test_equal_level_and_distinct_touch_count_are_not_lost():
    from firm_lab.research_features.structure import structure_features
    from firm_lab.research_features.types import Request
    rows={r.name:r for r in structure_features({'closes':bars([5,4,3,1,2,3,4,9,8,7,1])},Request('VTI','2026-09-11','2026-09-11T20:00:00Z'))}
    assert rows['close_level_equality'].value=={'levels':['1']}
    assert 'close_support_touch_count' in rows
