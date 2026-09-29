"""Load the frozen runtime plus this UI-only overlay; never copy runtime code."""
import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    root = args.runtime_root.resolve()
    ui = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    import agents
    agents.__path__.append(str(ui/'agents'))
    from agents.desk.frontdoor import make_server
    from agents.inbox import PaperInbox
    from agents.inbox_web import scheduler_loaded
    from agents.notifications import configured_notifiers
    from agents.readiness import OperationalProof
    from config.loader import load_config
    config_path = root/'config/settings.local.yaml'
    database = root/'data/agent.db'
    config = load_config(config_path)
    proof = OperationalProof(root=root, config_path=config_path, database=database,
        test_report=root/'outputs/operational-test-results.xml', test_manifest=root/'outputs/operational-test-run.json')
    with make_server(PaperInbox(database,config), args.port, proof=proof,
            service_check=scheduler_loaded, notification_channels=configured_notifiers(config,include_macos=False)) as server:
        server.serve_forever()


if __name__ == '__main__':
    main()
