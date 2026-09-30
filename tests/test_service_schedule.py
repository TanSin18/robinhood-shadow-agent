import plistlib
from pathlib import Path
from datetime import datetime, timezone

from test_inbox_lanes import setup_runtime


def test_launchd_runs_local_python_readonly_once_and_inbox(tmp_path):
    from scripts.install_shadow_services import service_definitions
    services=service_definitions(Path.cwd())
    assert set(services)=={'com.openai.robinhood-daily','com.openai.robinhood-inbox','com.openai.robinhood-maintenance','com.openai.robinhood-read-proxy','com.openai.robinhood-universe-screen'}
    screen=services['com.openai.robinhood-universe-screen']
    assert 'agents.nightly_screen' in screen['ProgramArguments'] and 'StartInterval' not in screen
    assert screen['StartCalendarInterval']==[{'Weekday':d,'Hour':16,'Minute':50} for d in range(1,6)]
    proxy=services['com.openai.robinhood-read-proxy']
    assert 'broker_proxy.server' in proxy['ProgramArguments']
    assert proxy['UserContext']=='robinhoodproxy'
    assert proxy['KeepAlive'] is True
    assert 'broker-proxy.local.yaml' in ' '.join(proxy['ProgramArguments'])
    daily=services['com.openai.robinhood-daily']
    assert daily['StartInterval']==60
    assert '--scheduled' in daily['ProgramArguments']
    assert 'agents.daily_cycle' in daily['ProgramArguments']
    for spec in services.values():
        assert Path(spec['ProgramArguments'][0]).is_absolute()
        assert plistlib.loads(plistlib.dumps(spec))==spec


def test_intraday_maintenance_expires_without_model_or_broker(tmp_path,monkeypatch):
    from agents.maintenance import run_once
    from agents.codex_bridge import CodexBridge
    monkeypatch.setattr(CodexBridge,'run',lambda *a,**kw: (_ for _ in ()).throw(AssertionError('No intraday model calls')))
    inbox,_=setup_runtime(tmp_path)
    result=run_once(inbox,datetime(2026,9,28,18,tzinfo=timezone.utc),tmp_path)
    assert result['mode']=='code_only'


def test_t_plus_one_settlement_skips_weekends_and_holidays(tmp_path):
    from agents.maintenance import next_settlement_day
    from datetime import date
    assert next_settlement_day(date(2026,9,25))==date(2026,9,28)
    assert next_settlement_day(date(2026,11,25))==date(2026,11,27)


def test_maintenance_checks_authorization_even_while_paused(tmp_path):
    from agents.maintenance import run_once
    inbox,_=setup_runtime(tmp_path)
    (tmp_path/'STOP_TRADING').write_text('pause')
    calls=[]
    def check():
        calls.append('checked')
        return {'status':'WARNING_1_DAY'}
    result=run_once(inbox,datetime(2026,9,28,18,tzinfo=timezone.utc),tmp_path,authorization_check=check)
    assert calls==['checked']
    assert result['authorization']['status']=='WARNING_1_DAY'

def test_repair_install_requires_pause(tmp_path):
    import pytest
    from scripts.install_shadow_services import require_paused_install
    inbox,_=setup_runtime(tmp_path)
    with pytest.raises(ValueError,match='pause'): require_paused_install(inbox.path)
    (tmp_path/'STOP_TRADING').write_text('test pause')
    require_paused_install(inbox.path)

def test_reload_waits_for_old_job_and_retries_transient_bootstrap(tmp_path):
    from scripts.install_shadow_services import reload_service
    from types import SimpleNamespace
    calls=[]; replies=iter([0,0,113,5,0])
    def runner(args,**kwargs):
        calls.append(args[1]); return SimpleNamespace(returncode=next(replies))
    reload_service('example',tmp_path/'example.plist',501,runner=runner,wait=lambda seconds:None)
    assert calls==['bootout','print','print','bootstrap','bootstrap']
