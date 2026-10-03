"""OHLCV calculations; no close-only reconstruction, network or feed activation."""
from decimal import Decimal as D
from .technical import precision, percentile
from .structure import result_builder, definition


@precision
def geometry(o,h,l,c,prior_close=None,prior_high=None,prior_low=None):
    if any(not x.is_finite() or x<=0 for x in (o,h,l,c)) or not l<=min(o,c)<=max(o,c)<=h:
        raise ValueError('INVALID_OHLC')
    body,span,upper,lower=abs(c-o),h-l,h-max(o,c),min(o,c)-l
    out=dict(body=body,range=span,upper_wick=upper,lower_wick=lower,
        body_fraction=body/span if span else None,upper_wick_fraction=upper/span if span else None,
        lower_wick_fraction=lower/span if span else None,clv=(2*c-h-l)/span if span else None,
        open_close_return=c/o-1)
    for name,value in (('gap_close',prior_close),('gap_high',prior_high),('gap_low',prior_low)):
        out[name]=o/value-1 if value is not None and value>0 else None
    return out


def true_range(h,l,prior_close):
    if any(not x.is_finite() or x<=0 for x in (h,l,prior_close)) or h<l:
        raise ValueError('INVALID_RANGE')
    return max(h-l,abs(h-prior_close),abs(l-prior_close))


@precision
def atr(ranges,n=14):
    if any(not v.is_finite() or v<0 for v in ranges):
        raise ValueError('INVALID_RANGE')
    if len(ranges)<n:
        return None
    value=sum(ranges[:n])/n
    for v in ranges[n:]:
        value=(value*(n-1)+v)/n
    return value


@precision
def volume_metrics(volumes):
    if any(not v.is_finite() or v<0 for v in volumes):
        raise ValueError('INVALID_VOLUME')
    out={'volume':volumes[-1] if volumes else None}
    for n in (20,63):
        out[f'volume_mean{n}']=sum(volumes[-n-1:-1])/n if len(volumes)>n else None
    mean=out['volume_mean20']
    out['rvol20']=volumes[-1]/mean if mean is not None and mean>0 else None
    out['volume_change']=volumes[-1]/volumes[-2]-1 if len(volumes)>1 and volumes[-2]>0 else None
    out['volume_percentile252']=percentile(volumes)
    return out


def ohlcv_definitions():
    out=[]
    for name in ('body','range','upper_wick','lower_wick','body_fraction','upper_wick_fraction',
                 'lower_wick_fraction','clv','open_close_return','gap_close','gap_high','gap_low'):
        unit='price' if name in ('body','range','upper_wick','lower_wick') else 'fraction'
        out.append(definition(name,'candlestick_geometry',unit,'validated OHLC raw geometry; zero range ratios null',2))
    for name,unit,n in (('true_range','price',2),('atr14','price',15),('atr_price','fraction',15)):
        out.append(definition(name,'volatility',unit,'TR=max(H-L,abs(H-priorC),abs(L-priorC)); Wilder14 ATR',n))
    for name,unit,n in (('volume','shares',1),('volume_mean20','shares',21),('volume_mean63','shares',64),
        ('rvol20','ratio',21),('volume_change','fraction',2),('volume_percentile252','percentile',252),
        ('return_rvol','interaction',21),('signed_return_volume_percentile','interaction',252),
        ('range_expansion_rvol','interaction',21),('breakout_distance_rvol','interaction',21)):
        out.append(definition(name,'volume',unit,'prior20/63 means; inclusive252 midrank; ratios/limited products',n))
    return tuple({**r,'required_inputs':['validated_daily_ohlcv'],
        'point_in_time':'validated completed OHLCV sessions; all input knowledge before cutoff'} for r in out)


@precision
def ohlcv_features(snapshot,request):
    bars=snapshot['ohlcv']
    make=result_builder({**snapshot,'closes':bars},request,__file__)
    values={}
    if bars:
        data=[{k:D(b[k]) for k in ('open','high','low','close','volume')} for b in bars]
        for b in data:
            geometry(b['open'],b['high'],b['low'],b['close'])
        current=data[-1]
        previous=data[-2] if len(data)>1 else {}
        values.update(geometry(current['open'],current['high'],current['low'],current['close'],
            previous.get('close'),previous.get('high'),previous.get('low')))
        tr=[true_range(b['high'],b['low'],a['close']) for a,b in zip(data,data[1:])]
        values['true_range']=tr[-1] if tr else None
        values['atr14']=atr(tr)
        values['atr_price']=values['atr14']/current['close'] if values['atr14'] is not None else None
        values.update(volume_metrics([b['volume'] for b in data]))
        ret=current['close']/previous['close']-1 if previous else None
        rvol=values['rvol20']
        vp=values['volume_percentile252']
        values['return_rvol']=ret*rvol if ret is not None and rvol is not None else None
        values['signed_return_volume_percentile']=D((ret>0)-(ret<0))*vp if ret is not None and vp is not None else None
        mean_range=sum(b['high']-b['low'] for b in data[-21:-1])/20 if len(data)>20 else None
        values['range_expansion_rvol']=values['range']/mean_range*rvol if mean_range and rvol is not None else None
        values['breakout_distance_rvol']=(current['close']/max(b['close'] for b in data[-21:-1])-1)*rvol if len(data)>20 and rvol is not None else None
    return tuple(make(d['name'],d['family'],values.get(d['name']),d['unit'],
        audit={'basis':'VALIDATED_OHLCV','formula':d['formula']},
        reason='NO_VALIDATED_OHLCV' if not bars else 'INSUFFICIENT_HISTORY_OR_UNDEFINED_DENOMINATOR') for d in ohlcv_definitions())
