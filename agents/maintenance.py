"""Code-only housekeeping. No inference, market fetching, or broker mutation."""
import argparse
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from agents.codex_bridge import ET
from agents.inbox import PAPER_TRACKS, PaperInbox
from agents.operator import nyse_holidays
from config.loader import load_config
from eval.weekly import report_if_due


def next_settlement_day(day):
    day+=timedelta(days=1)
    while day.weekday()>=5 or day in nyse_holidays(day.year)|nyse_holidays(day.year+1):
        day+=timedelta(days=1)
    return day


def run_once(inbox, now, reports, *, notifier=None, authorization_check=None):
    from agents.cycle_lifecycle import CycleLifecycle
    from agents.notification_outbox import deliver_pending
    from agents.notifications import MacOSNotifier
    authorization = authorization_check() if authorization_check is not None else {'status':'NOT_CHECKED'}
    CycleLifecycle(inbox.path, inbox.config.notifications.dashboard_base_url).reconcile(now)
    inbox.expire(now)
    today=now.astimezone(ET).date()
    with inbox.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for lane in ('A','B'):
            # All three paper arms settle T+1 (deterministic_no_ai was previously skipped).
            for track in PAPER_TRACKS:
                if db.execute('SELECT 1 FROM paper_accounts WHERE lane=? AND track=?',(lane,track)).fetchone() is None:
                    continue
                state=inbox.state(lane,track,db)
                remaining=[]
                for settlement in state.get('settlements',[]):
                    if date.fromisoformat(settlement['due'])<=today:
                        amount=Decimal(settlement['amount'])
                        state['settled_cash']=str(Decimal(state['settled_cash'])+amount)
                        state['unsettled_cash']=str(Decimal(state['unsettled_cash'])-amount)
                    else:
                        remaining.append(settlement)
                state['settlements']=remaining
                db.execute('UPDATE paper_accounts SET payload=? WHERE lane=? AND track=?',(json.dumps(state),lane,track))
    report=report_if_due(inbox,now,reports)
    delivery=deliver_pending(inbox.path,notifier,now) if notifier is not None else {'delivery':'deferred'}
    return {'mode':'code_only','timestamp':now.isoformat(),'weekly_report':str(report) if report else None,'real_execution':'blocked','notifications':delivery,'authorization':authorization}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',default='config/settings.local.yaml')
    parser.add_argument('--database',default='data/agent.db')
    parser.add_argument('--reports',default='outputs/weekly')
    args=parser.parse_args()
    from agents.notifications import configured_notifiers
    from broker_proxy.auth_monitor import check_authorization
    config=load_config(args.config)
    now=datetime.now(timezone.utc)
    print(json.dumps(run_once(PaperInbox(args.database,config),now,args.reports,notifier=configured_notifiers(config),
        authorization_check=lambda:check_authorization(args.database,config.broker_proxy_socket,now=now,
            dashboard_base_url=config.notifications.dashboard_base_url))))


if __name__=='__main__':
    main()
