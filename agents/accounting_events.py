"""Local, sanitized operational evidence. Never performs notification delivery."""
import json
import os
from pathlib import Path
import traceback


def record_failure(path, code, cycle_id, error, now, *, notify=True):
    """Keep a private stack without exception messages, source lines or locals."""
    path=Path(path)
    record={'code':code,'cycle_id':cycle_id,'timestamp':now.isoformat(),
            'error_type':type(error).__name__,
            'stack':[{'file':Path(frame.f_code.co_filename).name,'function':frame.f_code.co_name,'line':line}
                     for frame,line in traceback.walk_tb(error.__traceback__)]}
    outcome={'private_log_written':False,'incident_recorded':False}
    try:
        fd=os.open(path.parent/'private-errors.jsonl',os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as handle:
            os.fchmod(handle.fileno(),0o600)
            handle.write(json.dumps(record)+'\n'); handle.flush(); os.fsync(handle.fileno())
        outcome['private_log_written']=True
    except OSError:
        pass  # Failure remains explicit in the returned evidence, never "logged".
    if notify:
        try:
            from agents.safety_events import record_incident, ensure_operations_schema
            from data.connections import connection
            with connection(path) as db:
                ensure_operations_schema(db)
                prior=db.execute('SELECT id FROM safety_incidents WHERE code=? AND cycle_id=? AND resolved_at IS NULL',(code,cycle_id)).fetchone()
            if not prior:
                record_incident(path,code,cycle_id=cycle_id,now=now)
            outcome['incident_recorded']=True
        except (OSError,RuntimeError,ValueError):
            pass
        except Exception:
            # sqlite failures must not replace the original terminal evidence.
            pass
    return outcome


def enqueue_allocation_warning(path, cycle_id, now):
    from data.connections import connection
    from agents.notification_outbox import enqueue
    with connection(path) as db:
        enqueue(db,'allocation-unavailable:'+cycle_id,'Cost attribution fallback',
                'Token attribution unavailable; a labeled candidate-count split was used. Budget caps remain enforced.',
                now,priority=1)
