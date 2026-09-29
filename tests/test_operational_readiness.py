"""Readiness must reflect evidence, never a submitted success flag."""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def test_configuration_fingerprint_is_stable_across_processes(portable_settings):
    hashes = []
    for seed in ('1', '2', '3'):
        result = subprocess.run([
            sys.executable, '-c',
            'import sys; from config.loader import load_config; print(load_config(sys.argv[1]).config_hash)',
            str(portable_settings),
        ], env={**os.environ, 'PYTHONHASHSEED': seed}, capture_output=True, text=True, check=True)
        hashes.append(result.stdout.strip())
    assert hashes[0] == hashes[1] == hashes[2]


def evidence(tmp_path):
    """Local synthetic evidence exercises validation, not actual authentication."""
    from agents.readiness import OperationalProof, source_fingerprint, REQUIRED_TESTS
    from config.loader import load_config
    from data.store import SQLiteStore

    root = tmp_path / 'project'
    (root / 'agents').mkdir(parents=True)
    (root / 'agents' / 'worker.py').write_text('version = 1\n')
    (root / 'config').mkdir()
    (root / 'preregistration.yaml').write_bytes(Path('preregistration.yaml').read_bytes())
    config_path = root / 'config' / 'settings.yaml'
    config_path.write_bytes(Path('config/settings.yaml').read_bytes())
    config = load_config(config_path)
    now = datetime.now(timezone.utc)
    report = root / 'tests.xml'
    cases = sorted(set().union(*REQUIRED_TESTS.values()))
    report.write_text('<testsuites><testsuite tests="' + str(len(cases)) + '">' +
                      ''.join(f'<testcase classname="{c}" name="{n}"/>' for c, n in cases) +
                      '</testsuite></testsuites>')
    manifest = root / 'test-run.json'
    manifest.write_text(json.dumps({
        'test_run_id': 'offline-validation', 'source_hash': source_fingerprint(root),
        'config_hash': config.config_hash, 'report_sha256': sha(report.read_bytes()),
        'started_at': (now - timedelta(seconds=10)).isoformat(),
        'completed_at': now.isoformat(), 'exit_code': 0,
        'command': ['.venv/bin/python', '-m', 'pytest', '-q'],
    }))
    database = root / 'agent.db'
    store = SQLiteStore(database)
    result = {
        'cycle_id': 'cycle-evidence', 'status': 'COMPLETED',
        'data_mode': 'live_readonly', 'timestamp': now.isoformat(),
        'agents': [],
        'read_tools': ['get_accounts', 'get_portfolio', 'get_equity_quotes', 'get_equity_historicals'],
        'quote_count': 14, 'volatility_count': 14,
        'market_open': True, 'api_cost_estimate_usd': '0',
        'ai_gate': {'invoke': False, 'reason': 'AI_NOT_NEEDED', 'cost_usd': '0'},
        'source_hashes': {'robinhood-mcp:get_accounts': 'a' * 64},
        'notification_policy': 'log_only',
    }
    from broker.read_gateway import SCHEMAS
    result['trigger']='scheduled'
    result['transport_evidence']={'collector':{
        'selected_path':'full_scope_bounded_cash_fallback',
        'granted_scope_names':['internal'],'keychain_retrieval':'available',
        'effective_read_tools':sorted(SCHEMAS),'effective_write_tool_count':0,
        'remote_catalog_hash':'b'*64,
        'account_bounds':{
            'status':'VERIFIED',
            'checked_fields':['cash','buying_power','unleveraged_buying_power'],
        },
    },'inference':[]}
    from agents.readiness import canonical_hash
    receipt = {
        'record_type': 'background_cycle_receipt', 'cycle_id': result['cycle_id'],
        'result_hash': canonical_hash(result), 'source_hash': source_fingerprint(root),
        'config_hash': config.config_hash, 'completed_at': now.isoformat(),
        'runtime': {'service_label': 'com.openai.robinhood-daily', 'pid': 123,
                    'parent_pid': 1, 'launchd_confirmed': True,
                    'executable': str(root / '.venv/bin/python')},
    }
    store.append_json('run_states', result)
    store.append_json('run_states', receipt)
    proof = OperationalProof(root=root, config_path=config_path, database=database,
                             test_report=report, test_manifest=manifest)
    return proof, result, receipt, now


def replace_receipt(proof, receipt):
    with sqlite3.connect(proof.database) as db:
        db.execute('UPDATE run_states SET payload_json=? WHERE id=2', (json.dumps(receipt),))


def test_interactive_success_does_not_prove_background_auth(tmp_path):
    from agents.readiness import operations_ready
    proof, _, receipt, _ = evidence(tmp_path)
    receipt['runtime']['launchd_confirmed'] = False
    replace_receipt(proof, receipt)
    assert operations_ready(proof) is False
    assert proof.background_auth is False


def test_evidence_validates_then_source_change_closes_gate(tmp_path):
    from agents.readiness import operations_ready, require_operations_ready
    proof, _, _, _ = evidence(tmp_path)
    assert operations_ready(proof)
    (proof.root / 'agents/worker.py').write_text('version = 2\n')
    assert not operations_ready(proof)
    with pytest.raises(ValueError, match='not ready'):
        require_operations_ready(proof)


@pytest.mark.parametrize('mutation', ['fixture', 'unknown_tool', 'old', 'future', 'changed_result', 'wrong_config', 'missing_agent', 'malformed_runtime','manual_trigger','missing_isolation'])
def test_bad_background_evidence_fails_closed(tmp_path, mutation):
    from agents.readiness import canonical_hash, operations_ready
    proof, result, receipt, now = evidence(tmp_path)
    if mutation == 'fixture':
        result['data_mode'] = 'fixture'
    elif mutation=='manual_trigger':
        result['trigger']='manual_rerun'
    elif mutation=='missing_isolation':
        result.pop('transport_evidence',None)
    elif mutation == 'unknown_tool':
        result['read_tools'].append('transfer_money')
    elif mutation == 'old':
        receipt['completed_at'] = (now - timedelta(days=8)).isoformat()
    elif mutation == 'future':
        receipt['completed_at'] = (now + timedelta(hours=1)).isoformat()
    elif mutation == 'wrong_config':
        receipt['config_hash'] = '0' * 64
    elif mutation == 'missing_agent':
        result['agents'] = ['Research Agent']
    elif mutation == 'malformed_runtime':
        receipt['runtime'] = 'not an object'
    else:
        result['quote_count'] = 0
    if mutation != 'changed_result':
        receipt['result_hash'] = canonical_hash(result)
    with sqlite3.connect(proof.database) as db:
        db.execute('UPDATE run_states SET payload_json=? WHERE id=1', (json.dumps(result),))
    replace_receipt(proof, receipt)
    assert not operations_ready(proof)


@pytest.mark.parametrize('mutation', ['failure', 'skipped_required', 'empty', 'changed_hash', 'bad_config', 'stale', 'naive', 'collection_error'])
def test_test_artifact_cannot_lie_about_readiness(tmp_path, mutation):
    from agents.readiness import operations_ready
    proof, _, _, now = evidence(tmp_path)
    manifest = json.loads(proof.test_manifest.read_text())
    if mutation in {'failure', 'skipped_required'}:
        tag = 'failure' if mutation == 'failure' else 'skipped'
        proof.test_report.write_text(proof.test_report.read_text().replace('/>', f'><{tag}/></testcase>', 1))
        manifest['report_sha256'] = sha(proof.test_report.read_bytes())
    elif mutation == 'empty':
        proof.test_report.write_text('<testsuites/>')
        manifest['report_sha256'] = sha(proof.test_report.read_bytes())
    elif mutation == 'collection_error':
        proof.test_report.write_text(proof.test_report.read_text().replace('</testsuites>', '<error/></testsuites>'))
        manifest['report_sha256'] = sha(proof.test_report.read_bytes())
    elif mutation == 'changed_hash':
        proof.test_report.write_text(proof.test_report.read_text() + '\n')
    elif mutation == 'bad_config':
        manifest['config_hash'] = '0' * 64
    elif mutation == 'stale':
        manifest['started_at'] = (now - timedelta(days=8, seconds=1)).isoformat()
        manifest['completed_at'] = (now - timedelta(days=8)).isoformat()
    else:
        manifest['completed_at'] = now.replace(tzinfo=None).isoformat()
    proof.test_manifest.write_text(json.dumps(manifest))
    assert not operations_ready(proof)


def test_submitted_success_flags_are_forbidden(tmp_path):
    from agents.readiness import OperationalProof
    from pydantic import ValidationError
    proof, _, _, _ = evidence(tmp_path)
    with pytest.raises(ValidationError):
        OperationalProof(**proof.model_dump(), background_auth=True, evidence_valid=True)


def test_missing_database_is_not_created(tmp_path):
    from agents.readiness import operations_ready
    proof, _, _, _ = evidence(tmp_path)
    missing = tmp_path / 'missing.db'
    proof = proof.model_copy(update={'database': missing})
    assert not operations_ready(proof)
    assert not missing.exists()


def test_new_failed_cycle_invalidates_older_background_success(tmp_path):
    from agents.readiness import operations_ready
    from data.store import SQLiteStore
    proof, _, _, _ = evidence(tmp_path)
    assert operations_ready(proof)
    SQLiteStore(proof.database).append_json('run_states', {
        'status': 'FAILED', 'error_type': 'RuntimeError',
        'remediation': 'Inspect read-only auth',
    })
    assert not operations_ready(proof)


@pytest.mark.parametrize('identifier', [None, '', '   ', 123, []])
def test_malformed_cycle_ids_cannot_open_gate(tmp_path, identifier):
    from agents.readiness import canonical_hash, operations_ready
    proof, result, receipt, _ = evidence(tmp_path)
    if identifier is None:
        result.pop('cycle_id')
        receipt.pop('cycle_id')
    else:
        result['cycle_id'] = receipt['cycle_id'] = identifier
    receipt['result_hash'] = canonical_hash(result)
    with sqlite3.connect(proof.database) as db:
        db.execute('UPDATE run_states SET payload_json=? WHERE id=1', (json.dumps(result),))
    replace_receipt(proof, receipt)
    assessment = proof.assess()
    assert not operations_ready(proof)
    assert assessment['gates']['background_auth'] is False
    assert assessment['cycle_id'] is None


@pytest.mark.parametrize('mutation', ['lane_funding', 'starting_cash'])
def test_current_runtime_settings_must_match_approved_operating_limits(tmp_path, mutation):
    import yaml
    from agents.readiness import source_fingerprint, operations_ready
    from config.loader import load_config
    proof, _, receipt, _ = evidence(tmp_path)
    raw = yaml.safe_load(proof.config_path.read_text())
    if mutation == 'lane_funding':
        raw['paper_lanes']['stocks_etfs_starting_cash_usd'] = 5000
    else:
        raw['starting_cash_usd'] = 5000
    proof.config_path.write_text(yaml.safe_dump(raw))
    # All artifact hashes agree with the changed config: approval is a separate check.
    config = load_config(proof.config_path)
    manifest = json.loads(proof.test_manifest.read_text())
    for target in (receipt, manifest):
        target['source_hash'] = source_fingerprint(proof.root)
        target['config_hash'] = config.config_hash
    proof.test_manifest.write_text(json.dumps(manifest))
    replace_receipt(proof, receipt)
    assert not operations_ready(proof)


def test_background_detection_requires_actual_launchd_pid(monkeypatch, tmp_path):
    from agents.readiness import capture_runtime
    monkeypatch.setattr('agents.readiness.os.getpid', lambda: 123)
    monkeypatch.setattr('agents.readiness.os.getppid', lambda: 1)
    monkeypatch.setattr('agents.readiness.sys.executable', str(tmp_path / '.venv/bin/python'))
    monkeypatch.setenv('XPC_SERVICE_NAME', 'com.openai.robinhood-daily')
    monkeypatch.setattr('agents.readiness.subprocess.run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout='"PID" = 999;'))
    assert not capture_runtime(tmp_path)['launchd_confirmed']
    monkeypatch.setattr('agents.readiness.subprocess.run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout='"PID" = 123;'))
    assert capture_runtime(tmp_path)['launchd_confirmed']


def test_verifier_cli_reports_missing_evidence_without_writing_account(tmp_path, portable_settings):
    result = subprocess.run([
        sys.executable, '-m', 'scripts.verify_operations',
        '--config', str(portable_settings), '--database', str(tmp_path/'missing.db'),
        '--test-report', str(tmp_path/'missing.xml'), '--test-manifest', str(tmp_path/'missing.json'),
        '--output-dir', str(tmp_path/'report'),
    ], capture_output=True, text=True)
    assert result.returncode == 2
    report = json.loads((tmp_path/'report/operational-readiness.json').read_text())
    assert report['ready'] is False
    assert report['research_implementation_allowed'] is False
    assert not (tmp_path/'missing.db').exists()
    assert report['cycle_id'] is None


def test_scheduled_entrypoint_records_its_own_background_context(tmp_path, monkeypatch, capsys):
    from agents import daily_cycle
    from agents.inbox import PaperInbox
    from config.loader import load_config
    from agents.readiness import canonical_hash

    class Monday(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 28, 14, 0, tzinfo=timezone.utc)

    db = tmp_path/'cycle.db'
    config = load_config('config/settings.yaml')
    monkeypatch.setattr(daily_cycle, 'datetime', Monday)
    monkeypatch.setattr(daily_cycle, 'CodexBridge', lambda *a: daily_cycle.FixtureBridge(config, Monday.now()))
    class FakeReader(daily_cycle.FixtureReader):
        def close(self): pass
    monkeypatch.setattr('agents.market_reader.LiveReader',lambda *a:FakeReader(config,Monday.now()))
    monkeypatch.setattr('agents.readiness.capture_runtime', lambda root: {
        'service_label': 'com.openai.robinhood-daily', 'pid': 123, 'parent_pid': 1,
        'launchd_confirmed': True, 'executable': str(root/'.venv/bin/python'),
    })
    monkeypatch.setattr('sys.argv', ['daily_cycle', '--config', 'config/settings.yaml',
                                   '--database', str(db), '--mode', 'live', '--scheduled'])
    daily_cycle.main()
    rows = PaperInbox(db, config).store.read_json('run_states')
    result = next(r for r in rows if r.get('status') == 'COMPLETED')
    receipts = [r for r in rows if r.get('record_type') == 'background_cycle_receipt']
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt['cycle_id'] == result['cycle_id']
    assert receipt['result_hash'] == canonical_hash(result)
    assert receipt['runtime']['launchd_confirmed'] is True
    assert receipt['config_hash'] == config.config_hash
    assert receipt['source_hash']


def test_skipped_schedule_does_not_probe_auth_or_claim_success(tmp_path, monkeypatch, capsys):
    from agents import daily_cycle
    from agents.inbox import PaperInbox
    from config.loader import load_config
    monkeypatch.setattr('agents.cycle_lifecycle.CycleLifecycle.acquire', lambda *a, **kw: None)
    monkeypatch.setattr('agents.readiness.capture_runtime', lambda *a: pytest.fail('Skipped schedule must not probe auth'))
    monkeypatch.setattr(daily_cycle, 'CodexBridge', lambda *a: pytest.fail('Skipped schedule must not call inference'))
    db = tmp_path/'cycle.db'
    monkeypatch.setattr('sys.argv', ['daily_cycle', '--config', 'config/settings.yaml',
                                   '--database', str(db), '--mode', 'live', '--scheduled'])
    daily_cycle.main()
    assert json.loads(capsys.readouterr().out)['status'] == 'SKIPPED_SCHEDULE'
    assert PaperInbox(db, load_config('config/settings.yaml')).store.read_json('run_states') == []
