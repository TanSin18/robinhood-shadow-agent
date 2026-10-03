"""Versioned feature contracts; numeric payloads are finite decimal strings."""
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

FAMILIES = frozenset(('trend', 'momentum', 'volatility', 'support_resistance',
    'fibonacci', 'candlestick_geometry', 'breakout_structure', 'volume', 'sector',
    'fundamentals', 'earnings_events', 'macro_context', 'intraday_future'))


def timestamp(value):
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError('Timezone required')
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError) as e:
        raise ValueError('INVALID_TIMESTAMP') from e


def canonical(value):
    if is_dataclass(value):
        value = asdict(value)
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError) as e:
        raise ValueError('INVALID_PAYLOAD') from e


def content_hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def valid_hash(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('INVALID_CONTENT_HASH')


@dataclass(frozen=True)
class SourceRef:
    table: str
    row_id: str
    content_hash: str
    known_at: str

    def __post_init__(self):
        if self.table not in {'feature_observations', 'filing_observations',
                'fundamental_fact_observations', 'earnings_event_observations',
                'macro_observations', 'macro_events', 'research_sector_mappings',
                'corporate_action_observations', 'intraday_bar_observations',
                'universe_snapshots'} or not self.row_id:
            raise ValueError('INVALID_SOURCE')
        valid_hash(self.content_hash)
        object.__setattr__(self, 'known_at', timestamp(self.known_at))


@dataclass(frozen=True)
class Request:
    instrument: str
    as_of_session: str
    knowledge_cutoff: str

    def __post_init__(self):
        if not self.instrument or len(self.instrument) > 32:
            raise ValueError('INVALID_INSTRUMENT')
        date.fromisoformat(self.as_of_session)
        object.__setattr__(self, 'knowledge_cutoff', timestamp(self.knowledge_cutoff))


@dataclass(frozen=True)
class FeatureResult:
    instrument: str
    family: str
    name: str
    value: str | bool | dict | None
    unit: str
    as_of_session: str
    known_at: str | None
    availability: str
    missing_reason: str | None
    refs: tuple[SourceRef, ...]
    feature_version: str
    calculation_hash: str
    audit: dict

    def __post_init__(self):
        if self.family not in FAMILIES or not all((self.instrument, self.name,
                                                  self.unit, self.feature_version)):
            raise ValueError('INVALID_DEFINITION')
        date.fromisoformat(self.as_of_session)
        valid_hash(self.calculation_hash)
        if not isinstance(self.refs, tuple) or not all(isinstance(r, SourceRef) for r in self.refs):
            raise ValueError('INVALID_REFS')
        if self.availability == 'AVAILABLE':
            if self.value is None or not self.refs or self.missing_reason:
                raise ValueError('AVAILABLE_REQUIRES_EVIDENCE')
            object.__setattr__(self, 'known_at', timestamp(self.known_at))
            if any(r.known_at > self.known_at for r in self.refs):
                raise ValueError('KNOWN_AT_BEFORE_INPUT')
        elif self.availability == 'UNAVAILABLE':
            if self.value is not None or self.known_at is not None or not self.missing_reason:
                raise ValueError('UNAVAILABLE_REQUIRES_NULL')
        else:
            raise ValueError('INVALID_AVAILABILITY')
        if isinstance(self.value, str):
            try:
                if not Decimal(self.value).is_finite():
                    raise ValueError('NONFINITE')
            except InvalidOperation as e:
                raise ValueError('NUMERIC_STRING_REQUIRED') from e
        elif self.value is not None and not isinstance(self.value, (bool, dict)):
            raise ValueError('INVALID_VALUE_TYPE')
        canonical(self)


def from_payload(payload):
    data = json.loads(payload)
    data['refs'] = tuple(SourceRef(**r) for r in data['refs'])
    return FeatureResult(**data)
