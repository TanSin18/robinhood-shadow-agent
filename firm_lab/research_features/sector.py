"""Effective-dated internal taxonomy and descriptive reference comparisons."""
from decimal import Decimal as D
import json
from .types import timestamp, content_hash, SourceRef
from dataclasses import replace
from .technical import precision, simple_return, realized_vol,sma
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
    rows=[row]
    for symbol,sector,etf,url,evidence in (
        ('AAPL','technology','XLK','https://www.apple.com/newsroom/2025/06/apple-introduces-a-delightful-and-elegant-new-software-design/', 'Issuer describes integrated device hardware and software'),
        ('NVDA','technology','XLK','https://www.nvidia.com/en-us/about-nvidia/', 'Issuer describes accelerated computing chips, systems and software'),
        ('AMZN','consumer_discretionary','XLY','https://www.aboutamazon.com/what-we-do', 'Internal retail classification; issuer also reports cloud, devices and entertainment businesses'),
        ('GOOGL','communication_services','XLC','https://about.google/', 'Internal information and communications classification from Google product description'),
        ('META','communication_services','XLC','https://www.meta.com/about/company-info/', 'Issuer describes social connection products Facebook, Instagram, Messenger and WhatsApp')):
        item=dict(instrument=symbol,sector=sector,etf=etf,version='internal-v1',
            effective_from='2026-10-03',effective_to=None,known_at='2026-10-03T23:11:03+00:00',
            source_urls=[url,row['source_urls'][1]],evidence=evidence+'; internal classification, not historical GICS',proxy=False)
        item['content_hash']=content_hash(item)
        rows.append(item)
    return tuple(rows)


def mapping_at(rows,instrument,cutoff,session):
    eligible=[r for r in rows if r.get('kind','CLASSIFICATION')=='CLASSIFICATION' and r['instrument']==instrument and timestamp(r['known_at'])<=timestamp(cutoff)
              and r['effective_from']<=session and (not r.get('effective_to') or session<r['effective_to'])]
    if not eligible:
        return None
    latest=max(timestamp(r['known_at']) for r in eligible)
    selected=[r for r in eligible if timestamp(r['known_at'])==latest]
    if len(selected)!=1:
        raise ValueError('CONFLICTING_MAPPING')
    return selected[0]


def validate_mapping_record(record):
    body={k:v for k,v in record.items() if k not in ('content_hash','ref')}
    if (content_hash(body)!=record.get('content_hash') or not record.get('version') or
        not record.get('source_urls') or not record.get('effective_from')):
        raise ValueError('INVALID_MAPPING_EVIDENCE')
    timestamp(record['known_at'])
    if record.get('kind','CLASSIFICATION') not in ('CLASSIFICATION','ETF_MEMBERSHIP','CONSTITUENTS'):
        raise ValueError('INVALID_MAPPING_KIND')
    return record


def load_sector_context(db,request):
    """Read versioned evidence; never synthesize historical membership."""
    db.execute('PRAGMA query_only=ON')
    rows={r['content_hash']:r for r in current_mappings()}
    subset=dict(kind='ETF_MEMBERSHIP',members=['XLK','XLY','XLC'],version='observed-three-sector-subset-v1',
        effective_from='2026-10-03',effective_to=None,known_at='2026-10-03T23:11:03+00:00',
        source_urls=[current_mappings()[0]['source_urls'][1]],
        evidence='Fixed internal comparison subset, not all sectors and not constituent breadth')
    subset['content_hash']=content_hash(subset)
    rows[subset['content_hash']]=subset
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='research_sector_mappings'").fetchone():
        for (payload,) in db.execute('SELECT payload FROM research_sector_mappings'):
            row=validate_mapping_record(json.loads(payload))
            rows[row['content_hash']]=row
    available=[r for r in rows.values() if timestamp(r['known_at'])<=request.knowledge_cutoff]
    classifications=[r for r in available if r.get('kind','CLASSIFICATION')=='CLASSIFICATION']
    mapping=mapping_at(classifications,request.instrument,request.knowledge_cutoff,request.as_of_session)
    def select(kind):
        candidates=[r for r in available if r.get('kind')==kind and eligible_membership(r,request)]
        if kind=='CONSTITUENTS':
            candidates=[r for r in candidates if (mapping and r.get('sector')==mapping['sector']) or r.get('instrument')==request.instrument]
        if not candidates:
            return None
        latest=max(timestamp(r['known_at']) for r in candidates)
        latest_rows=[r for r in candidates if timestamp(r['known_at'])==latest]
        if len(latest_rows)!=1:
            raise ValueError('CONFLICTING_MEMBERSHIP')
        return latest_rows[0]
    return {'mappings':classifications,'sector_membership_record':select('ETF_MEMBERSHIP'),
            'constituent_record':select('CONSTITUENTS')}


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


def eligible_membership(record,request):
    if not record or timestamp(record['known_at'])>request.knowledge_cutoff or record['effective_from']>request.as_of_session or (record.get('effective_to') and request.as_of_session>=record['effective_to']):
        return None
    body={k:v for k,v in record.items() if k not in ('content_hash','ref')}
    if (content_hash(body)!=record.get('content_hash') or not record.get('version') or
        not record.get('source_urls') or not record.get('members') or len(set(record['members']))!=len(record['members'])):
        raise ValueError('INVALID_MEMBERSHIP_EVIDENCE')
    return record


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
    membership_record=eligible_membership(snapshot.get('sector_membership_record'),request)
    constituent_record=eligible_membership(snapshot.get('constituent_record'),request)
    membership=tuple(membership_record['members']) if membership_record else ()
    constituents=tuple(constituent_record['members']) if constituent_record else ()
    contributing=[b for s in sorted(set(membership+constituents)) for b in references.get(s,[])]
    all_bars=own+etf+vti+contributing
    make=result_builder({**snapshot,'closes':all_bars},request,__file__)
    values={}
    for n in (5,10,20,63,126,252):
        values[f'excess_vti_price_return{n}']=relative_return(own,vti,n)
        values[f'sector_excess_price_return{n}']=relative_return(own,etf,n)
        values[f'sector_etf_price_return{n}']=simple_return([D(b['value']) for b in etf],n)
    values['sector_vol20']=realized_vol([D(b['value']) for b in etf],20)
    returns={s:simple_return([D(b['value']) for b in references.get(s,[])],20) for s in membership}
    ranks=leadership(returns,membership)
    previous={s:simple_return([D(b['value']) for b in references.get(s,[])][:-5],20) for s in membership}
    old=leadership(previous,membership)
    # Change over five sessions needs the same membership at both endpoints.
    if membership and any(len(references.get(s,[]))<6 or membership_record['effective_from']>references[s][-6]['session'] for s in membership):
        old=None
    selected=mapping['etf'] if mapping else request.instrument
    values['sector_leadership_rank20']=ranks.get(selected) if ranks else None
    values['sector_leadership_change5']=ranks[selected]-old[selected] if ranks and old and selected in ranks else None
    if constituents and all(len(references.get(s,[]))>=2 and references[s][-1]['session']==request.as_of_session for s in constituents):
        values['sector_breadth']=D(sum(D(references[s][-1]['value'])>D(references[s][-2]['value']) for s in constituents))/len(constituents)
        if all(len(references[s])>=50 for s in constituents):
            values['sector_sma50_participation']=D(sum(D(references[s][-1]['value'])>sma([D(b['value']) for b in references[s]],50) for s in constituents))/len(constituents)
    out=[]
    for d in sector_definitions():
        name=d['name']
        reason='NO_POINT_IN_TIME_CONSTITUENTS' if name in ('sector_breadth','sector_sma50_participation') else 'NO_ELIGIBLE_MAPPING_OR_REFERENCE_HISTORY'
        row=make(name,'sector',values.get(name),d['unit'],
            audit={'mapping':{k:v for k,v in mapping.items() if k!='ref'} if mapping else None,
                   'reference_membership':list(membership),'constituents':list(constituents),
                   'breadth_definition':'fraction of complete documented constituent set with positive one-session close return',
                   'basis':'PRICE_RETURN_NOT_TOTAL_RETURN'},reason=reason)
        record=constituent_record if name in ('sector_breadth','sector_sma50_participation') else membership_record if name.startswith('sector_leadership') else None
        if record and row.value is not None:
            ref=SourceRef('research_sector_mappings',record['content_hash'],record['content_hash'],record['known_at'])
            row=replace(row,known_at=max(row.known_at,ref.known_at),refs=row.refs+(ref,))
        if mapping and row.value is not None and not name.startswith('excess_vti'):
            ref=mapping.get('ref') or SourceRef('research_sector_mappings',mapping['content_hash'],mapping['content_hash'],mapping['known_at'])
            row=replace(row,known_at=max(row.known_at,ref.known_at),refs=row.refs+(ref,))
        out.append(row)
    return tuple(out)
