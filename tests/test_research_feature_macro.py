from decimal import Decimal as D


def test_midpoint():
    from firm_lab.research_features.macro import target_midpoint
    assert target_midpoint(D('3.75'),D(4))==D('3.875')


def test_pce_revision_waits_and_unavailable_families_stay_null():
    from firm_lab.research_features.macro import macro_features
    from firm_lab.research_features.types import Request,SourceRef
    def row(value,known,revision):
        return dict(series='pce_headline_mom_sa',value=value,unit='percent_change_mom_sa',period='2026-08',
            revision=revision,published_at=known,known_at=known,ref=SourceRef('macro_observations',str(revision),'a'*64,known))
    snap={'macro':[row('.2','2026-10-01T20:00:00+00:00',0),row('.1','2026-10-03T20:00:00+00:00',1)]}
    rows={r.name:r for r in macro_features(snap,Request('VTI','2026-09-30','2026-10-02T20:00:00Z'))}
    assert D(rows['pce_headline_mom_sa'].value)==D('.2')
    assert rows['cpi_feature_family'].value is None
    assert rows['treasury_yield_feature_family'].value is None


def test_intraday_is_registry_only():
    from firm_lab.research_features.registry import definitions
    rows=[r for r in definitions() if r['family']=='intraday_future']
    assert rows and all(r['current_availability']=='UNAVAILABLE' for r in rows)


def test_rate_changes_require_source_prior_not_sparse_observation_difference():
    from firm_lab.research_features.macro import macro_features
    from firm_lab.research_features.types import Request,SourceRef
    rows=[]
    for p,l,u in [('2026-06-17','3.5','3.75'),('2026-09-16','3.75','4')]:
        for series,value in [('fed_target_lower',l),('fed_target_upper',u)]:
            rows.append(dict(series=series,value=value,unit='percent',period=p,revision=0,
                published_at=p+'T18:00:00+00:00',known_at='2026-10-03T20:00:00+00:00',source='Federal Reserve',
                ref=SourceRef('macro_observations',series+p,'a'*64,'2026-10-03T20:00:00+00:00')))
    result={r.name:r for r in macro_features({'macro':rows},Request('VTI','2026-09-30','2026-10-03T20:00:00Z'))}
    assert result['fed_latest_change_bps'].value is None
    assert result['fed_change_last3'].value is None
