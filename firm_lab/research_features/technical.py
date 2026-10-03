"""Close-only descriptive mathematics, never a trading rule."""
from decimal import Decimal as D, localcontext, ROUND_HALF_EVEN
from functools import wraps
from pathlib import Path
import hashlib
from .types import FeatureResult


def precision(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with localcontext() as ctx:
            ctx.prec, ctx.rounding = 34, ROUND_HALF_EVEN
            return fn(*args, **kwargs)
    return wrapped


def prices(values):
    values = [D(v) for v in values]
    if any(not v.is_finite() or v <= 0 for v in values):
        raise ValueError('INVALID_CLOSE')
    return values


@precision
def sma(values, n):
    values = prices(values)
    return sum(values[-n:]) / D(n) if n > 0 and len(values) >= n else None


@precision
def simple_return(values, n):
    values = prices(values)
    return values[-1] / values[-n-1] - 1 if n > 0 and len(values) > n else None


@precision
def rsi_wilder(values, n=14):
    values = prices(values)
    if n <= 0 or len(values) <= n:
        return None
    differences = [b-a for a,b in zip(values, values[1:])]
    gain = sum(max(d, D(0)) for d in differences[:n]) / n
    loss = sum(max(-d, D(0)) for d in differences[:n]) / n
    for d in differences[n:]:
        gain = (gain*(n-1) + max(d, D(0))) / n
        loss = (loss*(n-1) + max(-d, D(0))) / n
    if loss == 0:
        return D(100) if gain else D(50)
    return D(100) - D(100) / (1 + gain/loss)


@precision
def ema_series(values, n):
    if n <= 0 or len(values) < n:
        return []
    out = [sum(values[:n]) / n]
    alpha = D(2) / (n+1)
    for v in values[n:]:
        out.append(out[-1] + alpha*(v-out[-1]))
    return out


def ema(values, n):
    series = ema_series(prices(values), n)
    return series[-1] if series else None


@precision
def realized_vol(values, n):
    values = prices(values)
    if n < 2 or len(values) <= n:
        return None
    window = values[-n-1:]
    returns = [(b/a).ln() for a,b in zip(window, window[1:])]
    mean = sum(returns)/n
    return (sum((v-mean)**2 for v in returns)/(n-1)*252).sqrt()


@precision
def percentile(values, n=252):
    if len(values) < n or any(v is None for v in values[-n:]):
        return None
    sample = values[-n:]
    current = sample[-1]
    return D(100)*(sum(v < current for v in sample) + D('.5')*sum(v == current for v in sample))/n


def technical_definitions():
    rows = []
    def add(name, family, unit, lookback, formula, value_type='decimal'):
        rows.append(dict(name=name, family=family, unit=unit, lookback=lookback,
            formula=formula, version=name+'_v1', value_type=value_type,
            required_inputs=['close'], optional_inputs=[], cadence='daily',
            point_in_time='contiguous completed sessions; all inputs known by cutoff',
            missing_behavior='null with exact missing reason'))
    for n in (20,50,100,200):
        for suffix, unit, extra, formula in (
            ('', 'price', 0, f'mean(last {n} closes)'),
            ('_ratio', 'fraction', 0, f'C/SMA{n}'),
            ('_distance', 'fraction', 0, f'C/SMA{n}-1'),
            ('_slope5', 'fraction', 5, f'SMA{n}(t)/SMA{n}(t-5)-1')):
            add(f'sma{n}{suffix}', 'trend', unit, n+extra, formula)
    add('sma_ordering', 'trend', 'ordering', 200, 'descending labels with equal groups', 'object')
    for n in (5,10,20,63,126,252):
        add(f'return{n}', 'momentum', 'fraction', n+1, f'C(t)/C(t-{n})-1')
    add('momentum_acceleration20', 'momentum', 'fraction', 41, 'return20(t)-return20(t-20)')
    add('return20_percentile252', 'momentum', 'percentile', 272, 'inclusive 252; midrank ties')
    add('rsi14_wilder', 'momentum', 'index_0_100', 15, 'Wilder14; flat=50; recursive from first14 differences')
    for name, n in (('ema12',12),('ema26',26),('macd_line',26),('macd_smoothing9',34),('macd_histogram',34),('macd_price_normalized',26)):
        add(name,'momentum','fraction' if name.endswith('normalized') else 'price',n,
            'EMA SMA seed; alpha2/(n+1); MACD12-26; smoothing9; histogram difference; normalization/C')
    for n in (20,63):
        add(f'realized_vol{n}', 'volatility', 'annualized_fraction', n+1, f'sample sd({n} log returns)*sqrt252')
    add('realized_vol20_percentile252', 'volatility', 'percentile', 272, 'inclusive252; midrank ties')
    return tuple(rows)


@precision
def technical_features(snapshot, request):
    bars = snapshot['closes']
    values = prices([b['value'] for b in bars])
    computed = {}
    for n in (20,50,100,200):
        m = sma(values,n)
        prior = sma(values[:-5], n)
        computed.update({f'sma{n}':m, f'sma{n}_ratio':values[-1]/m if m is not None else None,
            f'sma{n}_distance':values[-1]/m-1 if m is not None else None,
            f'sma{n}_slope5':m/prior-1 if m is not None and prior is not None else None})
    if computed['sma200'] is not None:
        levels = [('C', values[-1])] + [(f'SMA{n}', computed[f'sma{n}']) for n in (20,50,100,200)]
        groups = []
        for v in sorted(set(v for _,v in levels), reverse=True):
            groups.append([name for name,x in levels if x==v])
        computed['sma_ordering'] = {'groups': groups}
    for n in (5,10,20,63,126,252):
        computed[f'return{n}'] = simple_return(values,n)
    computed['momentum_acceleration20'] = simple_return(values,20)-simple_return(values[:-20],20) if len(values)>40 else None
    computed['rsi14_wilder'] = rsi_wilder(values)
    a,b = ema_series(values,12), ema_series(values,26)
    computed['ema12'],computed['ema26'] = (a[-1] if a else None),(b[-1] if b else None)
    macd = [x-y for x,y in zip(a[14:],b)]
    smoothing = ema_series(macd,9)
    computed['macd_line'] = macd[-1] if macd else None
    computed['macd_smoothing9'] = smoothing[-1] if smoothing else None
    computed['macd_histogram'] = macd[-1]-smoothing[-1] if smoothing else None
    computed['macd_price_normalized'] = macd[-1]/values[-1] if macd else None
    for n in (20,63):
        computed[f'realized_vol{n}'] = realized_vol(values,n)
    for name,fn in (('return20',simple_return),('realized_vol20',realized_vol)):
        computed[name+'_percentile252'] = percentile([fn(values[:i],20) for i in range(max(21,len(values)-251),len(values)+1)])
    code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    refs = tuple(b['ref'] for b in bars)
    out=[]
    for definition in technical_definitions():
        value=computed.get(definition['name'])
        reason = None if value is not None else (snapshot['missing_reasons'][0] if snapshot['missing_reasons'] else 'INSUFFICIENT_HISTORY')
        out.append(FeatureResult(request.instrument,definition['family'],definition['name'],
            value if isinstance(value,dict) or value is None else str(value),definition['unit'],
            request.as_of_session,max(b['known_at'] for b in bars) if value is not None else None,
            'AVAILABLE' if value is not None else 'UNAVAILABLE',reason,refs,
            definition['version'],code_hash,{'knowledge_cutoff':request.knowledge_cutoff,
                'price_basis':'provider_reported_close','formula':definition['formula']}))
    return tuple(out)
