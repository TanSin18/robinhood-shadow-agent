"""Read-only reconstruction audit, not a model rerun or fill backtest.

Legacy final records lack input dossiers. Do not replace absent point-in-time
evidence with current quotes or current paper holdings.
"""
import hashlib
import json

from agents.decision_packet import build_critic_packet
from agents.rehearsal import official_read


def replay_recorded_decision(database, cycle_id):
    with official_read(database) as db:
        rows=db.execute("SELECT payload_json FROM run_states WHERE json_extract(payload_json,'$.cycle_id')=? AND json_extract(payload_json,'$.status')='COMPLETED' ORDER BY id DESC LIMIT 1",(cycle_id,)).fetchall()
    if not rows:
        raise ValueError('RECORDED_CYCLE_NOT_FOUND')
    raw=rows[0][0]
    record=json.loads(raw)
    signals=(record.get('strategy_assessment') or {}).get('signals',[])
    lanes={}
    for signal in signals:
        if signal.get('lane') in {'A','B'}:
            lanes.setdefault(signal.get('instrument'),set()).add(signal['lane'])
    critic=record.get('critic')
    rejected=(critic or {}).get('rejected_instruments',[])
    invalid_rejections=not isinstance(rejected,list) or any(not isinstance(value,str) for value in rejected)
    if invalid_rejections:
        rejected=[]
    selections=[]
    for pick in (record.get('decision') or {}).get('picks',[]):
        instrument=pick.get('instrument')
        observed_lanes=lanes.get(instrument,set())
        lane=next(iter(observed_lanes)) if len(observed_lanes)==1 else None
        missing=['historical_quote_snapshot','historical_paper_context']
        if invalid_rejections:
            missing.append('critic.rejected_instruments')
        if lane=='A':
            packet=build_critic_packet(pick,{}, {'lane':lane})
            missing+=packet['missing_evidence']
        elif lane is None:
            missing.append('lane')
        else:
            missing.extend(['historical_contract_snapshot','contract_id_and_terms'])
        veto=instrument in rejected
        selections.append({'instrument':instrument,'lane':lane,
                           'outcome':'CRITIC_VETO' if veto else 'UNKNOWN',
                           'sizing':'NOT_REACHED' if veto else 'UNKNOWN',
                           'missing_evidence':sorted(set(missing))})
    return {'parent_official_run_id':cycle_id,
            'source_record_sha256':hashlib.sha256(raw.encode()).hexdigest(),
            'status':'REPLAY_INCOMPLETE','scope':'recorded_outcome_and_packet_gap_audit_only',
            'selections':selections,'official_writes':0,'model_calls':0,
            'reason':'Final records do not contain full point-in-time input snapshots; no new model or execution outcome is asserted.'}
