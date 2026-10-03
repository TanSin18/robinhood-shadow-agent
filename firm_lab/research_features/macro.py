"""Factual Fed/PCE context only. There is no macro model or score."""
from datetime import date
from decimal import Decimal as D
from .inputs import eligible_rows
from .structure import result_builder, definition
from .technical import precision


@precision
def target_midpoint(lower,upper):
    if not lower.is_finite() or not upper.is_finite() or lower>upper:
        raise ValueError('INVALID_TARGET_RANGE')
    return (lower+upper)/2


def macro_definitions():
    rows=[]
    for name,unit in (('fed_target_lower','percent'),('fed_target_upper','percent'),('fed_target_midpoint','percent'),
        ('fed_latest_change_bps','basis_points'),('days_since_fomc','days'),('fed_change_last3','basis_points'),
        ('fed_hikes_last3','count'),('fed_cuts_last3','count'),('fed_holds_last3','count'),
        ('pce_headline_mom_sa','percent_change_mom_sa'),('pce_core_mom_sa','percent_change_mom_sa'),('days_since_pce','days')):
        rows.append(definition(name,'macro_context',unit,'eligible original-source facts; point-in-time revisions; distinct Fed meeting periods',0))
    for name in ('cpi','labor','treasury_yield','market_volatility'):
        rows.append(definition(name+'_feature_family','macro_context','state','no validated input; never substitute a proxy',0))
    return tuple({**d,'required_inputs':['validated_fed_or_pce'],'cadence':'event'} for d in rows)


def intraday_definitions():
    return tuple({**definition(name,'intraday_future',unit,'registry only; licensed time-stamped trades/quotes/bars required',0),
        'required_inputs':['validated_intraday_trades_quotes_bars'],'cadence':'intraday','current_availability':'UNAVAILABLE'}
        for name,unit in (('vwap','price'),('vwap_distance','fraction'),('opening_range_high','price'),
            ('opening_range_low','price'),('opening_range_breakout','fraction'),('time_of_day_rvol','ratio'),
            ('intraday_range','price'),('intraday_atr','price'),('nbbo_spread','price'),('quote_imbalance','fraction'),
            ('signed_volume','shares'),('aggressive_buy_proxy','shares'),('aggressive_sell_proxy','shares')))


@precision
def macro_features(snapshot,request):
    rows=eligible_rows(snapshot.get('macro',[]),request.knowledge_cutoff)
    latest={}
    for row in rows:
        if row['series'] not in ('fed_target_lower','fed_target_upper','pce_headline_mom_sa','pce_core_mom_sa') or row['period']>request.as_of_session:
            continue
        expected='percent' if row['series'].startswith('fed') else 'percent_change_mom_sa'
        if row['unit']!=expected:
            continue
        key=(row['series'],row['period'])
        previous=latest.get(key)
        order=(row['known_at'],row['revision'])
        if previous is None or order>(previous['known_at'],previous['revision']):
            latest[key]=row
        elif order==(previous['known_at'],previous['revision']) and row['value']!=previous['value']:
            raise ValueError('CONFLICTING_MACRO_REVISION')
    eligible=list(latest.values())
    events=eligible_rows(snapshot.get('macro_events',[]),request.knowledge_cutoff)
    make=result_builder({'closes':eligible+events},request,__file__)
    values={}
    audit={'basis':'FACTUAL_MACRO_NO_MODEL'}
    periods=sorted({p for s,p in latest if s=='fed_target_lower' and ('fed_target_upper',p) in latest})
    if periods:
        p=periods[-1]
        lower,upper=latest['fed_target_lower',p],latest['fed_target_upper',p]
        # Reject differently published/source bounds rather than mix decisions.
        if lower.get('published_at')==upper.get('published_at') and lower.get('source')==upper.get('source'):
            values['fed_target_lower'],values['fed_target_upper']=D(lower['value']),D(upper['value'])
            values['fed_target_midpoint']=target_midpoint(D(lower['value']),D(upper['value']))
            values['days_since_fomc']=(date.fromisoformat(request.as_of_session)-date.fromisoformat(p)).days
            changes=[]
            for period in periods:
                pair=[]
                for series in ('fed_target_lower','fed_target_upper'):
                    observation=latest[series,period]
                    matching=[e for e in events if e.get('period')==period and e.get('series')==series
                        and e.get('prior_value') is not None and e.get('released_value')==observation['value']
                        and e.get('published_at')==observation['published_at'] and e.get('source')==observation.get('source')]
                    event=max(matching,key=lambda e:e['known_at']) if matching else None
                    pair.append((D(event['released_value'])-D(event['prior_value']))*100 if event else None)
                changes.append(pair[0] if pair[0] is not None and pair[0]==pair[1] else None)
            if changes:
                values['fed_latest_change_bps']=changes[-1]
            # A sparse sample of observed decisions is not proof of the last three meetings.
            if snapshot.get('fed_meeting_coverage_complete') is True and len(changes)>=3 and all(x is not None for x in changes[-3:]):
                values['fed_change_last3']=sum(changes[-3:])
                for name,test in (('hikes',lambda x:x>0),('cuts',lambda x:x<0),('holds',lambda x:x==0)):
                    values['fed_'+name+'_last3']=sum(test(x) for x in changes[-3:])
    pce=[]
    for series in ('pce_headline_mom_sa','pce_core_mom_sa'):
        candidates=[r for r in eligible if r['series']==series]
        if candidates:
            r=max(candidates,key=lambda r:r['period'])
            values[series]=D(r['value'])
            pce.append(r)
    if pce:
        age=(date.fromisoformat(request.as_of_session)-date.fromisoformat(max(r['published_at'] for r in pce)[:10])).days
        values['days_since_pce']=age if age>=0 else None
    return tuple(make(d['name'],'macro_context',values.get(d['name']),d['unit'],audit=audit,
        reason='NO_VALIDATED_INPUT' if d['name'].endswith('_family') else 'INSUFFICIENT_VALIDATED_HISTORY') for d in macro_definitions())
