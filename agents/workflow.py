from __future__ import annotations

import json
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from agents.definitions import AgentBundle
from agents.schemas import CriticOutput, ResearchPacket, TradeProposal
from data.store import SQLiteStore


class LowLevelRunner(Protocol):
    def run(self, agent: object, prompt: str) -> object: ...


T = TypeVar("T", bound=BaseModel)


class ValidatedAgentRunner:
    def __init__(self, runner: LowLevelRunner, store: SQLiteStore) -> None:
        self.runner = runner
        self.store = store

    def run_typed(
        self,
        agent: object,
        prompt: str,
        schema: type[T],
        *,
        prompt_version: str,
    ) -> T | None:
        last_raw: object = None
        for attempt in range(2):
            request = prompt
            if attempt:
                request += (
                    "\n\nYour prior output failed schema validation. Return only a complete "
                    "JSON object matching the configured output schema. Never guess missing fields."
                )
            last_raw = self.runner.run(agent, request)
            try:
                if isinstance(last_raw, schema):
                    return last_raw
                return schema.model_validate(last_raw)
            except ValidationError:
                continue
        self.store.record_validation_failure(
            getattr(agent, "name", "unknown"),
            prompt_version,
            json.dumps(last_raw, sort_keys=True, default=str),
        )
        return None


class TradingWorkflow:
    def __init__(self, agents: AgentBundle, runner: ValidatedAgentRunner) -> None:
        self.agents = agents
        self.runner = runner

    def run(self, research_request: str) -> TradeProposal | None:
        research = self.runner.run_typed(
            self.agents.research,
            research_request,
            ResearchPacket,
            prompt_version="research_v1",
        )
        if research is None:
            return None
        proposal = self.runner.run_typed(
            self.agents.portfolio,
            "Create a proposal from this point-in-time research:\n" + research.model_dump_json(),
            TradeProposal,
            prompt_version="portfolio_v1",
        )
        if proposal is None:
            return None
        critic = self.runner.run_typed(
            self.agents.critic,
            "Write the strongest case against this proposal:\n" + proposal.model_dump_json(),
            CriticOutput,
            prompt_version="critic_v1",
        )
        if critic is None or critic.proposal_id != proposal.proposal_id:
            return None
        return proposal.model_copy(
            update={"critic_counterargument": critic.counterargument}
        )


class OpenAIAgentsSDKRunner:
    """Thin sync adapter used only when an API-backed run is explicitly started."""

    def run(self, agent: object, prompt: str) -> Any:
        from agents.run import Runner

        return Runner.run_sync(agent, prompt).final_output

