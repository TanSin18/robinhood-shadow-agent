"""Factual filing and earnings metadata; filing acceptance is not release time."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
from .calendar import calendar, session_dates
from .inputs import eligible_rows
from .types import timestamp
from .structure import result_builder, definition


def event_definitions():
    rows=[]
    for form in ('10q','10k','8k'):
        rows.append(definition('days_since_'+form,'earnings_events','days','calendar days since accepted filing',0))
        rows.append(definition('latest_filing_is_'+form,'earnings_events','boolean','latest eligible accepted filing form',0))
    for n in (30,90):
        rows.append(definition('filing_count'+str(n),'earnings_events','count','distinct accessions, amendments distinct, accepted in trailing calendar days',0))
    for name,unit in (('sessions_since_earnings','sessions'),('sessions_until_earnings','sessions'),('earnings_timing','state'),('earnings_event_age','days')):
        rows.append(definition(name,'earnings_events',unit,'authoritative factual event timing; no filing-time substitution',0))
    return tuple({**r,'required_inputs':['validated_filing_or_earnings_event'],'cadence':'event'} for r in rows)


def event_features(snapshot,request):
    filings=eligible_rows(snapshot.get('filings',[]),request.knowledge_cutoff)
    filings=[r for r in filings if timestamp(r['accepted_timestamp'])[:10]<=request.as_of_session]
    unique={r['accession_number']:r for r in sorted(filings,key=lambda r:r['known_at'])}
    filings=list(unique.values())
    events=eligible_rows(snapshot.get('earnings',[]),request.knowledge_cutoff)
    make=result_builder({'closes':filings+events},request,__file__)
    today=date.fromisoformat(request.as_of_session)
    age=lambda r:(today-datetime.fromisoformat(timestamp(r['accepted_timestamp'])).astimezone(ZoneInfo('America/New_York')).date()).days
    values={}
    latest=max(filings,key=lambda r:r['accepted_timestamp']) if filings else None
    for code,form in (('10q','10-Q'),('10k','10-K'),('8k','8-K')):
        matching=[r for r in filings if r.get('form_type')==form]
        values['days_since_'+code]=min(map(age,matching)) if matching else None
        values['latest_filing_is_'+code]=latest.get('form_type')==form if latest else None
    for n in (30,90):
        values['filing_count'+str(n)]=sum(0<=age(r)<n for r in filings) if filings else None
    released=[r for r in events if r.get('event_date','9999')<=request.as_of_session]
    if released:
        event=max(released,key=lambda r:r['event_date'])
        values['earnings_event_age']=(today-date.fromisoformat(event['event_date'])).days
        values['sessions_since_earnings']=len([s for s in session_dates(event['event_date'],request.as_of_session) if s>event['event_date']])
        if event.get('release_timestamp'):
            instant=datetime.fromisoformat(timestamp(event['release_timestamp']))
            day=instant.astimezone(ZoneInfo('America/New_York')).date().isoformat()
            cal=calendar()
            if cal.is_session(day):
                values['earnings_timing']={'timing':'BEFORE_OPEN' if instant<cal.session_open(day) else 'AFTER_CLOSE' if instant>=cal.session_close(day) else 'REGULAR_SESSION'}
    scheduled=[r for r in events if r.get('scheduled_timestamp') and r.get('schedule_authoritative') is True
               and timestamp(r['scheduled_timestamp'])[:10]>request.as_of_session]
    if scheduled:
        day=min(timestamp(r['scheduled_timestamp'])[:10] for r in scheduled)
        values['sessions_until_earnings']=len([s for s in session_dates(request.as_of_session,day) if s>request.as_of_session])
    return tuple(make(d['name'],'earnings_events',values.get(d['name']),d['unit'],
        audit={'basis':'FACTUAL_EVENTS_NO_CONSENSUS'},reason='NO_AUTHORITATIVE_EVENT_FIELD') for d in event_definitions())
