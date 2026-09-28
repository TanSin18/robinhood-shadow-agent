from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PhoenixSettings:
    host: str
    port: int
    working_dir: Path


def phoenix_settings(working_dir: str | Path) -> PhoenixSettings:
    return PhoenixSettings(
        host="127.0.0.1",
        port=6006,
        working_dir=Path(working_dir).resolve(),
    )


def main() -> int:
    import phoenix

    root = Path(__file__).parents[1]
    settings = phoenix_settings(root / "data" / "phoenix")
    settings.working_dir.mkdir(parents=True, exist_ok=True)
    os.environ["PHOENIX_WORKING_DIR"] = str(settings.working_dir)
    os.environ["PHOENIX_HOST"] = settings.host
    os.environ["PHOENIX_PORT"] = str(settings.port)
    session = phoenix.launch_app(
        run_in_thread=True,
        use_temp_dir=False,
    )
    if session is None:
        raise RuntimeError("Phoenix did not return a local session")
    print(f"Phoenix is available at {session.url}", flush=True)
    try:
        while session.active:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        session.end()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
