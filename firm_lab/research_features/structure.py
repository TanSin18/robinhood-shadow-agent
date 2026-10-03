"""Confirmed CLOSE structure. No OHLC extrema or predictive interpretation."""
from decimal import Decimal as D
from dataclasses import asdict
from pathlib import Path
import hashlib
from .technical import precision, prices
from .types import FeatureResult, content_hash, timestamp

PIVOT_VERSION = 'close_fractal_3x3_v1'


def confirmed_pivots(closes):
    bars = sorted(closes, key=lambda b: b['session'])
    if len({b['session'] for b in bars}) != len(bars):
        raise ValueError('DUPLICATE_SESSION')
    values=prices([b['value'] for b in bars])
    out=[]
    for i in range(3,len(bars)-3):
        neighbors=values[i-3:i]+values[i+1:i+4]
        kind='HIGH' if all(values[i]>v for v in neighbors) else 'LOW' if all(values[i]<v for v in neighbors) else None
        if kind:
            refs=tuple(b['ref'] for b in bars[i-3:i+4])
            p=dict(type=kind,value=str(values[i]),session=bars[i]['session'],
                confirmed_session=bars[i+3]['session'],known_at=max(b['known_at'] for b in bars[i-3:i+4]),
                version=PIVOT_VERSION,refs=refs)
            p['id']=content_hash({**p,'refs':[asdict(r) for r in refs]})
            out.append(p)
    return tuple(out)


def completed_legs(pivots):
    pending=None
    out=[]
    for p in pivots:
        if pending is None:
            pending=p
        elif p['type']==pending['type']:
            if ((p['type']=='HIGH' and D(p['value'])>D(pending['value'])) or
                (p['type']=='LOW' and D(p['value'])<D(pending['value']))):
                pending=p
        else:
            if p['value'] != pending['value']:
                out.append(dict(id=content_hash([pending['id'],p['id']]),start=pending,end=p,
                    direction='UP' if D(p['value'])>D(pending['value']) else 'DOWN'))
            pending=p
    return tuple(out)


@precision
def cluster_levels(levels):
    out=[]
    for value in sorted(levels):
        if not out or (value-out[-1][0])/out[-1][0]>D('.005'):
            out.append([value])
        else:
            out[-1].append(value)
    return tuple(tuple(g) for g in out)


@precision
def break_retest(values,level,direction):
    if level<=0 or direction not in ('up','down'):
        raise ValueError('INVALID_LEVEL_OR_DIRECTION')
    crosses=[i for i in range(1,len(values)) if
        (values[i-1]<level<values[i] if direction=='up' else values[i-1]>level>values[i])]
    if not crosses:
        return {'broken':False,'age':None,'retest':False}
    age=len(values)-1-crosses[-1]
    on_side=values[-1]>=level if direction=='up' else values[-1]<=level
    return {'broken':True,'age':age,'retest':0<age<=5 and on_side and abs(values[-1]/level-1)<=D('.005')}


def definition(name,family,unit,formula,lookback=7,optional=()):
    return dict(name=name,family=family,unit=unit,lookback=lookback,formula=formula,
        version=name+'_v1',value_type='object' if unit in ('state','levels','level','relation') else 'boolean' if unit=='boolean' else 'decimal',
        required_inputs=['close'],optional_inputs=list(optional),cadence='daily',
        point_in_time='close-only; 3x3 pivots available after confirmation and source knowledge',
        missing_behavior='null with explicit missing dependency')


def structure_definitions():
    out=[]
    for side in ('support','resistance'):
        for suffix,unit in (('level','price'),('distance','fraction'),('pivot_count','count'),('touch_count','count'),('age','sessions')):
            out.append(definition(f'close_{side}_{suffix}','support_resistance',unit,
                'trailing252 confirmed close pivots; bounded0.5% clusters; mean level; strict nearest side'))
        out.append(definition(f'close_prior_{side}_break_retest','support_resistance','state',
            'prior-session frozen confirmed level; strict cross; return within0.5% from crossed side within5sessions'))
    out.append(definition('close_level_equality','support_resistance','state','current close equals confirmed cluster mean; equality is neither above nor below',252))
    for n in (20,50,252):
        for side in ('high','low'):
            for name,unit in ((f'close_distance_{side}{n}','fraction'),(f'close_new_{side}{n}','boolean'),
                              (f'close_breakout_{side}{n}_age','sessions'),(f'close_breakout_{side}{n}_retest','boolean')):
                out.append(definition(name,'breakout_structure',unit,
                    f'prior{n} closes excluding current; strict cross, frozen breakout level, five-session retest',n+1))
    return tuple(out)


def result_builder(snapshot,request,module):
    bars=snapshot['closes']
    refs=tuple(b['ref'] for b in bars)
    # Include common helper dependencies, not only the calling module.
    digest=hashlib.sha256(b''.join(Path(p).read_bytes() for p in sorted({module,__file__,
        str(Path(__file__).with_name('technical.py')),str(Path(__file__).with_name('types.py'))}))).hexdigest()
    def make(name,family,value,unit='price',audit=None,reason=None):
        available=value is not None
        return FeatureResult(request.instrument,family,name,
            value if isinstance(value,(bool,dict)) or value is None else str(value),unit,
            request.as_of_session,max(timestamp(b[k]) for b in bars for k in
                ('known_at','accepted_timestamp','published_at') if b.get(k)) if available else None,
            'AVAILABLE' if available else 'UNAVAILABLE',None if available else reason or 'INSUFFICIENT_HISTORY',
            refs,name+'_v1',digest,{'knowledge_cutoff':request.knowledge_cutoff,
                'basis':'CLOSE_ONLY',**(audit or {})})
    return make


@precision
def structure_features(snapshot,request):
    bars=snapshot['closes']
    values=prices([b['value'] for b in bars])
    make=result_builder(snapshot,request,__file__)
    out=[]
    pivots=confirmed_pivots(bars)
    recent=[p for p in pivots if p['session'] in {b['session'] for b in bars[-252:]}]
    clusters=cluster_levels([D(p['value']) for p in recent])
    means=[sum(g)/len(g) for g in clusters]
    out.append(make('close_level_equality','support_resistance',
        {'levels':[str(m) for m in means if m==values[-1]]} if values and means else None,'state',reason='NO_CONFIRMED_LEVEL'))
    for side in ('support','resistance'):
        candidates=[m for m in means if (m<values[-1] if side=='support' else m>values[-1])] if values else []
        level=(max(candidates) if side=='support' else min(candidates)) if candidates else None
        members=[] if level is None else [p for p in recent if D(p['value']) in clusters[means.index(level)]]
        audit={'pivots':[{k:v for k,v in p.items() if k!='refs'} for p in members]}
        out.append(make('close_'+side+'_level','support_resistance',level,audit=audit,reason='NO_CONFIRMED_LEVEL'))
        out.append(make('close_'+side+'_distance','support_resistance',values[-1]/level-1 if level else None,'fraction',audit))
        out.append(make('close_'+side+'_pivot_count','support_resistance',D(len(members)) if members else None,'count',audit))
        touches=None
        if members:
            confirmed=max(p['confirmed_session'] for p in members)
            inside=False
            touches=0
            for bar in bars:
                if bar['session']<confirmed:
                    continue
                near=abs(D(bar['value'])/level-1)<=D('.005')
                touches+=int(near and not inside)
                inside=near
        out.append(make('close_'+side+'_touch_count','support_resistance',touches,'count',
                        {**audit,'touch_definition':'distinct entries within0.5% after cluster confirmation'}))
        age=next((len(bars)-1-i for i,b in enumerate(bars) if members and b['session']==max(p['session'] for p in members)),None)
        out.append(make('close_'+side+'_age','support_resistance',age,'sessions',audit))
        # Prior level is reconstructed without the current bar; use that frozen
        # level only after its latest constituent pivot was confirmable.
        state=None
        for i in range(1,len(bars)):
            eligible=[p for p in pivots if p['confirmed_session']<=bars[i-1]['session'] and
                      p['session']>=bars[max(0,i-252)]['session'] and p['known_at']<=request.knowledge_cutoff]
            prior_means=[sum(g)/len(g) for g in cluster_levels([D(p['value']) for p in eligible])]
            candidates=[m for m in prior_means if (m<values[i-1] if side=='support' else m>values[i-1])]
            frozen=(max(candidates) if side=='support' else min(candidates)) if candidates else None
            if frozen is not None and (values[i]<frozen if side=='support' else values[i]>frozen):
                state={'broken':True,'age':len(values)-1-i,'retest':False,'level':str(frozen)}
        if state:
            frozen=D(state['level'])
            on_side=values[-1]<=frozen if side=='support' else values[-1]>=frozen
            state['retest']=0<state['age']<=5 and on_side and abs(values[-1]/frozen-1)<=D('.005')
        out.append(make(f'close_prior_{side}_break_retest','support_resistance',state,'state',reason='NO_PRIOR_LEVEL_BREAK'))
    for n in (20,50,252):
        for side,fn in (('high',max),('low',min)):
            level=fn(values[-n-1:-1]) if len(values)>n else None
            distance=values[-1]/level-1 if level else None
            flag=(distance>0 if side=='high' else distance<0) if distance is not None else None
            out.append(make(f'close_distance_{side}{n}','breakout_structure',distance,'fraction'))
            out.append(make(f'close_new_{side}{n}','breakout_structure',flag,'boolean'))
            crossings=[i for i in range(n,len(values)) if (values[i]>max(values[i-n:i]) if side=='high' else values[i]<min(values[i-n:i]))]
            age=len(values)-1-crossings[-1] if crossings else None
            retest=None
            if crossings:
                i=crossings[-1]
                frozen=fn(values[i-n:i])
                on_side=values[-1]>=frozen if side=='high' else values[-1]<=frozen
                retest=0<age<=5 and on_side and abs(values[-1]/frozen-1)<=D('.005')
            out.append(make(f'close_breakout_{side}{n}_age','breakout_structure',age,'sessions',reason='NO_PRIOR_BREAKOUT'))
            out.append(make(f'close_breakout_{side}{n}_retest','breakout_structure',retest,'boolean',reason='NO_PRIOR_BREAKOUT'))
    return tuple(out)
