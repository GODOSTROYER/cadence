"""Cadence support agent: models, deterministic rules, prompts and the ``SupportAgent`` pipeline."""

from cadence.agent.models import AgentResponse, Escalation, EvidenceItem, LLMDecision, Trace, fit_reply
from cadence.agent.pipeline import SupportAgent
from cadence.agent.prompts import build_system_prompt, build_user_prompt, policy_block, taxonomy_block
from cadence.agent.rules import RuleResult, apply_rules

__all__ = [
    "AgentResponse",
    "Escalation",
    "EvidenceItem",
    "LLMDecision",
    "Trace",
    "fit_reply",
    "SupportAgent",
    "build_system_prompt",
    "build_user_prompt",
    "policy_block",
    "taxonomy_block",
    "RuleResult",
    "apply_rules",
]
