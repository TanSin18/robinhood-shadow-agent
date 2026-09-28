"""Install the explicitly requested local launchd application services."""
import argparse
import os
import plistlib
import subprocess
import time
import pwd
from pathlib import Path

def require_paused_install(path):
    from agents.safety_events import safety_stopped
    if not safety_stopped(path):
        raise ValueError('Service repairs require an active safety pause; installation never enables inference')

def reload_service(label,path,uid,*,runner=subprocess.run,wait=time.sleep):
    target=f'gui/{uid}/{label}'
    runner(['/bin/launchctl','bootout',target],capture_output=True)
    for _ in range(20):
        state=runner(['/bin/launchctl','print',target],capture_output=True)
        if state.returncode in {3,113}: break
        if state.returncode!=0: raise RuntimeError('Cannot establish prior service state')
        wait(.25)
    else: raise RuntimeError('Prior service did not unload within deadline')
    for _ in range(20):
        result=runner(['/bin/launchctl','bootstrap',f'gui/{uid}',str(path)],capture_output=True)
        if result.returncode==0: return
        if result.returncode!=5: raise RuntimeError('Service registration failed')
        wait(.25)
    raise RuntimeError('Service registration did not complete within deadline')


def service_definitions(root):
    root=Path(root).resolve()
    common={'WorkingDirectory':str(root),'EnvironmentVariables':{'PATH':'/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin','TZ':'America/New_York'}}
    services={}
    proxy_label='com.openai.robinhood-read-proxy'
    proxy_runtime=Path('/Users/Shared/RobinhoodShadow')
    private=proxy_runtime/'private/current'
    services[proxy_label]={
        'WorkingDirectory':str(private/'app'),
        'EnvironmentVariables':{'PATH':'/usr/bin:/bin','TZ':'America/New_York',
                                'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1'},
        'Label':proxy_label,
        'ProgramArguments':[str(private/'python/bin/python3'),'-B','-E','-s','-m','broker_proxy.server',
                            '--config',str(private/'app/config/broker-proxy.local.yaml'),
                            '--preregistration',str(private/'app/preregistration.yaml')],
        'StandardOutPath':str(proxy_runtime/'logs/proxy.log'),
        'StandardErrorPath':str(proxy_runtime/'logs/proxy.error.log'),
        'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':15,
        'UserContext':'robinhoodproxy',
    }
    for name,module,extra in [('daily','agents.daily_cycle',['--mode','live','--scheduled']),('inbox','agents.inbox_web',[]),('maintenance','agents.maintenance',[])]:
        label=f'com.openai.robinhood-{name}'
        spec={**common,'Label':label,'ProgramArguments':[str(root/'.venv/bin/python'),'-m',module,'--config',str(root/'config/settings.local.yaml'),'--database',str(root/'data/agent.db'),*extra], 'StandardOutPath':str(root/f'logs/{name}.log'),'StandardErrorPath':str(root/f'logs/{name}.error.log'),'RunAtLoad':True}
        if name=='inbox':
            spec['KeepAlive']=True
            spec['ThrottleInterval']=15
        else:
            spec['StartInterval']=60 if name=='daily' else 300
            if name=='daily':
                # Same trusted interpreter as the app, outside iCloud. Apple's
                # system Python has a separate macOS Documents permission.
                spec['ProgramArguments']=['/opt/homebrew/opt/python@3.14/bin/python3.14',
                    str(proxy_runtime/'launch/runtime_preflight.py'),'--root',str(root),
                    '--python',str(root/'.venv/bin/python'),module,
                    '--config',str(root/'config/settings.local.yaml'),
                    '--database',str(root/'data/agent.db'),*extra]
                spec['StartCalendarInterval']=[{'Weekday':day,'Hour':10,'Minute':0} for day in range(1,6)]
        services[label]=spec
    return services


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--install',action='store_true')
    parser.add_argument('--service', action='append', choices=['daily','maintenance','read-proxy','inbox'])
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    from config.loader import load_config
    from agents.inbox import PaperInbox
    config=load_config(root/'config/settings.local.yaml')
    inbox=PaperInbox(root/'data/agent.db',config)
    if args.install: require_paused_install(inbox.path)
    preview=root/'work/launchd-preview'
    preview.mkdir(parents=True,exist_ok=True)
    (root/'logs').mkdir(exist_ok=True)
    if args.install:
        import shutil
        launch=Path('/Users/Shared/RobinhoodShadow/launch')
        launch.mkdir(mode=0o755,exist_ok=True)
        shutil.copyfile(root/'scripts/runtime_preflight.py',launch/'runtime_preflight.py')
        os.chmod(launch/'runtime_preflight.py',0o644)
        from scripts.check_broker_proxy_identity import check
        identity=check(root/'config/broker-proxy.local.yaml')
        if identity['status']!='PASSED':
            raise RuntimeError('Broker proxy identity preflight failed: '+','.join(identity['failures']))
        from broker_proxy.config import load_broker_proxy_config
        proxy_config=load_broker_proxy_config(root/'config/broker-proxy.local.yaml')
    for label,spec in service_definitions(root).items():
        # Dashboard restart is a separate post-proof action, never implicit.
        selected=args.service or ['daily','maintenance','read-proxy']
        if args.install and label.removeprefix('com.openai.robinhood-') not in selected:
            continue
        spec=dict(spec)
        proxy_user=spec.pop('UserContext',None)
        if args.install:
            uid=(pwd.getpwnam(proxy_user).pw_uid if proxy_user
                 else proxy_config.operator_uid)
            account=pwd.getpwuid(uid)
            destination=Path(account.pw_dir)/'Library/LaunchAgents'
            if os.geteuid() not in {0,uid}:
                raise RuntimeError('Service installation must run as the target user or administrator')
        else:
            uid=os.getuid(); destination=preview
        destination.mkdir(parents=True,exist_ok=True)
        path=destination/f'{label}.plist'
        path.write_bytes(plistlib.dumps(spec))
        if args.install and os.geteuid()==0:
            os.chown(path,uid,pwd.getpwuid(uid).pw_gid)
        subprocess.run(['/usr/bin/plutil','-lint',str(path)],check=True)
        if args.install:
            reload_service(label,path,uid)
    print('Installed application services.' if args.install else 'Validated service definitions; not activated.')


if __name__=='__main__':
    main()
