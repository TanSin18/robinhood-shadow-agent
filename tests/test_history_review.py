"""Checkpoint 8 review regressions. Each test was written to fail on the code it was found in, then the code was repaired.

Compliance and point-in-time integrity findings live here so that a later change cannot quietly undo a repair."""
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from firm_lab.errors import FirmLabError

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'firm_lab'


class _Recorder:
    """A transport that answers nothing and remembers what it was asked."""
    def __init__(self):
        self.urls = []

    def get(self, url, headers=None):
        from firm_lab_collectors.transport import Response
        self.urls.append(url)
        return Response(404, b'', url, '2026-10-04T16:00:00+00:00', 'not found', {})


# ---------------------------------------------------------------------------------------- licensing: FRED and ALFRED
def test_no_collector_asks_fred_or_alfred_and_no_fred_sourced_row_can_be_stored(tmp_path):
    """The St. Louis Fed terms prohibit, without written consent, storing FRED content and using it to develop or train
    machine-learning systems. Checkpoint 5's sample capture saved FRED and ALFRED answers to files, and the macro store
    accepted FRED as a source. Neither may remain."""
    from firm_lab import macro
    from firm_lab_collectors import capture
    public, keyed = _Recorder(), _Recorder()
    out = capture.run_macro(tmp_path / 'capture', environ={'FIRM_LAB_FRED_API_KEY': 'a' * 32}, transport=public, keyed_transport=keyed)
    assert public.urls and not [u for u in public.urls + keyed.urls if 'stlouisfed' in u]
    assert not keyed.urls and 'fred_api_key_present' not in out
    for path in sorted((ROOT / 'firm_lab_collectors').glob('*.py')):
        assert 'stlouisfed.org' not in path.read_text(), path.name
    assert 'FRED' not in macro.SOURCE_HOSTS and not [name for name, spec in macro.SERIES.items() if 'FRED' in spec[3]]
    raw = b'{"synthetic_fixture":true}'
    row = dict(series='unemployment_rate', value='4.3', unit='percent', period='2026-08', source='FRED',
               source_url='https://fred.stlouisfed.org/series/UNRATE', source_timestamp='2026-09-04T12:30:00Z', published_at='2026-09-04T12:30:00Z',
               ingested_at='2026-09-04T12:31:00Z', revision=0, source_hash=hashlib.sha256(raw).hexdigest())
    with pytest.raises(FirmLabError, match='SERIES_SOURCE_MISMATCH'):
        macro.validate_observation(row, raw=raw, now=datetime(2026, 10, 3, 16, tzinfo=timezone.utc))
