"""Pluggable Agent Brain Bridge — connect Antigravity, OpenCode, Claude Code, Codex, and ACP agents."""

from .base import (
    AgentBrain,
    BrainCallbacks,
    BrainTurnResult,
    create_brain,
    discover_local_agents,
    extract_meet_agent_ops,
)

__all__ = [
    "AgentBrain",
    "BrainCallbacks",
    "BrainTurnResult",
    "create_brain",
    "discover_local_agents",
    "extract_meet_agent_ops",
]
