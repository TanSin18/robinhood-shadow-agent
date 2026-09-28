from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


def _money(value: Decimal) -> str:
    return f"${value.quantize(Decimal('0.01')):,.2f}"


@dataclass(frozen=True)
class ScoreboardInputs:
    starting_cash: Decimal
    agent_alone_gross_pnl: Decimal
    approved_gross_pnl: Decimal
    vti_gross_pnl: Decimal
    agent_alone_non_api_costs: Decimal
    approved_non_api_costs: Decimal
    api_cost: Decimal


@dataclass(frozen=True)
class ScoreboardLine:
    name: str
    net_value: Decimal
    net_pnl: Decimal
    api_cost: Decimal
    summary: str


@dataclass(frozen=True)
class Scoreboard:
    agent_alone: ScoreboardLine
    with_approvals: ScoreboardLine
    vti: ScoreboardLine
    cash: ScoreboardLine

    @property
    def lines(self) -> tuple[ScoreboardLine, ...]:
        return (self.agent_alone, self.with_approvals, self.vti, self.cash)

    def to_markdown(self) -> str:
        rows = ["| Track | Net value | Net result | API cost |", "|---|---:|---:|---:|"]
        for line in self.lines:
            rows.append(
                f"| {line.name} | {_money(line.net_value)} | {_money(line.net_pnl)} | {_money(line.api_cost)} |"
            )
        rows.extend(["", *(line.summary for line in self.lines)])
        return "\n".join(rows)


def build_scoreboard(values: ScoreboardInputs) -> Scoreboard:
    def line(name: str, gross_pnl: Decimal, non_api: Decimal, *, agent: bool = True) -> ScoreboardLine:
        api_cost = values.api_cost if agent else Decimal('0')
        net_pnl = gross_pnl - non_api - api_cost
        net_value = values.starting_cash + net_pnl
        direction = "up" if net_pnl >= 0 else "down"
        return ScoreboardLine(
            name=name,
            net_value=net_value,
            net_pnl=net_pnl,
            api_cost=api_cost,
            summary=(
                (f"After paying {_money(api_cost)} in AI costs, " if agent else "") + f"{name.lower()} "
                f"is {direction} {_money(abs(net_pnl))}."
            ),
        )

    return Scoreboard(
        agent_alone=line(
            "Agent alone", values.agent_alone_gross_pnl, values.agent_alone_non_api_costs
        ),
        with_approvals=line(
            "Agent + my approvals", values.approved_gross_pnl, values.approved_non_api_costs
        ),
        vti=line("Starting cash held in VTI", values.vti_gross_pnl, Decimal("0"), agent=False),
        cash=line("Starting cash held in cash", Decimal("0"), Decimal("0"), agent=False),
    )
