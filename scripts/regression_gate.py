from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from eval.golden import GoldenGate, GoldenResult


@dataclass(frozen=True)
class GateVerdict:
    passed: bool
    risk_tests_passed: bool
    golden_passed: int
    golden_total: int
    failed_scenarios: tuple[str, ...]


class RegressionGate:
    def evaluate(
        self,
        *,
        risk_tests_passed: bool,
        golden_results: tuple[GoldenResult, ...],
    ) -> GateVerdict:
        failed = tuple(item.id for item in golden_results if not item.passed)
        return GateVerdict(
            passed=risk_tests_passed and not failed,
            risk_tests_passed=risk_tests_passed,
            golden_passed=len(golden_results) - len(failed),
            golden_total=len(golden_results),
            failed_scenarios=failed,
        )


def main() -> int:
    root = Path(__file__).parents[1]
    risk = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_risk_engine.py", "-q"],
        cwd=root,
        check=False,
    )
    golden = GoldenGate.load(root / "tests/fixtures/golden_scenarios.yaml").run()
    verdict = RegressionGate().evaluate(
        risk_tests_passed=risk.returncode == 0,
        golden_results=golden,
    )
    print(
        f"regression gate: {'PASS' if verdict.passed else 'FAIL'}; "
        f"risk={'PASS' if verdict.risk_tests_passed else 'FAIL'}; "
        f"golden={verdict.golden_passed}/{verdict.golden_total}"
    )
    if verdict.failed_scenarios:
        print("failed golden scenarios: " + ", ".join(verdict.failed_scenarios))
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

