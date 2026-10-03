"""Pure deterministic orchestration. No DB, network, broker or model handles."""
from dataclasses import replace
from pathlib import Path
import hashlib
from .types import timestamp, canonical
from .technical import technical_features
from .structure import structure_features, result_builder
from .fibonacci import fibonacci_features
from .ohlcv import ohlcv_features
from .sector import sector_features
from .fundamental import fundamental_features
from .events import event_features
from .macro import macro_features, intraday_definitions


def calculation_hash():
    digest=hashlib.sha256()
    for file in sorted(Path(__file__).parent.glob('*.py')):
        digest.update(file.name.encode())
        digest.update(b'\0'+file.read_bytes())
    return digest.hexdigest()


def compute(snapshot,request):
    snapshot=dict(snapshot)
    def eligible_bars(bars):
        rows=[r for r in bars if r['session']<=request.as_of_session and
              timestamp(r['known_at'])<=request.knowledge_cutoff and r['ref'].known_at<=request.knowledge_cutoff]
        return sorted(rows,key=lambda r:r['session'])
    for key in ('closes','ohlcv'):
        snapshot[key]=eligible_bars(snapshot.get(key,[]))
    snapshot['reference_closes']={symbol:eligible_bars(bars) for symbol,bars in snapshot.get('reference_closes',{}).items()}
    snapshot.setdefault('missing_reasons',[])
    out=[]
    for fn in (technical_features,structure_features,fibonacci_features,ohlcv_features,
               sector_features,fundamental_features,event_features,macro_features):
        out.extend(fn(snapshot,request))
    make=result_builder({'closes':[]},request,__file__)
    out.extend(make(d['name'],d['family'],None,d['unit'],reason='NO_VALIDATED_INTRADAY_DATA') for d in intraday_definitions())
    digest=calculation_hash()
    result=[]
    for row in out:
        refs=tuple(sorted(set(row.refs),key=lambda r:(r.table,r.row_id,r.content_hash)))
        if row.known_at and row.known_at>request.knowledge_cutoff:
            raise ValueError('RESULT_KNOWN_AFTER_CUTOFF')
        result.append(replace(row,calculation_hash=digest,refs=refs))
    return tuple(sorted(result,key=lambda r:(r.family,r.name,r.feature_version)))
