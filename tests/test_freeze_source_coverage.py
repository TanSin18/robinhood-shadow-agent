import pytest


@pytest.mark.parametrize('relative', [
    'broker_proxy/server.py',
    'research/strategy_signals.py',
    'broker/read_schemas_v1.4.2.json',
    'agents/static/avatar.svg',
    'agents/static/font.woff2',
    'agents/static/page.html',
])
def test_scheduled_proof_fingerprint_detects_proxy_and_dashboard_asset_changes(tmp_path, relative):
    from agents.readiness import source_fingerprint

    (tmp_path / 'pyproject.toml').write_text('[project]\nname="test"\n')
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'before')
    before = source_fingerprint(tmp_path)
    path.write_bytes(b'after')
    assert source_fingerprint(tmp_path) != before
