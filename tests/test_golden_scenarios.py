from pathlib import Path

from eval.golden import GoldenGate

FIXTURE = Path(__file__).parent / "fixtures" / "golden_scenarios.yaml"


def test_all_twenty_four_golden_scenarios_pass() -> None:
    gate = GoldenGate.load(FIXTURE)

    results = gate.run()

    assert len(results) == 24
    assert all(result.passed for result in results)


def test_required_adverse_scenarios_are_present() -> None:
    ids = {scenario.id for scenario in GoldenGate.load(FIXTURE).scenarios}

    assert {
        "stale_data",
        "injected_news_instruction",
        "earnings_gap",
        "drawdown_breaker_trip",
        "option_near_expiry",
        "halted_ticker",
        "duplicate_signal",
        "api_timeout",
    } <= ids

