"""Two-anchor CLOSE projections; not price targets or recommendations."""
from decimal import Decimal as D
from .technical import precision, sma
from .structure import confirmed_pivots, completed_legs, cluster_levels, result_builder, definition
from .ohlcv import ohlcv_features

RETRACEMENTS=('0.236','0.382','0.5','0.618','0.786')
EXTENSIONS=('1.272','1.618')


def fibonacci_definitions():
    out=[]
    for key in ['retracement_'+r for r in RETRACEMENTS]+['extension_'+r for r in EXTENSIONS]:
        for suffix,unit in (('','price'),('_distance','fraction'),('_atr_distance','ATR'),('_relation','relation'),('_touch_count','count'),('_cross_count','count')):
            out.append(definition('close_fib_'+key+suffix,'fibonacci',unit,
                'directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%',
                optional=('validated_atr14',) if suffix=='_atr_distance' else ()))
    for suffix,unit in (('nearest','level'),('clusters','levels')):
        out.append(definition('close_fib_'+suffix,'fibonacci',unit,'latest3 completed close legs; bounded0.5% clusters; nearest fractional distance'))
    return tuple(out)


@precision
def directed_levels(start,end):
    if start<=0 or end<=0 or start==end:
        raise ValueError('NONZERO_POSITIVE_LEG_REQUIRED')
    delta=end-start
    return {**{'retracement_'+r:end-D(r)*delta for r in RETRACEMENTS},
            **{'extension_'+r:start+D(r)*delta for r in EXTENSIONS}}


@precision
def fibonacci_features(snapshot,request):
    bars=snapshot['closes']
    legs=completed_legs(confirmed_pivots(bars))
    make=result_builder(snapshot,request,__file__)
    levels=directed_levels(D(legs[-1]['start']['value']),D(legs[-1]['end']['value'])) if legs else {}
    audit={k:({x:y for x,y in v.items() if x!='refs'} if isinstance(v,dict) else v) for k,v in legs[-1].items()} if legs else {}
    current=D(bars[-1]['value']) if bars else None
    ohlc=snapshot.get('ohlcv',[])
    atr_value=None
    # Close-anchor identity is unchanged. ATR is a separate optional input and
    # must describe the same completed sessions and price basis.
    if bars and ohlc and [b['session'] for b in ohlc]==[b['session'] for b in bars] and all(
            D(a['close'])==D(b['value']) and a.get('price_basis')==b.get('price_basis') for a,b in zip(ohlc,bars)):
        atr_row=next(r for r in ohlcv_features({**snapshot,'ohlcv':ohlc},request) if r.name=='atr14')
        atr_value=D(atr_row.value) if atr_row.value is not None and D(atr_row.value)>0 else None
    make_atr=result_builder({**snapshot,'closes':bars+ohlc},request,__file__)
    out=[]
    for key in ['retracement_'+r for r in RETRACEMENTS]+['extension_'+r for r in EXTENSIONS]:
        value=levels.get(key)
        reason='NO_CONFIRMED_CLOSE_LEG'
        if value is not None and value<=0:
            value=None
            reason='NONPOSITIVE_PROJECTED_LEVEL'
        detail={**audit,'ratio':key.split('_')[1],'projection_type':key.split('_')[0],
                'computed_level':str(value) if value is not None else None}
        out.append(make('close_fib_'+key,'fibonacci',value,audit=detail,reason=reason))
        distance=(current-value)/value if value is not None and value>0 else None
        out.append(make('close_fib_'+key+'_distance','fibonacci',distance,'fraction',detail))
        out.append(make_atr('close_fib_'+key+'_atr_distance','fibonacci',
            (current-value)/atr_value if value is not None and atr_value is not None else None,
            'ATR',detail,'NO_VALIDATED_ATR' if atr_value is None else reason))
        relation={'relation':'ABOVE' if current>value else 'BELOW' if current<value else 'EQUAL'} if value is not None else None
        out.append(make('close_fib_'+key+'_relation','fibonacci',relation,'relation',detail))
        touching=False
        touches=crosses=0
        previous=None
        if value is not None and value>0:
            for bar in bars:
                if bar['session']<legs[-1]['end']['confirmed_session'] or bar['known_at']<max(legs[-1]['start']['known_at'],legs[-1]['end']['known_at']):
                    continue
                price=D(bar['value'])
                inside=abs(price/value-1)<=D('.005')
                touches+=int(inside and not touching)
                crosses+=int(previous is not None and (price-value)*(previous-value)<0)
                touching=inside
                previous=price
        out.append(make('close_fib_'+key+'_touch_count','fibonacci',D(touches) if value is not None else None,'count',detail))
        out.append(make('close_fib_'+key+'_cross_count','fibonacci',D(crosses) if value is not None else None,'count',detail))
    nearest=min((k for k,v in levels.items() if v>0),key=lambda k:(abs(current/levels[k]-1),D(k.split('_')[1]),k)) if levels else None
    out.append(make('close_fib_nearest','fibonacci',{'name':nearest,'level':str(levels[nearest])} if nearest else None,'level',audit))
    all_levels=[]
    members=[]
    for leg in legs[-3:]:
        for key,value in directed_levels(D(leg['start']['value']),D(leg['end']['value'])).items():
            if value>0:
                all_levels.append(value)
                members.append({'leg_id':leg['id'],'projection':key,'level':str(value)})
    groups=cluster_levels(all_levels)
    closes=[D(b['value']) for b in bars]
    averages={f'SMA{n}':sma(closes,n) for n in (20,50,100,200)}
    pivots=confirmed_pivots(bars)
    structure=[sum(g)/len(g) for g in cluster_levels([D(p['value']) for p in pivots if p['session'] in {b['session'] for b in bars[-252:]}])]
    clusters=[]
    for g in groups:
        mean=sum(g)/len(g)
        clusters.append({'level':str(mean),'density':len(g),'levels':[str(v) for v in g],
            'members':[m for m in members if D(m['level']) in g],
            'sma_overlaps':[name for name,v in averages.items() if v is not None and abs(v/mean-1)<=D('.005')],
            'structure_overlaps':[str(v) for v in structure if abs(v/mean-1)<=D('.005')]})
    nearest_cluster=min(clusters,key=lambda c:abs(current/D(c['level'])-1)) if clusters else None
    out.append(make('close_fib_clusters','fibonacci',{'clusters':clusters,'leg_ids':[l['id'] for l in legs[-3:]],'tolerance':'0.005',
        'nearest_cluster_distance':str(current/D(nearest_cluster['level'])-1) if nearest_cluster else None} if legs else None,'levels',audit))
    return tuple(out)
