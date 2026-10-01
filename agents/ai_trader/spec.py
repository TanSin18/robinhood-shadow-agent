"""Load and pin the forward-experiment spec. Any byte change is a new trial."""
from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

import yaml

SPEC_PATH = Path(__file__).resolve().parents[2] / 'research' / 'recipes' / 'ai_trader_fwd_v1.yaml'


class SpecError(ValueError):
    pass


class Spec:
    def __init__(self, raw: dict, sha256: str):
        self.raw, self.sha256 = raw, sha256
        r = raw['risk']
        self.id = raw['recipe']['id']
        self.capital = Decimal(raw['books']['capital_usd_each'])
        self.universe = tuple(raw['universe']['tradable'])
        self.max_fraction = Decimal(r['max_fraction_per_name'])
        self.max_names = int(r['max_names'])
        self.entries_per_day = int(r['entries_per_day_max'])
        self.daily_stop = Decimal(r['daily_book_loss_stop'])
        self.weekly_stop = Decimal(r['weekly_book_loss_stop'])
        self.limit_band = Decimal(r['fills']['limit_band'])
        self.slippage = Decimal('0.001')
        self.time_stop_max = int(raw['ticket_fields']['time_stop_sessions_max'])
        self.thesis_max_sentences = int(raw['ticket_fields']['thesis_max_sentences'])
        self.daily_budget = Decimal(raw['budget']['daily_cap_usd'])
        self.envelopes = raw['budget']['envelopes']
        self.models = {seat: raw['seats'][seat]['model'] for seat in ('scout', 'pm', 'critic')}
        self.models['manage'] = self.models['pm']
        self.seed = raw['books']['C']['seed']
        self.start_not_before = raw['recipe']['start_not_before']
        self.protective_stop = Decimal('0.08')
        self.fail_codes = tuple(raw['critic_fail_codes'])


def load_spec(path=SPEC_PATH) -> Spec:
    data = Path(path).read_bytes()
    raw = yaml.safe_load(data)
    if not isinstance(raw, dict) or raw.get('recipe', {}).get('kind') != 'forward_paper_experiment':
        raise SpecError('SPEC_SHAPE_INVALID')
    if raw['recipe'].get('status') != 'research_only_never_official':
        raise SpecError('SPEC_MUST_BE_RESEARCH_ONLY')
    if raw['universe'].get('options', '').startswith('on'):
        raise SpecError('OPTIONS_NOT_ALLOWED_IN_V1')
    return Spec(raw, hashlib.sha256(data).hexdigest())
