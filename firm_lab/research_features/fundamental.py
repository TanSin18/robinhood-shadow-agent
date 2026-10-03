"""Comparable-period SEC facts. No synthetic quarters or missing-debt imputation."""
from datetime import date
from decimal import Decimal as D
from .technical import precision
from .types import timestamp
from .inputs import eligible_rows
from .structure import result_builder, definition

GROWTH_FIELDS=('revenue','operating_income','net_income','eps_diluted','operating_cash_flow','diluted_shares_weighted_average')
RATIOS={'operating_margin':('operating_income','revenue'), 'net_margin':('net_income','revenue'),
    'gross_margin':('gross_profit','revenue'), 'ocf_net_income':('operating_cash_flow','net_income'),
    'ocf_margin':('operating_cash_flow','revenue'), 'cash_revenue':('cash_and_equivalents','revenue'),
    'debt_revenue':('total_debt','revenue'), 'debt_ocf':('total_debt','operating_cash_flow')}


@precision
def signed_growth(current,prior):
    return (current-prior)/abs(prior) if prior else None


def fundamental_definitions():
    out=[]
    for field in GROWTH_FIELDS:
        out.append(definition(field+'_yoy','fundamentals','fraction','(current-prior)/abs(prior), equivalent fiscal duration and quarter',0))
    out.append(definition('revenue_qoq','fundamentals','fraction','standalone3M periods only; no YTD subtraction',0))
    for name in RATIOS:
        out.append(definition(name,'fundamentals','ratio','compatible units, exact duration match; balance instant equals duration end',0))
    out.append(definition('dilution_trend','fundamentals','state','direction of comparable weighted-average diluted-share YoY change',0))
    return tuple({**d,'required_inputs':['confirmed_sec_normalized_facts'],'cadence':'event',
        'point_in_time':'filing acceptance AND local knowledge <= cutoff'} for d in out)


def _facts(snapshot,request):
    rows=[r for r in eligible_rows(snapshot['facts'],request.knowledge_cutoff)
          if r.get('confirmed_in_filing')=='CONFIRMED' and r['period_end']<=request.as_of_session]
    selected={}
    def order(r):
        return (timestamp(r['known_at']),timestamp(r['accepted_timestamp']),int(r.get('version',0)))
    for row in rows:
        field=row['normalized_field']
        required='USD/shares' if field=='eps_diluted' else 'shares' if field=='diluted_shares_weighted_average' else 'USD'
        if row['unit']!=required:
            continue
        value=D(row['value'])
        if not value.is_finite():
            continue
        key=(field,row.get('period_start'),row['period_end'],row['period_type'])
        prior=selected.get(key)
        ordering=order(row)
        if prior is None or ordering>order(prior):
            selected[key]=row
        elif ordering==order(prior) and prior['value']!=row['value']:
            raise ValueError('CONFLICTING_FACT_REVISION')
    return list(selected.values())


@precision
def fundamental_features(snapshot,request):
    facts=_facts(snapshot,request)
    make=result_builder({'closes':facts},request,__file__)
    fields={name:sorted([f for f in facts if f['normalized_field']==name],key=lambda r:(r['period_end'],r['known_at']),reverse=True)
            for name in set(GROWTH_FIELDS)|{x for pair in RATIOS.values() for x in pair}}
    values={}
    audits={}
    for field in GROWTH_FIELDS:
        rows=fields[field]
        if not rows:
            continue
        current=rows[0]
        try:
            year=int(current['filing_fiscal_year'])
        except (ValueError,TypeError,KeyError):
            continue
        prior=next((r for r in rows[1:] if r['period_type']==current['period_type'] and
            r.get('filing_fiscal_period')==current.get('filing_fiscal_period') and
            str(r.get('filing_fiscal_year'))==str(year-1) and
            350<=(date.fromisoformat(current['period_end'])-date.fromisoformat(r['period_end'])).days<=380),None)
        if prior:
            values[field+'_yoy']=signed_growth(D(current['value']),D(prior['value']))
            audits[field+'_yoy']={'current_period':current['period_end'],'prior_period':prior['period_end'],'duration':current['period_type']}
    revenues=fields['revenue']
    if revenues and revenues[0]['period_type']=='3M':
        current=revenues[0]
        prior=next((r for r in revenues[1:] if r['period_type']=='3M' and
            (date.fromisoformat(current['period_start'])-date.fromisoformat(r['period_end'])).days==1),None)
        if prior:
            values['revenue_qoq']=signed_growth(D(current['value']),D(prior['value']))
    for name,(numerator,denominator) in RATIOS.items():
        if not fields[numerator]:
            continue
        a=fields[numerator][0]
        instant=numerator in ('cash_and_equivalents','total_debt')
        b=next((r for r in fields[denominator] if r['period_end']==a['period_end'] and
                (instant or (r.get('period_start')==a.get('period_start') and r['period_type']==a['period_type']))),None)
        if b and D(b['value'])!=0:
            values[name]=D(a['value'])/D(b['value'])
            audits[name]={'duration':b['period_type'],'period_start':b.get('period_start'),'period_end':b['period_end']}
    shares=values.get('diluted_shares_weighted_average_yoy')
    values['dilution_trend']={'direction':'INCREASE' if shares>0 else 'DECREASE' if shares<0 else 'UNCHANGED'} if shares is not None else None
    return tuple(make(d['name'],'fundamentals',values.get(d['name']),d['unit'],
        audit={'basis':'SEC_CONFIRMED_AS_REPORTED',**audits.get(d['name'],{})},
        reason='MISSING_OR_INCOMPATIBLE_CONFIRMED_FACTS') for d in fundamental_definitions())
