"""Run the Phase 0 Robinhood diagnostic without inference or broker writes."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from broker.proxy_client import BrokerProxyClient
from broker.read_gateway import EffectiveReadGateway
from agents.preregistration import load_phase0_registration
from config.loader import load_config
from data.evidence import EvidenceCache


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='config/settings.local.yaml')
    parser.add_argument('--database', default='data/agent.db')
    parser.add_argument('--output', default='outputs/phase0-readonly-diagnostic.json')
    args = parser.parse_args()
    config = load_config(args.config)
    registration = load_phase0_registration(Path('preregistration.yaml'))
    database = Path(args.database).resolve()
    incidents: list[str] = []
    client = BrokerProxyClient(config.broker_proxy_socket)
    try:
        client.open()
        authorization = client.authorization_evidence()
        gateway = EffectiveReadGateway(
            client, config, incidents.append,
            lambda: datetime.now(timezone.utc),
            EvidenceCache(database.parent / 'evidence.db'),
            max_agentic_cash_usd=registration.max_agentic_cash_usd,
        )
        capability = gateway.preflight(scope_path=authorization['selected_path'])
        result = {
            'status': 'PASSED',
            'checked_at': datetime.now(timezone.utc).isoformat(),
            'inference_calls': 0,
            'broker_write_calls': 0,
            'authorization': authorization,
            'capability': capability,
            'incidents': incidents,
        }
        exit_code = 0
    except Exception as error:
        result = {
            'status': 'FAILED',
            'checked_at': datetime.now(timezone.utc).isoformat(),
            'error_type': type(error).__name__,
            'inference_calls': 0,
            'broker_write_calls': 0,
            'incidents': incidents,
        }
        exit_code = 2
    finally:
        client.close()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
