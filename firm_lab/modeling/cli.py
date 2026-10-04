"""Operator-invoked modeling research. Local, manual, never scheduled; it cannot trade. Every command refuses a database that is
not a modeling database (the registered database is looked at read-only to be refused, and is never read from or written).

    python -m firm_lab.modeling.cli build   --source RESEARCH_DB --database MODELING_DB    # session-time copy of the sources (new file)
    python -m firm_lab.modeling.cli history --database MODELING_DB [--workers 2]          # unchanged Checkpoint 6 calculators, every session
    python -m firm_lab.modeling.cli dataset --database MODELING_DB                         # dataset manifest and hashes
    python -m firm_lab.modeling.cli run     --database MODELING_DB                         # the tournament, once
    python -m firm_lab.modeling.cli run     --database MODELING_DB --supersedes REPORT_ID --reason TEXT    # a rerun after a recorded defect
    python -m firm_lab.modeling.cli export  --database MODELING_DB --out LAB_DB            # the small read-only file the laboratory page reads
    python -m firm_lab.modeling.cli verify  --database MODELING_DB                         # the stored report was produced by this code

MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from firm_lab.research_features.store import CANONICAL_OFFICIAL

from . import DATABASE_ROLE, WARNING, timeview

EXPORTED = ('modeling_reports', 'modeling_models', 'modeling_datasets', 'modeling_runs')


def export(database, out) -> dict:
    """Copies the report, registry, dataset manifests and run records into a new small file. No feature rows, no predictions."""
    timeview.check(database)
    out = Path(out)
    if out.exists():
        raise ValueError('EXPORT_TARGET_EXISTS')
    if not out.parent.is_dir():
        raise ValueError('EXPORT_FOLDER_MISSING')
    if out.resolve() == Path(database).resolve() or CANONICAL_OFFICIAL.resolve().parent in out.resolve().parents:
        raise ValueError('EXPORT_TARGET_MUST_BE_SEPARATE')              # never beside the registered database
    src = sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)
    dst = sqlite3.connect(out)
    counts = {}
    try:
        with dst:
            timeview.create_tables(dst)
            dst.execute('CREATE TABLE firm_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)')
            for key, value, at in src.execute('SELECT key, value, updated_at FROM firm_meta'):
                dst.execute('INSERT INTO firm_meta VALUES (?,?,?)', (key, value, at))
            dst.execute('INSERT INTO firm_meta VALUES (?,?,?)', ('export', json.dumps({'of': DATABASE_ROLE, 'tables': list(EXPORTED),
                        'left_out': 'feature snapshots, time view, per-sample records and predictions'}), datetime.now(timezone.utc).isoformat()))
            for table in EXPORTED:
                rows = [r for r in src.execute(f'SELECT id, payload, created_at FROM {table}') if not r[0].endswith(':samples')]
                dst.executemany(f'INSERT INTO {table} VALUES (?,?,?)', rows)
                counts[table] = len(rows)
    finally:
        src.close()
        dst.close()
    timeview.check(out)
    return {'out': str(out), 'rows': counts, 'sha256': timeview.file_sha256(out)}


def verify(database) -> dict:
    """Whether the newest stored report, and every registry row of its run, was produced by the code in this tree."""
    from . import registry, tournament
    timeview.check(database)
    with registry.Registry(database) as store:
        report = store.latest_report()
        rows = store.models()
    if not report:
        raise ValueError('NO_STORED_REPORT')
    code = registry.code_hash()
    mine = [m for m in rows if m.get('report_id') == report['report_id']]
    problems = []
    if report['code_hash'] != code:
        problems.append('the stored report was produced by other code')
    if report['plan_version'] != tournament.PLAN_VERSION:
        problems.append('the stored report was produced under another plan version')
    if not mine or any(m['code_hash'] != code for m in mine):
        problems.append('registry rows of the run are missing or were produced by other code')
    return {'report_id': report['report_id'], 'report_code_hash': report['code_hash'], 'tree_code_hash': code, 'plan_version': report['plan_version'],
            'models_of_this_run': len(mine), 'models_of_other_runs': len(rows) - len(mine), 'matches': not problems, 'problems': problems}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['build', 'history', 'dataset', 'run', 'export', 'verify'])
    parser.add_argument('--supersedes')
    parser.add_argument('--reason')
    parser.add_argument('--source')
    parser.add_argument('--database', required=True)
    parser.add_argument('--out')
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--official-database')
    args = parser.parse_args(argv)
    try:
        if args.command == 'build':
            if not args.source:
                parser.error('build needs --source')
            kw = {'official_db': args.official_database} if args.official_database else {}
            out = timeview.build(args.source, args.database, **kw)
        elif args.command == 'history':
            from . import history
            out = history.generate(args.database, workers=args.workers)
        elif args.command == 'dataset':
            from . import dataset
            data = dataset.build(args.database)
            out = {'registered': dataset.register(args.database, data), **{k: data.manifest[k] for k in ('dataset_hash', 'hashes', 'rows', 'usable_samples_all_horizons',
                                                                                                         'usable_sessions_all_horizons', 'calculation_hash')}}
        elif args.command == 'run':
            from . import lab, report
            run = lab.Lab(args.database, log=lambda text: print(text, flush=True)).execute()
            if bool(args.supersedes) != bool(args.reason):
                parser.error('--supersedes and --reason go together')
            body = report.assemble(run, supersedes={'report_id': args.supersedes, 'reason': args.reason} if args.supersedes else None)
            out = {**report.write(run, body), 'warning': WARNING, 'fibonacci': body['ablation']['fibonacci']['statement'], 'seconds': body['seconds']}
        elif args.command == 'verify':
            out = verify(args.database)
            print(json.dumps(out, sort_keys=True, default=str))
            return 0 if out['matches'] else 2
        else:
            if not args.out:
                parser.error('export needs --out')
            out = export(args.database, args.out)
        print(json.dumps(out, sort_keys=True, default=str))
        return 0
    except (ValueError, sqlite3.Error) as error:
        print(json.dumps({'status': 'REJECTED', 'reason': str(error)[:300]}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
