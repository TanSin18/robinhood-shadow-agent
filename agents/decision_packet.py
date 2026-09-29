"""Pure, blind Critic dossier construction. No broker, model, or database access.

Development primitive: callers supply recorded evidence, never reconstructed
historical balances. Absence is explicit; this is not an execution permission.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation


def _number(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('INVALID_PACKET_NUMBER')
    try:
        result=Decimal(str(value))
    except InvalidOperation:
        raise ValueError('INVALID_PACKET_NUMBER') from None
    if not result.is_finite() or result < 0:
        raise ValueError('INVALID_PACKET_NUMBER')
    return str(result)


def _text_fields(source, fields):
    return {key:source[key] for key in fields if isinstance(source.get(key),str) and source[key].strip()}


def build_critic_packet(selection: dict, evidence: dict, paper_context: dict) -> dict:
    instrument=selection.get('instrument')
    lane=paper_context.get('lane')
    asset=evidence.get('asset_class')
    contract=evidence.get('contract')
    if asset is not None and (not isinstance(asset,str) or asset not in {'stock','etf','option'}):
        raise ValueError('INVALID_ASSET_CLASS')
    if not isinstance(instrument,str) or not instrument or lane not in {'A','B'}:
        raise ValueError('LANE_OR_CONTRACT_MISMATCH')
    option=asset=='option' or contract is not None
    if ((option and (lane!='B' or not isinstance(contract,dict)
                     or contract.get('id')!=instrument
                     or not isinstance(contract.get('chain_symbol'),str)
                     or not contract['chain_symbol'].strip()))
            or (not option and lane=='B')):
        raise ValueError('LANE_OR_CONTRACT_MISMATCH')
    if asset in {'stock','etf'} and option:
        raise ValueError('LANE_OR_CONTRACT_MISMATCH')
    chosen=_text_fields(selection,('instrument','side','thesis','good_if','invalidation'))
    observed=_text_fields(evidence,('asset_class','quote_time','underlying'))
    observed.update({key:_number(evidence.get(key)) for key in ('bid','ask','realized_vol_20d')})
    if observed.get('quote_time'):
        stamp=datetime.fromisoformat(observed['quote_time'])
        if stamp.tzinfo is None:
            raise ValueError('TIMEZONE_REQUIRED')
    refs=evidence.get('source_ids',[])
    if not isinstance(refs,list) or any(not isinstance(ref,str) or not ref.strip() for ref in refs):
        raise ValueError('INVALID_SOURCE_REFERENCES')
    observed['source_ids']=list(refs)
    if option:
        observed['contract']=_text_fields(contract,('id','chain_symbol','type','expiration_date'))
        observed['contract'].update({key:_number(contract.get(key)) for key in ('strike_price','trade_value_multiplier')})
    fractional=paper_context.get('fractional_allowed')
    if fractional is not None and type(fractional) is not bool:
        raise ValueError('INVALID_FRACTIONAL_POLICY')
    if option and fractional is True:
        raise ValueError('INVALID_FRACTIONAL_POLICY')
    context={'lane':lane,'fractional_allowed':False if option else fractional,
             **{key:_number(paper_context.get(key)) for key in
                ('settled_cash','unsettled_cash','held_quantity','pending_quantity')}}
    missing=[key for key in ('bid','ask','quote_time') if observed.get(key) is None]
    missing += [key for key in ('settled_cash','held_quantity','pending_quantity','fractional_allowed')
                if context.get(key) is None]
    if not refs:
        missing.append('source_ids')
    if asset is None:
        missing.append('asset_class')
    if option:
        missing += ['contract.'+key for key in ('type','expiration_date','strike_price','trade_value_multiplier')
                    if observed['contract'].get(key) is None]
    return {'selection':chosen,'evidence':observed,'paper_context':context,
            'preliminary_sizing':{'status':'NOT_COMPUTED','executable':False},
            'missing_evidence':missing}
