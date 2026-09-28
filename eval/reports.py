from __future__ import annotations

from pathlib import Path

from eval.scoreboard import Scoreboard


class WeeklyReport:
    def render(
        self,
        board: Scoreboard,
        *,
        holdings: str,
        calibration: str,
        biggest_wins: str,
        biggest_losses: str,
        rules_fired: str,
    ) -> str:
        return "\n".join(
            (
                "# Weekly shadow trading report",
                "",
                "## Scoreboard",
                "",
                board.to_markdown(),
                "",
                "## What the account holds and why",
                "",
                holdings,
                "",
                "## Confidence check",
                "",
                calibration,
                "",
                "## Biggest wins",
                "",
                biggest_wins,
                "",
                "## Biggest losses",
                "",
                biggest_losses,
                "",
                "## Rules that fired",
                "",
                rules_fired,
                "",
            )
        )

    def write(self, path: str | Path, board: Scoreboard, **sections: str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.render(board, **sections), encoding="utf-8")

