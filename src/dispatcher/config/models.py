"""Pydantic configuration models and custom exceptions."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, field_validator, model_validator


# ---------------------------------------------------------------------------
# Pydantic configuration models
# ---------------------------------------------------------------------------


class ModelConfig(BaseModel):
    """Single LLM model entry from models.yml."""

    provider: str
    model_id: str
    host: str | None = None  # For ollama (e.g. http://ollama:11434) or openai (api_base)
    region_name: str | None = None  # For bedrock (AWS region, e.g. us-east-1)
    temperature: float = 0.7
    max_tokens: int = 4096


class SwarmDefaults(BaseModel):
    """Global safety defaults for multi-agent swarms (from models.yml)."""

    max_handoffs: int = 20
    max_iterations: int = 20
    execution_timeout: float = 900.0
    node_timeout: float = 300.0
    repetitive_handoff_detection_window: int = 0
    repetitive_handoff_min_unique_agents: int = 0


class ModelsConfig(BaseModel):
    """Top-level models.yml schema."""

    models: dict[str, ModelConfig]
    swarm_defaults: SwarmDefaults = SwarmDefaults()


class SwarmConfig(BaseModel):
    """Swarm section of an agent.yml — defines a multi-agent swarm."""

    agents: list[str]  # References to other agents (format: "provider:name")
    entry_point: str = "self"  # "self" or an agent ref like "custom:writer"

    # Safety overrides (None means use global default from swarm_defaults)
    max_handoffs: int | None = None
    max_iterations: int | None = None
    execution_timeout: float | None = None
    node_timeout: float | None = None
    repetitive_handoff_detection_window: int | None = None
    repetitive_handoff_min_unique_agents: int | None = None

    @field_validator("agents")
    @classmethod
    def agents_not_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("swarm.agents must contain at least one agent reference")
        return v

    def resolve_defaults(self, defaults: SwarmDefaults) -> dict:
        """Merge agent-level overrides with global swarm defaults.

        Returns a dict with all 6 safety parameters resolved.
        """
        return {
            "max_handoffs": self.max_handoffs if self.max_handoffs is not None else defaults.max_handoffs,
            "max_iterations": self.max_iterations if self.max_iterations is not None else defaults.max_iterations,
            "execution_timeout": self.execution_timeout if self.execution_timeout is not None else defaults.execution_timeout,
            "node_timeout": self.node_timeout if self.node_timeout is not None else defaults.node_timeout,
            "repetitive_handoff_detection_window": self.repetitive_handoff_detection_window if self.repetitive_handoff_detection_window is not None else defaults.repetitive_handoff_detection_window,
            "repetitive_handoff_min_unique_agents": self.repetitive_handoff_min_unique_agents if self.repetitive_handoff_min_unique_agents is not None else defaults.repetitive_handoff_min_unique_agents,
        }


class DelegatesConfig(BaseModel):
    """Delegates section of an agent.yml — sub-agents injected as tools."""

    agents: list[str]  # References to sub-agents (format: "provider:name")

    @field_validator("agents")
    @classmethod
    def agents_not_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("delegates.agents must contain at least one agent reference")
        return v


class AgentConfig(BaseModel):
    """Schema for agents/{provider}/{name}/agent.yml (unwrapped)."""

    display_name: str = ""
    description: str = ""
    tags: list[str] = []
    status: Literal["active", "inactive", "internal"] = "active"
    system_prompt: str
    model: str  # reference to a key in models.yml
    tools: list[str] = []
    skills: list[str] = []
    max_turns: int = 10
    timeout_seconds: int = 300
    swarm: SwarmConfig | None = None  # Optional swarm section for multi-agent
    delegates: DelegatesConfig | None = None  # Optional delegates (agents as tools)

    @field_validator("system_prompt")
    @classmethod
    def system_prompt_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("system_prompt must not be empty")
        return v

    @field_validator("model")
    @classmethod
    def model_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("model must not be empty")
        return v

    @model_validator(mode="after")
    def swarm_delegates_exclusive(self) -> AgentConfig:
        if self.swarm is not None and self.delegates is not None:
            raise ValueError(
                "Un agente no puede tener 'swarm' y 'delegates' al mismo tiempo. "
                "Usa 'swarm' para orquestacion colaborativa entre pares, o "
                "'delegates' para delegacion con control centralizado."
            )
        return self


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class ConfigError(Exception):
    """Raised when a configuration file is missing or invalid."""


class ModelNotFoundError(ConfigError):
    """Raised when a model reference cannot be resolved in models.yml."""


class ToolNotFoundError(ConfigError):
    """Raised when a tool directory/file does not exist."""


class SkillNotFoundError(ConfigError):
    """Raised when a skill directory does not exist."""
