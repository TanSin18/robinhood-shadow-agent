"""Verify operations without trading, inference, credential access or DB writes."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agents.readiness import OperationalProof, source_fingerprint
from config.loader import load_config


def write_report(assessment: dict, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'operational-readiness.json').write_text(json.dumps(assessment, indent=2) + '\n')
    lines = ['# Operational prerequisite check', '',
             '**Research may proceed:** ' + ('yes' if assessment['ready'] else 'no'), '',
             'Stage 1 real-money execution remains blocked.', '',
             '| Check | Result |', '|---|---|']
    lines += [f'| {name.replace("_", " ")} | {"verified" if value else "not proven"} |'
              for name, value in assessment['gates'].items()]
    lines += ['', f'Passing tests: {assessment["tests"].get("passed", "unavailable")}.',
              f'Background cycle: {assessment.get("cycle_id") or "not proven"}.', '',
              '## Remaining blockers', '']
    lines += ['- ' + reason for reason in assessment['blockers']] or ['None.']
    lines += ['', 'A successful interactive run or a skipped schedule is not proof of background authentication.',
              'Costs are estimates of API-equivalent usage, not an asserted invoice.',
              'No research strategy has been implemented or qualified by this check.', '']
    (destination / 'operational-readiness.md').write_text('\n'.join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='config/settings.local.yaml')
    parser.add_argument('--database', default='data/agent.db')
    parser.add_argument('--test-report', default='outputs/operational-test-results.xml')
    parser.add_argument('--test-manifest', default='outputs/operational-test-run.json')
    parser.add_argument('--output-dir', default='outputs')
    parser.add_argument('--run-tests', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report, manifest = Path(args.test_report).resolve(), Path(args.test_manifest).resolve()
    config_path = Path(args.config).resolve()
    if args.run_tests:
        report.parent.mkdir(parents=True, exist_ok=True)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        started = datetime.now(timezone.utc)
        source_hash = source_fingerprint(root)
        config_hash = load_config(config_path).config_hash
        command = [sys.executable, '-m', 'pytest', '-q', f'--junitxml={report}']
        result = subprocess.run(command, cwd=root, check=False)
        manifest.write_text(json.dumps({
            'test_run_id': uuid4().hex, 'source_hash': source_hash, 'config_hash': config_hash,
            'report_sha256': hashlib.sha256(report.read_bytes()).hexdigest() if report.exists() else None,
            'started_at': started.isoformat(), 'completed_at': datetime.now(timezone.utc).isoformat(),
            'exit_code': result.returncode, 'command': command,
        }, indent=2) + '\n')
    proof = OperationalProof(root=root, config_path=config_path, database=Path(args.database).resolve(),
                             test_report=report, test_manifest=manifest)
    assessment = proof.assess()
    write_report(assessment, Path(args.output_dir))
    print(json.dumps(assessment, indent=2))
    return 0 if assessment['ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
