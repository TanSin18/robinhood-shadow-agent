"""At-least-once OS notifications. Notification retries never retry trades."""
from datetime import timedelta
import sqlite3
from agents.safety_events import ensure_operations_schema
from data.connections import connection

CHANNELS = ('macos', 'pushover')


def enqueue(db,event_id,title,body,now,*,priority=0,url=None,channels=CHANNELS):
    if priority not in {-2, -1, 0, 1}:
        raise ValueError('Notification priority must be between -2 and 1.')
    if any(channel not in CHANNELS for channel in channels):
        raise ValueError('Unknown notification channel.')
    ensure_operations_schema(db)
    db.execute('INSERT OR IGNORE INTO notification_outbox(event_id,title,body,created_at) VALUES (?,?,?,?)',(event_id,title,body,now.isoformat()))
    for channel in channels:
        db.execute('''INSERT OR IGNORE INTO notification_deliveries
          (event_id,channel,priority,url) VALUES (?,?,?,?)''',
                   (event_id,channel,priority,url))

def deliver_pending(path,notifier,now):
    notifiers = notifier if isinstance(notifier, dict) else {'macos': notifier}
    result = {'channels': {channel: {'delivered': 0, 'failed': 0, 'disabled': 0}
                           for channel in CHANNELS}}
    with connection(path,timeout=5) as db:
        db.execute('BEGIN IMMEDIATE'); ensure_operations_schema(db)
        for channel in CHANNELS:
            if channel in notifiers:
                db.execute("UPDATE notification_deliveries SET status='PENDING' WHERE channel=? AND status='NOT_CONFIGURED'",(channel,))
            else:
                changed=db.execute("UPDATE notification_deliveries SET status='NOT_CONFIGURED' WHERE channel=? AND status IN ('PENDING','SENDING')",(channel,)).rowcount
                result['channels'][channel]['disabled'] += changed
    for channel, channel_notifier in notifiers.items():
        for _ in range(20):
            with connection(path,timeout=5) as db:
                db.execute('BEGIN IMMEDIATE'); ensure_operations_schema(db)
                # A crash after remote submission may duplicate a notification, never a trade.
                db.execute("UPDATE notification_deliveries SET status='PENDING' WHERE channel=? AND status='SENDING' AND next_attempt_at<=?",(channel,now.isoformat()))
                db.execute("UPDATE notification_deliveries SET status='UNKNOWN' WHERE channel=? AND status='PENDING' AND attempts>=3",(channel,))
                row=db.execute('''SELECT d.event_id,o.title,o.body,d.priority,d.url,d.attempts
                  FROM notification_deliveries d JOIN notification_outbox o USING(event_id)
                  WHERE d.channel=? AND d.status='PENDING' AND d.attempts<3
                    AND (d.next_attempt_at IS NULL OR d.next_attempt_at<=?)
                  ORDER BY o.created_at LIMIT 1''',(channel,now.isoformat())).fetchone()
                if row is None: break
                key,title,body,priority,url,attempts=row
                next_attempt=(now+timedelta(seconds=60 if attempts==0 else 300)).isoformat()
                db.execute("UPDATE notification_deliveries SET status='SENDING',attempts=attempts+1,next_attempt_at=? WHERE event_id=? AND channel=?",(next_attempt,key,channel))
            error=None; receipt={}
            try:
                if channel == 'pushover':
                    receipt = channel_notifier.notify(title,body,priority=priority,url=url) or {}
                else:
                    channel_notifier.notify(title,body)
            except Exception as exc:
                error=type(exc).__name__
            with connection(path,timeout=5) as db:
                if error:
                    status='EXHAUSTED' if attempts+1>=3 else 'PENDING'
                    db.execute('''UPDATE notification_deliveries SET status=?,error_class=?
                      WHERE event_id=? AND channel=? AND attempts=?''',(status,error,key,channel,attempts+1))
                    result['channels'][channel]['failed']+=1
                else:
                    db.execute('''UPDATE notification_deliveries
                      SET status='DELIVERED',delivered_at=?,error_class=NULL,request_id=?,receipt=?
                      WHERE event_id=? AND channel=? AND attempts=?''',
                               (now.isoformat(),receipt.get('request_id'),receipt.get('receipt'),key,channel,attempts+1))
                    result['channels'][channel]['delivered']+=1
                # Preserve the legacy event-level macOS status for existing readers.
                if channel == 'macos':
                    db.execute('''UPDATE notification_outbox SET status=?,attempts=?,next_attempt_at=?,
                      delivered_at=?,error_class=? WHERE event_id=?''',
                               ('DELIVERED' if not error else status,attempts+1,next_attempt,
                                now.isoformat() if not error else None,error,key))
    result['sent_to_macos']=result['channels']['macos']['delivered']
    result['failed']=sum(item['failed'] for item in result['channels'].values())
    return result

def record_views(path,card_ids,now):
    with connection(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS card_views(card_id TEXT PRIMARY KEY,first_rendered_at TEXT NOT NULL)')
        for key in card_ids:
            db.execute('INSERT OR IGNORE INTO card_views SELECT id,? FROM approval_inbox WHERE id=?',(now.isoformat(),key))
