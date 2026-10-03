"""Narrow official-release parsers. Source text is data, never model input.

No publication-time defaults, broker, credentials, scheduler or execution imports.
Unsupported formats fail explicitly; no latest-value API is substituted for a vintage.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html import unescape
import hashlib
import re
import csv
import io
from zoneinfo import ZoneInfo

from firm_lab.errors import FirmLabError
from firm_lab.macro import SERIES, validate_observation, validate_event

MONTHS = {m.lower():i for i,m in enumerate(('January','February','March','April','May','June','July','August','September','October','November','December'),1)}
MONTH = '('+'|'.join(MONTHS)+')'
DATE = MONTH + r'\s+(\d{1,2}),?\s+(\d{4})'
ET = ZoneInfo('America/New_York')
PCE_CONVENTIONS='https://www.bea.gov/news/pio-release-additional-information'


def text(html):
    html = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', html, flags=re.I|re.S)
    return ' '.join(unescape(re.sub(r'<[^>]*>', ' ', html)).split())


def one(pattern, value, code):
    match = re.search(pattern, value, re.I|re.S)
    if not match:
        raise FirmLabError(code)
    return match


def publication(kind, html):
    s = text(html)
    if kind == 'fed':
        # Date must come from the publisher's article-date element, not navigation.
        day = one(DATE, text(one(r'<p\b[^>]*class=["\']article__time["\'][^>]*>(.*?)</p>', html, 'MISSING_PUBLICATION_TIME')[1]), 'MISSING_PUBLICATION_TIME')
        clock = one(r'For release at (\d{1,2}):(\d{2})\s*([ap])\.m\.\s+(EDT|EST)', s, 'MISSING_PUBLICATION_TIME')
    else:
        header = one(r'(?:embargoed until(?: release at)?)\s+(\d{1,2}):(\d{2})\s*([ap])\.m\.\s*(?:\((ET)\)|(EDT|EST))[,\s]+(?:\w+,?\s+)?'+DATE,
                     s, 'MISSING_PUBLICATION_TIME')
        clock = header
        day = (None, header[6], header[7], header[8])
    if not 1<=int(clock[1])<=12 or not 0<=int(clock[2])<60:
        raise FirmLabError('INVALID_PUBLICATION_CLOCK')
    hour, minute = int(clock[1]) % 12 + (12 if clock[3].lower() == 'p' else 0), int(clock[2])
    zone = clock[4] if kind == 'fed' else (clock[4] or clock[5])
    stamp = datetime(int(day[3]),MONTHS[day[1].lower()],int(day[2]),hour,minute,tzinfo=ET)
    if zone.upper() != 'ET' and stamp.tzname() != zone.upper():
        raise FirmLabError('PUBLICATION_ZONE_MISMATCH')
    return stamp.astimezone(timezone.utc).isoformat()


def fraction(value):
    value=value.strip().replace('–','-')
    if '-' in value:
        whole, part=value.split('-',1)
        return Decimal(whole)+fraction(part)
    if '/' in value:
        a,b=value.split('/')
        return Decimal(a)/Decimal(b)
    return Decimal(value)


def cells(html):
    return [[text(c) for c in re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]>', r, re.I|re.S)]
            for r in re.findall(r'<tr\b[^>]*>(.*?)</tr>',html,re.I|re.S)]


def parse_release(kind, response, *, now, include_prior=False):
    if not response.ok:
        raise FirmLabError(f'HTTP_{response.status}')
    if kind not in ('fed','cpi','pce','labor'):
        raise FirmLabError('UNSUPPORTED_MACRO_PARSER')
    html=response.body.decode('utf-8',errors='strict')
    s=text(html)
    published=publication(kind,html)
    source={'fed':'Federal Reserve','cpi':'BLS','labor':'BLS','pce':'BEA'}[kind]
    metadata={'underlying_source':source,'publication_evidence':'explicit publisher release/embargo header',
              'vintage_basis':'archived release captured locally; local version zero does not certify original economic vintage'}
    if kind=='fed':
        one(r'Federal Reserve issues FOMC statement',s,'NOT_FOMC_STATEMENT')
        target=one(r'(?:decided to|will)\s+(raise|lower|maintain)\s+the target range for the federal funds rate\s+(?:by\s+([\d/.-]+)\s+percentage point\s+to|at)\s+([\d/.-]+)\s+to\s+([\d/.-]+)\s+percent',s,'FOMC_TARGET_UNSUPPORTED')
        lo,hi=fraction(target[3]),fraction(target[4])
        if lo>hi: raise FirmLabError('FOMC_RANGE_INVALID')
        change=Decimal(0) if target[1].lower()=='maintain' else fraction(target[2])*100*(-1 if target[1].lower()=='lower' else 1)
        period=published[:10]
        values=[('fed_target_lower',str(lo)),('fed_target_upper',str(hi))]
        metadata.update(meeting_date=period,change_basis_points=format(change.normalize(),'f'),change_basis='publisher explicit decision wording',
                        source_series_ids=['FOMC target range lower','FOMC target range upper'],seasonal_adjustment='not applicable')
    else:
        title={'cpi':r'CONSUMER PRICE INDEX\s*[-—–]\s*','labor':r'(?:THE )?EMPLOYMENT SITUATION\s*[-—–]\s*','pce':r'Personal Income and Outlays,?\s*'}[kind]
        d=one(title+MONTH+r'\s+(\d{4})',s,'RELEASE_PERIOD_UNAVAILABLE')
        period=f'{d[2]}-{MONTHS[d[1].lower()]:02d}'
        if kind=='pce':
            tables=[t for t in re.findall(r'<table\b[^>]*>.*?</table>',html,re.I|re.S) if 'PCE price index excluding food and energy' in text(t)]
            if len(tables)!=1 or not re.search('Percent change from preceding month',text(tables[0]),re.I):
                raise FirmLabError('PCE_TABLE_IDENTITY_UNAVAILABLE')
            # The selected table establishes monthly units; the publisher-linked
            # conventions establish the release's seasonal basis, not an unrelated paragraph.
            if re.search(r'(?:not seasonally adjusted|unadjusted)',text(tables[0]),re.I):
                raise FirmLabError('PCE_SEASONAL_IDENTITY_UNAVAILABLE')
            if not re.search(r'href=["\'](?:https://www.bea.gov)?/news/pio-release-additional-information["\']',html):
                raise FirmLabError('PCE_SEASONAL_IDENTITY_UNAVAILABLE')
            table=cells(tables[0]); values=[]; previous_values=[]
            headers=[r for r in table if r and r[0]=='' and len(r)==3]
            if len(headers)!=1: raise FirmLabError('TABLE_PERIOD_MISMATCH')
            header=headers[0]
            if header[-1].lower()!=d[1].lower(): raise FirmLabError('TABLE_PERIOD_MISMATCH')
            for label,series in [('PCE price index','pce_headline_mom_sa'),('PCE price index excluding food and energy','pce_core_mom_sa')]:
                matches=[r for r in table if r and r[0]==label]
                if len(matches)!=1 or len(matches[0])!=len(header): raise FirmLabError('AMBIGUOUS_PCE_ROW')
                values.append((series,matches[0][-1]))
                previous_values.append((series,matches[0][-2]))
            metadata.update(source_series_ids=['BEA personal income release: PCE price index, monthly percent change',
                         'BEA personal income release: PCE price index excluding food and energy, monthly percent change'],
                            seasonal_adjustment='seasonally adjusted',seasonal_adjustment_basis=PCE_CONVENTIONS,
                            index_base='not applicable: percent change, NOT index level')
        elif kind=='cpi':
            tables=[t for t in re.findall(r'<table\b[^>]*>.*?</table>',html,re.I|re.S)
                    if re.search(r'Table 1\. Consumer Price Index for All Urban Consumers',text(t))]
            if len(tables)!=1 or 'Unadjusted indexes' not in text(tables[0]) or '1982-84=100' not in text(tables[0]):
                raise FirmLabError('CPI_TABLE_IDENTITY_UNAVAILABLE')
            table_period=one(r'U\.S\. city average,\s*'+MONTH+r'\s+(\d{4})',text(tables[0]),'TABLE_PERIOD_MISMATCH')
            if f'{table_period[2]}-{MONTHS[table_period[1].lower()]:02d}'!=period:
                raise FirmLabError('TABLE_PERIOD_MISMATCH')
            headers=' '.join(text(h) for h in re.findall(r'<th\b[^>]*>(.*?)</th>',tables[0],re.I|re.S))
            dates=re.findall(r'\b([A-Za-z]{3,9})\.?\s+(\d{4})\b',headers)
            month_lookup={m[:3]:n for m,n in MONTHS.items()}
            dates=[(int(y),month_lookup[m[:3].lower()]) for m,y in dates if m[:3].lower() in month_lookup]
            year,month=map(int,period.split('-'))
            expected=[(year-1,month),(year if month>1 else year-1,month-1 if month>1 else 12),(year,month)]
            if dates!=expected: raise FirmLabError('TABLE_COLUMN_IDENTITY_UNAVAILABLE')
            table=cells(tables[0]); values=[]
            for label,series in [('All items','cpi_headline_nsa'),('All items less food and energy','cpi_core_nsa')]:
                matches=[r for r in table if r and r[0]==label]
                if len(matches)!=1 or len(matches[0])!=10: raise FirmLabError('AMBIGUOUS_CPI_ROW')
                values.append((series,matches[0][4]))
            metadata.update(source_series_ids=['CUUR0000SA0','CUUR0000SA0L1E'],seasonal_adjustment='not seasonally adjusted',index_base='1982-84=100')
        else:
            one(r'seasonally adjusted',s,'SEASONAL_IDENTITY_UNAVAILABLE')
            payroll=one(r'Total nonfarm payroll employment\s+(increased|rose|declined|decreased|fell)\s+by\s+([\d,]+)',s,'PAYROLL_CHANGE_UNAVAILABLE')
            unemployment=one(r'unemployment rate\s+(?:was\s+)?(?:unchanged\s+at|changed little at|edged (?:up|down) to|rose to|fell to|increased to|decreased to)\s+([\d.]+)\s+percent',s,'UNEMPLOYMENT_UNAVAILABLE')
            change=Decimal(payroll[2].replace(',',''))/1000*(-1 if payroll[1].lower() in ('declined','decreased','fell') else 1)
            values=[('unemployment_rate',unemployment[1]),('nonfarm_payroll_change',str(change))]
            metadata.update(source_series_ids=['LNS14000000','CES0000000001:publisher_reported_monthly_change'],seasonal_adjustment='seasonally adjusted')
    observations=[]; events=[]
    dated_values=[(series,value,period) for series,value in values]
    if kind=='pce' and include_prior:
        year,month=map(int,period.split('-'))
        previous_period=f'{year if month>1 else year-1}-{month-1 if month>1 else 12:02d}'
        if MONTHS.get(header[-2].lower())!=int(previous_period[-2:]): raise FirmLabError('TABLE_PERIOD_MISMATCH')
        dated_values += [(series,value,previous_period) for series,value in previous_values]
        metadata['prior_period_basis']='values for prior period as republished in THIS release; not backdated to the earlier release'
    for series,value,period in dated_values:
        row=dict(series=series,value=value,unit=SERIES[series][0],period=period,source=source,source_url=response.url,
                 source_timestamp=published,published_at=published,ingested_at=response.fetched_at,revision=0,
                 source_hash=hashlib.sha256(response.body).hexdigest())
        validate_observation(row,raw=response.body,now=now)
        observations.append(row)
        event_type={'fed':'fomc_rate_decision','cpi':'cpi_release','pce':'pce_release','labor':'unemployment_release' if series=='unemployment_rate' else 'payrolls_release'}[kind]
        event={k:v for k,v in row.items() if k!='value'}
        event.update(event_id=f'{event_type}:{series}:{period}',event_type=event_type,
                     scheduled_at=None,actual_published_at=published,released_value=value,prior_value=None,revised_prior_value=None,consensus='UNAVAILABLE')
        validate_event(event,raw=response.body,now=now)
        events.append(event)
    bundle={'observations':observations,'events':events,'metadata':metadata}
    validate_links(bundle)
    return bundle


def validate_links(bundle):
    if len(bundle['observations'])!=len(bundle['events']): raise FirmLabError('EVENT_OBSERVATION_MISMATCH')
    for o,e in zip(bundle['observations'],bundle['events']):
        if any(o[k]!=e[k] for k in ('series','period','source','source_url','unit','revision','published_at','source_hash')) or o['value']!=e['released_value'] or e['actual_published_at']!=o['published_at']:
            raise FirmLabError('EVENT_OBSERVATION_MISMATCH')


def treasury_candidates(raw, *, now):
    """Unpublished CMT candidates only. These are NOT admissible MacroStore rows."""
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if not {'Date','2 Yr','10 Yr'} <= set(reader.fieldnames or []):
        raise FirmLabError('TREASURY_SERIES_IDENTITY_UNAVAILABLE')
    rows=[]
    for row in reader:
        period=datetime.strptime(row['Date'],'%m/%d/%Y').date()
        if period>now.date(): raise FirmLabError('FUTURE_OBSERVATION_PERIOD')
        for column,series in [('2 Yr','treasury_2y'),('10 Yr','treasury_10y'),('3 Mo','treasury_3m')]:
            if column not in row: continue
            try: value=Decimal(row[column])
            except (InvalidOperation,TypeError): raise FirmLabError('TREASURY_VALUE_INVALID') from None
            if not value.is_finite() or not -10 <= value <= 100: raise FirmLabError('TREASURY_VALUE_INVALID')
            rows.append(dict(series=series,value=str(value),unit='percent',period=period.isoformat(),
                             source='US Treasury',source_series_id='Daily Treasury Par Yield Curve Rates: '+column,
                             publication_status='UNAVAILABLE'))
    return rows


def parse_treasury(raw):
    # Daily CMT files carry observation dates, not authenticated publication instants.
    raise FirmLabError('EXACT_PUBLICATION_UNAVAILABLE: Treasury daily CMT date is not publication time')


def parse_fred(payload):
    # Neither economic dates nor ALFRED date-only realtime_start establish an exact clock time.
    raise FirmLabError('EXACT_PUBLICATION_UNAVAILABLE: FRED/ALFRED date-only vintage is not publication time')
