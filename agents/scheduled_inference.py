"""Registered inference restricted to the current official cycle owner."""
from pathlib import Path
from decimal import Decimal
from agents.bounded_inference import BoundedInference
from data.connections import connection
from agents.safety_events import safety_stopped
from agents.bounded_inference import validate_registered_models


class LazyAPIClient:
    """No credential read or network use until a qualified AI invocation."""
    def __init__(self):
        self.client = None

    def with_options(self, **options):
        if options != {'max_retries':0,'timeout':120.0}:
            raise ValueError('UNREGISTERED_CLIENT_OPTIONS')
        return self

    @property
    def responses(self):
        if self.client is None:
            import subprocess
            from openai import OpenAI
            try:
                result=subprocess.run(['/usr/bin/security','find-generic-password',
                    '-s','robinhood-shadow-openai','-a','rehearsal','-w'],
                    capture_output=True,timeout=10)
            except (OSError,subprocess.TimeoutExpired):
                raise ValueError('API_ACCESS_UNAVAILABLE') from None
            if result.returncode or not result.stdout.strip():
                raise ValueError('API_ACCESS_UNAVAILABLE')
            self.client=OpenAI(api_key=result.stdout.decode().strip(),
                base_url='https://api.openai.com/v1',max_retries=0,timeout=120.0)
            del result
        return self.client.responses


def configured_scheduled_bridge(path,config,*,lifecycle,cycle_id):
    validate_registered_models(config)
    if config.stage!=1 or config.broker!='paper' or config.daily_api_budget_usd!=Decimal('.40'):
        raise ValueError('REGISTERED_SCHEDULED_CONFIG_REQUIRED')
    return ScheduledInference(path,client=LazyAPIClient(),lifecycle=lifecycle,cycle_id=cycle_id)


class ScheduledInference(BoundedInference):
    database_mode = 'live'
    data_mode = 'live_readonly'
    ceiling_key = 'official_daily_llm_ceiling'

    def __init__(self, path, *, client, lifecycle, cycle_id):
        self.path = Path(path)
        self.lifecycle, self.cycle_id = lifecycle, cycle_id
        self.isolation_evidence = []
        self.check_owner()
        super().__init__(path,client=client)

    def check_owner(self):
        if self.lifecycle is None or Path(self.lifecycle.path).resolve()!=self.path.resolve():
            raise ValueError('INFERENCE_OWNERSHIP_REQUIRED')
        with connection(self.path) as db:
            if not self.lifecycle.owns(db,self.cycle_id):
                raise ValueError('INFERENCE_OWNERSHIP_REQUIRED')
        if safety_stopped(self.path):
            raise ValueError('INFERENCE_SAFETY_STOP')

    def _run(self, *args, **kwargs):
        self.check_owner()
        result = super()._run(*args, **kwargs)
        self.isolation_evidence.append({'transport':'responses_api','tools':[],
            'broker_access':False,'registered_model':args[0],
            'hard_output_cap':True,'automatic_retries':0})
        return result

    def before_generation(self):
        self.check_owner()
