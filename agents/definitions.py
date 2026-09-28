from __future__ import annotations

from dataclasses import dataclass

from agents.agent import Agent
from agents.schemas import CriticOutput, ResearchPacket, TradeProposal
from prompts.registry import PromptRegistry


@dataclass(frozen=True)
class AgentBundle:
    research: Agent
    portfolio: Agent
    critic: Agent


def build_agents(registry: PromptRegistry, *, model_name: str = 'gpt-5.6-terra', research_model_name: str | None = None, portfolio_model_name: str | None = None, critic_model_name: str | None = None) -> AgentBundle:
    research_prompt = registry.load("research", "v1")
    portfolio_prompt = registry.load("portfolio", "v1")
    critic_prompt = registry.load("critic", "v1")
    return AgentBundle(
        research=Agent(
            name="Research Agent",
            instructions=research_prompt.text,
            model=research_model_name or model_name,
            output_type=ResearchPacket,
        ),
        portfolio=Agent(
            name="Portfolio Agent",
            instructions=portfolio_prompt.text,
            model=portfolio_model_name or model_name,
            output_type=TradeProposal,
        ),
        critic=Agent(
            name="Critic",
            instructions=critic_prompt.text,
            model=critic_model_name or model_name,
            output_type=CriticOutput,
        ),
    )
