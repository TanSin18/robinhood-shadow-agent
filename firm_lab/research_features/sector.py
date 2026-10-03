"""Effective-dated internal taxonomy and descriptive reference comparisons."""
from decimal import Decimal as D
from .types import timestamp, content_hash, SourceRef
from dataclasses import replace
from .technical import precision, simple_return, realized_vol
from .structure import result_builder, definition


def current_mappings():
    """Explicitly current internal classification, not historical GICS."""
    row=dict(instrument='MSFT',sector='technology',etf='XLK',version='internal-v1',
        effective_from='2026-10-03',effective_to=None,known_at='2026-10-03T21:50:02+00:00',
        source_urls=['https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630.htm',
                     'https://www.ssga.com/us/en/intermediary/capabilities/equities/sector-investing/select-sector-etfs'],
        evidence='Issuer technology description and official sector fund mandate; internal classification only',
        proxy=False)
    row['content_hash']=content_hash(row)
    return (row,)


def mapping_at(rows,instrument,cutoff,session):
    eligible=[r for r in rows if r['instrument']==instrument and timestamp(r['known_at'])<=timestamp(cutoff)
              and r['effective_from']<=session and (not r.get('effective_to') or session<r['effective_to'])]
    if not eligible:
        return None
    latest=max(timestamp(r['known_at']) for r in eligible)
    selected=[r for r in eligible if timestamp(r['known_at'])==latest]
    if len(selected)!=1:
        raise ValueError('CONFLICTING_MAPPING')
    return selected[0]


@precision
def relative_return(a,b,n):
    if len(a)<=n or len(b)<=n or [x['session'] for x in a[-n-1:]] != [x['session'] for x in b[-n-1:]]:
        return None
    if {r.get('price_basis','UNSPECIFIED') for r in a[-n-1:]+b[-n-1:]}.__len__()!=1:
        return None
    return simple_return([D(x['value']) for x in a],n)-simple_return([D(x['value']) for x in b],n)


@precision
def leadership(returns,membership):
    if set(returns)!=set(membership) or any(v is None for v in returns.values()):
        return None
    return {name:1+D(sum(v>value for v in returns.values()))+D(sum(v==value for v in returns.values())-1)/2 for name,value in returns.items()}


def sector_definitions():
    out=[]
    for n in (5,10,20,63,126,252):
        for prefix in ('excess_vti_price_return','sector_excess_price_return','sector_etf_price_return'):
            out.append(definition(f'{prefix}{n}','sector','fraction','aligned same-basis simple price returns; difference for excess',n+1))
    for name,unit in (('sector_vol20','annualized_fraction'),('sector_leadership_rank20','rank'),
                      ('sector_leadership_change5','rank_change'),('sector_breadth','fraction'),('sector_sma50_participation','fraction')):
        out.append(definition(name,'sector',unit,'effective-dated mapping; fixed observed membership; no historical imputation',51))
    return tuple(out)


@precision
def sector_features(snapshot,request):
    mapping=mapping_at(snapshot.get('mappings',[]),request.instrument,request.knowledge_cutoff,request.as_of_session)
    references=snapshot.get('reference_closes',{})
    own=snapshot['closes']
    etf=references.get(mapping['etf'],[]) if mapping else []
    vti=references.get('VTI',[])
    all_bars=own+etf+vti
    make=result_builder({**snapshot,'closes':all_bars},request,__file__)
    values={}
    for n in (5,10,20,63,126,252):
        values[f'excess_vti_price_return{n}']=relative_return(own,vti,n)
        values[f'sector_excess_price_return{n}']=relative_return(own,etf,n)
        values[f'sector_etf_price_return{n}']=simple_return([D(b['value']) for b in etf],n)
    values['sector_vol20']=realized_vol([D(b['value']) for b in etf],20)
    membership=tuple(snapshot.get('sector_membership',()))
    returns={s:simple_return([D(b['value']) for b in references.get(s,[])],20) for s in membership}
    ranks=leadership(returns,membership)
    previous={s:simple_return([D(b['value']) for b in references.get(s,[])][:-5],20) for s in membership}
    old=leadership(previous,membership)
    selected=mapping['etf'] if mapping else request.instrument
    values['sector_leadership_rank20']=ranks.get(selected) if ranks else None
    values['sector_leadership_change5']=ranks[selected]-old[selected] if ranks and old and selected in ranks else None
    out=[]
    for d in sector_definitions():
        name=d['name']
        reason='NO_POINT_IN_TIME_CONSTITUENTS' if name in ('sector_breadth','sector_sma50_participation') else 'NO_ELIGIBLE_MAPPING_OR_REFERENCE_HISTORY'
        row=make(name,'sector',values.get(name),d['unit'],
            audit={'mapping':{k:v for k,v in mapping.items() if k!='ref'} if mapping else None,
                   'reference_membership':list(membership),'basis':'PRICE_RETURN_NOT_TOTAL_RETURN'},reason=reason)
        if mapping and row.value is not None and not name.startswith('excess_vti'):
            ref=mapping.get('ref') or SourceRef('research_sector_mappings',mapping['content_hash'],mapping['content_hash'],mapping['known_at'])
            row=replace(row,known_at=max(row.known_at,ref.known_at),refs=row.refs+(ref,))
        out.append(row)
    return tuple(out)
