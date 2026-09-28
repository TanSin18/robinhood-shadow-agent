from pathlib import Path

from eval.golden import GoldenResult
from scripts.generate_samples import generate_samples
from scripts.regression_gate import RegressionGate

PASSING = (GoldenResult(id="safe", expected="blocked", observed="blocked", passed=True),)
FAILING = (GoldenResult(id="unsafe", expected="blocked", observed="allowed", passed=False),)


def test_regression_gate_passes_only_when_risk_and_golden_both_pass() -> None:
    gate = RegressionGate()

    assert gate.evaluate(risk_tests_passed=True, golden_results=PASSING).passed is True
    assert gate.evaluate(risk_tests_passed=False, golden_results=PASSING).passed is False
    assert gate.evaluate(risk_tests_passed=True, golden_results=FAILING).passed is False


def test_mocked_samples_include_local_trace_and_api_cost(tmp_path: Path) -> None:
    outputs = generate_samples(tmp_path)

    card = outputs.approval_card.read_text()
    scoreboard = outputs.scoreboard.read_text()
    assert "MOCKED SAMPLE" in card
    assert str((tmp_path/'sample_approval_trace.md').resolve()) in card
    assert (tmp_path/'sample_approval_trace.md').exists()
    assert 'not a Phoenix trace' in (tmp_path/'sample_approval_trace.md').read_text()
    assert "[YES] [NO]" in card
    assert "MOCKED SAMPLE" in scoreboard
    assert "API cost" in scoreboard
    assert "$0.40" in scoreboard
