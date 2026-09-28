"""Evidence-based prerequisite gate. No brokerage, inference or account writes.

This is a local audit boundary, not a defense against a malicious operator who
can rewrite the application and its database. Artifacts never contain secrets.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from broker.policy import READ_ONLY_TOOL_ALLOWLIST
from config.loader import load_config
from data.connections import connection

SERVICE_LABEL = 'com.openai.robinhood-daily'
REQUIRED_READS = {'get_accounts', 'get_portfolio', 'get_equity_quotes', 'get_equity_historicals'}
EXPECTED_AGENTS = ['Research Agent', 'Portfolio Agent', 'Critic']
REQUIRED_TESTS = {
    'approved_phase0_boundary': {('tests.test_preregistration_phase0','test_phase0_preflight_accepts_exact_approved_registration')},
    'isolated_proxy_auth': {('tests.test_robinhood_oauth','test_keychain_storage_round_trips_tokens_and_client_info'),('tests.test_market_reader','test_live_reader_uses_local_proxy_client_not_codex_session')},
    'application_write_denial': {('tests.test_direct_read_gateway','test_every_enforcement_layer_blocks_non_exact_tool_before_upstream')},
    'bounded_cash_fallback': {('tests.test_direct_read_gateway','test_bounded_fallback_holds_outside_cap_or_on_margin')},
    'fixture_isolation': {('tests.test_database_role','test_fixture_never_claims_live_day'),('tests.test_database_role','test_fixture_refuses_database_with_live_evidence')},
    'scheduler_lifecycle': {('tests.test_cycle_lifecycle','test_exchange_calendar_classifies_official_window'),('tests.test_cycle_lifecycle','test_stale_worker_fenced_and_lock_retained'),('tests.test_cycle_lifecycle','test_only_scheduled_worker_can_claim_official_day')},
    'notifications': {('tests.test_notification_outbox','test_issue_deduplicates_notification_and_delivery'),('tests.test_notification_outbox','test_failed_notification_does_not_rollback_fill')},
    'freshness_budget': {('tests.test_cycle_budget_and_freshness','test_stale_refresh_never_issues'),('tests.test_phase0_budget','test_official_etf_only_cycle_is_code_only_and_records_zero_ai_cost')},
    'corporate_actions': {('tests.test_corporate_actions','test_split_and_reverse_split_normalize_every_live_value'),('tests.test_corporate_actions','test_ticker_change_preserves_permanent_identity')},
    'automatic_breakers': {('tests.test_breakers','test_automatic_breakers_block_new_entries'),('tests.test_breakers','test_peak_breaker_rearms_only_after_documented_operator_approval')},
    'daily_cycle': {
        ('tests.test_daily_cycle', 'test_once_per_trading_day_scheduler_and_intraday_code_only'),
        ('tests.test_service_schedule', 'test_intraday_maintenance_expires_without_model_or_broker'),
        ('tests.test_codex_bridge', 'test_raw_mcp_event_is_authority_and_usage_is_persisted'),
        ('tests.test_codex_bridge', 'test_budget_survives_restart_and_reserves_atomically'),
    },
    'inbox': {
        ('tests.test_inbox_web', 'test_yes_button_records_decision_and_public_trace_masks_account'),
        ('tests.test_inbox_lanes', 'test_pending_survives_restart_and_only_yes_fills_approval_track'),
        ('tests.test_inbox_lanes', 'test_config_expiry_and_no_never_fill'),
        ('tests.test_runtime_safety', 'test_no_is_persisted_as_skipped_fill'),
    },
    'agent_only_api_costs': {('tests.test_hardening', 'test_benchmarks_do_not_pay_for_agents')},
    'closing_checked': {('tests.test_hardening', 'test_closing_claim_cannot_create_unheld_shares')},
    'cash_checked': {('tests.test_hardening', 'test_risk_cash_check_is_independent_of_paper_broker')},
    'real_writes_blocked': {
        ('tests.test_stage1_robinhood_policy', 'test_stage_one_blocks_real_order_cancel_and_exercise_before_invocation'),
        ('tests.test_codex_bridge', 'test_bridge_blocks_writes_before_process'),
    },
}


def canonical_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def source_fingerprint(root: Path) -> str:
    root = Path(root).resolve()
    paths = [root / 'pyproject.toml', root / 'preregistration.yaml']
    for folder in ('agents', 'broker', 'broker_proxy', 'config', 'data', 'eval', 'risk', 'research', 'scripts', 'prompts', 'tests'):
        base = root / folder
        if base.is_dir():
            paths.extend(p for p in base.rglob('*') if p.is_file() and
                         (p.suffix in {'.py', '.sql', '.md', '.yaml', '.css', '.js', '.html', '.svg', '.woff', '.woff2'} or
                          (folder in {'broker', 'broker_proxy'} and p.suffix == '.json')) and
                         p.name != 'settings.local.yaml' and '__pycache__' not in p.parts)
    entries = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(set(paths)) if p.is_file()}
    if not entries:
        raise ValueError('No operational source files found')
    return canonical_hash(entries)


def capture_runtime(root: Path) -> dict:
    """Prove this PID belongs to the installed launchd job; environment is insufficient."""
    pid, parent = os.getpid(), os.getppid()
    expected = Path(root).absolute() / '.venv/bin/python'
    confirmed = False
    if parent == 1 and Path(sys.executable).absolute() == expected:
        try:
            result = subprocess.run(['/bin/launchctl', 'list', SERVICE_LABEL],
                                    capture_output=True, text=True, timeout=5, check=False)
            match = re.search(r'"PID"\s*=\s*(\d+)\s*;', result.stdout)
            confirmed = result.returncode == 0 and match is not None and int(match[1]) == pid
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {'service_label': SERVICE_LABEL if confirmed else None,
            'pid': pid, 'parent_pid': parent, 'launchd_confirmed': confirmed,
            'executable': str(expected) if Path(sys.executable).absolute() == expected else None}


def record_background_receipt(store, result: dict, runtime: dict, *, source_hash: str,
                              config_hash: str, completed_at: datetime) -> dict:
    receipt = {'record_type': 'background_cycle_receipt',
               'cycle_id': result.get('cycle_id'), 'result_hash': canonical_hash(result),
               'source_hash': source_hash, 'config_hash': config_hash,
               'completed_at': completed_at.isoformat(), 'runtime': dict(runtime)}
    store.append_json('run_states', receipt)
    return receipt


def _timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('Naive evidence timestamp')
    return result


def _valid_cycle_id(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 128 and value.strip() == value


class OperationalProof(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    root: Path
    config_path: Path
    database: Path
    test_report: Path
    test_manifest: Path
    max_age_hours: int = Field(default=72, gt=0, le=168)

    def assess(self, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError('Readiness clock must be timezone-aware')
        gates = {name: False for name in REQUIRED_TESTS}
        gates['background_auth'] = False
        gates.update(proxy_auth=False,exact_read_capability=False,bounded_cash=False,
                     source_hashes=False,background_data_reads=False,scheduled_full_cycle=False)
        blockers, report_cases = [], set()
        output = {'checked_at': now.isoformat(), 'gates': gates, 'cycle_id': None,
                  'test_run_id': None, 'tests': {}, 'blockers': blockers,
                  'real_execution': 'blocked', 'cost_basis': 'estimated_api_equivalent',
                  'market_open_verified': False, 'evidence_valid': False}
        horizon = timedelta(hours=self.max_age_hours)
        try:
            config = load_config(self.config_path)
            from agents.preregistration import load_phase0_registration
            registration = load_phase0_registration(self.root / 'preregistration.yaml')
            source_hash = source_fingerprint(self.root)
            output.update(source_hash=source_hash, config_hash=config.config_hash,
                          preregistration_version=registration.version,
                          preregistration_hash=registration.canonical_sha256)
            config.validate_runtime_ready()
            if config.stage != 1 or config.broker != 'paper':
                raise ValueError('Stage 1 paper required')
            if config.daily_api_budget_usd != Decimal('0.40'):
                raise ValueError('Approved budget changed')
            if config.starting_cash_usd != Decimal(500) or config.paper_lanes != {
                'stocks_etfs_starting_cash_usd': Decimal(500),
                'options_starting_cash_usd': Decimal(500),
            }:
                raise ValueError('Approved paper account funding changed')
        except (OSError, ValueError, TypeError):
            blockers.append('Operational configuration or source snapshot is unavailable or invalid.')
            return self._finish(output)

        try:
            manifest = json.loads(self.test_manifest.read_text())
            report_bytes = self.test_report.read_bytes()
            if hashlib.sha256(report_bytes).hexdigest() != manifest['report_sha256']:
                raise ValueError('Changed test report')
            if manifest['source_hash'] != source_hash or manifest['config_hash'] != config.config_hash:
                raise ValueError('Stale test version')
            start, finish = _timestamp(manifest['started_at']), _timestamp(manifest['completed_at'])
            if not start <= finish <= now or now - start >= horizon or manifest['exit_code'] != 0:
                raise ValueError('Stale or unsuccessful tests')
            tree = ET.fromstring(report_bytes)
            cases = list(tree.iter('testcase'))
            if not cases or any(list(case) and any(c.tag in {'failure', 'error', 'skipped'} for c in case) for case in cases):
                raise ValueError('Missing, failed or skipped tests')
            if next(tree.iter('error'), None) is not None or next(tree.iter('failure'), None) is not None:
                raise ValueError('Collection failure')
            report_cases = {(case.attrib.get('classname'), case.attrib.get('name', '').split('[')[0]) for case in cases}
            output['test_run_id'] = manifest['test_run_id']
            output['tests'] = {'passed': len(cases), 'failed': 0, 'skipped': 0,
                               'completed_at': finish.isoformat(), 'sha256': manifest['report_sha256']}
            for name, required in REQUIRED_TESTS.items():
                gates[name] = required <= report_cases
                if not gates[name]:
                    blockers.append(f'Required regression evidence missing: {name}.')
        except (OSError, ValueError, KeyError, TypeError, ET.ParseError):
            blockers.append('Fresh passing tests matching the current code/configuration are not proven.')

        try:
            uri = self.database.resolve().as_uri() + '?mode=ro'
            with connection(uri, uri=True) as db:
                records = [json.loads(row[0]) for row in db.execute('SELECT payload_json FROM run_states ORDER BY id')]
            if any(not isinstance(r, dict) for r in records):
                raise ValueError('Malformed run evidence')
            cycles = {r['cycle_id']: r for r in records
                      if r.get('status') == 'COMPLETED' and _valid_cycle_id(r.get('cycle_id'))}
            receipts = [(index, r) for index, r in enumerate(records)
                        if r.get('record_type') == 'background_cycle_receipt']
            for index, receipt in reversed(receipts):
                cycle_id = receipt.get('cycle_id')
                if not _valid_cycle_id(cycle_id):
                    continue
                if any(r.get('status') == 'FAILED' for r in records[index + 1:]):
                    continue
                result = cycles.get(cycle_id)
                if not result:
                    continue
                runtime = receipt['runtime']
                if not isinstance(runtime, dict):
                    raise ValueError('Malformed runtime evidence')
                completed = _timestamp(receipt['completed_at'])
                started = _timestamp(result['timestamp'])
                tools = set(result.get('read_tools', []))
                from broker.read_gateway import SCHEMAS
                transport=result.get('transport_evidence') or {}
                collector=transport.get('collector') or {}
                sessions=transport.get('inference') or []
                bounds=collector.get('account_bounds') or {}
                scope_ok=(collector.get('selected_path')=='full_scope_bounded_cash_fallback'
                          and collector.get('granted_scope_names')==['internal']
                          and collector.get('keychain_retrieval')=='available')
                capability_ok=(set(collector.get('effective_read_tools',[]))==set(SCHEMAS)
                               and collector.get('effective_write_tool_count')==0
                               and isinstance(collector.get('remote_catalog_hash'),str)
                               and len(collector['remote_catalog_hash'])==64)
                bounded_cash=(
                    bounds.get('status')=='VERIFIED'
                    and bounds.get('checked_fields')==[
                        'cash','buying_power','unleveraged_buying_power'
                    ]
                )
                hashes=result.get('source_hashes') or {}
                hashes_ok=bool(hashes) and all(isinstance(value,str) and len(value)==64 for value in hashes.values())
                gate=result.get('ai_gate') or {}
                code_only=(gate.get('invoke') is False and result.get('agents')==[]
                           and Decimal(str(result.get('api_cost_estimate_usd')))==0
                           and sessions==[])
                ai_cycle=(result.get('agents')==EXPECTED_AGENTS and len(sessions)==3)
                valid = (
                    receipt['source_hash'] == source_hash and receipt['config_hash'] == config.config_hash
                    and receipt['result_hash'] == canonical_hash(result)
                    and started <= completed <= now and now - started < horizon
                    and runtime.get('launchd_confirmed') is True
                    and runtime.get('service_label') == SERVICE_LABEL
                    and runtime.get('parent_pid') == 1 and type(runtime.get('pid')) is int and runtime['pid'] > 1
                    and runtime.get('executable') == str(self.root.absolute() / '.venv/bin/python')
                    and result.get('data_mode') == 'live_readonly' and (code_only or ai_cycle)
                    and result.get('quote_count', 0) > 0 and result.get('volatility_count', 0) > 0
                    and REQUIRED_READS <= tools <= READ_ONLY_TOOL_ALLOWLIST
                    and result.get('trigger') in {'scheduled','scheduled_recovery'}
                    and scope_ok and capability_ok and bounded_cash and hashes_ok
                    and result.get('notification_policy') in {'log_only','required_actions_only'}
                )
                if valid:
                    confirmed = dict(cycle_id=cycle_id, background_completed_at=completed.isoformat(),
                                  runtime=runtime, read_tools=sorted(tools),
                                  api_cost_estimate_usd=result.get('api_cost_estimate_usd'),
                                  market_open_verified=result.get('market_open') is True)
                    output.update(confirmed)
                    gates['background_auth'] = True
                    gates.update(proxy_auth=True,exact_read_capability=True,bounded_cash=True,
                                 source_hashes=True,background_data_reads=True,scheduled_full_cycle=True)
                    break
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
            pass
        if not gates['background_auth']:
            blockers.append('No fresh authenticated full cycle is proven under the installed launchd service for this code/configuration.')
        output['evidence_valid'] = all(gates.values()) and not blockers
        return self._finish(output)

    @staticmethod
    def _finish(output):
        output['ready'] = output['evidence_valid'] and all(output['gates'].values())
        output['phase0_gate_passed'] = output['ready']
        output['research_implementation_allowed'] = False
        output['phase1_blocked_pending_v1_5_approval'] = True
        return output

    @property
    def evidence_valid(self) -> bool:
        return self.assess()['evidence_valid']

    @property
    def background_auth(self) -> bool:
        return self.assess()['gates']['background_auth']


def operations_ready(proof: OperationalProof) -> bool:
    return proof.assess()['ready']


def require_operations_ready(proof: OperationalProof) -> None:
    assessment = proof.assess()
    if not assessment['ready']:
        raise ValueError('Operations not ready: ' + ' '.join(assessment['blockers']))
