"""Hydrate content-addressed immutable input sets, including legacy inline rows."""
import json
from .types import content_hash,canonical,from_payload,valid_hash


def read_result(db,payload):
    data=json.loads(payload)
    if 'input_set_id' in data:
        key=data.pop('input_set_id')
        valid_hash(key)
        if data.get('refs') is not None:
            raise ValueError('CONFLICTING_INLINE_INPUTS')
        row=db.execute('SELECT payload FROM research_feature_inputs WHERE id=?',(key,)).fetchone()
        if row is None:
            raise ValueError('MISSING_INPUT_SET')
        inputs=json.loads(row[0])
        if content_hash(inputs)!=key:
            raise ValueError('INPUT_SET_HASH_MISMATCH')
        data['refs']=inputs['refs']
    return from_payload(canonical(data))
