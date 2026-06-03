"""Reference parsers and hash utilities for agent configuration."""

from __future__ import annotations

import hashlib


def parse_agent_ref(agent_ref: str) -> tuple[str, str]:
    """Parse an agent reference into (provider, agent_name).

    Used for swarm sub-agent references in agent.yml.

    Supported formats:
    - ``"custom:writer"``     → ``("custom", "writer")``
    - ``"acme:code-reviewer"``→ ``("acme", "code-reviewer")``

    Args:
        agent_ref: Agent reference string (``"provider:name"``).

    Returns:
        Tuple of (provider, agent_name).

    Raises:
        ValueError: If the reference does not contain a provider prefix.
    """
    if ":" not in agent_ref:
        raise ValueError(
            f"Agente '{agent_ref}' no tiene proveedor. "
            f"Usa el formato 'proveedor:nombre' (ej: 'custom:{agent_ref}')."
        )
    provider, _, name = agent_ref.partition(":")
    return provider.strip(), name.strip()


def parse_skill_ref(skill_ref: str) -> tuple[str, str]:
    """Parse a skill reference into (provider, skill_name).

    All skill references must include a provider prefix.

    Supported formats:
    - ``"writer:chef"``  → ``("writer", "chef")``
    - ``"custom:my-skill"``      → ``("custom", "my-skill")``

    Args:
        skill_ref: Skill reference string from agent.yml (``"provider:name"``).

    Returns:
        Tuple of (provider, skill_name).

    Raises:
        ValueError: If the reference does not contain a provider prefix.
    """
    if ":" not in skill_ref:
        raise ValueError(
            f"Skill '{skill_ref}' no tiene proveedor. "
            f"Usa el formato 'proveedor:nombre' (ej: 'user:{skill_ref}')."
        )
    provider, _, name = skill_ref.partition(":")
    return provider.strip(), name.strip()


def parse_tool_ref(tool_ref: str) -> tuple[str, str]:
    """Parse a tool reference into (provider, tool_name).

    All tool references must include a provider prefix.

    Supported formats:
    - ``"user:calculator"``     → ``("user", "calculator")``
    - ``"strands:shell"``       → ``("strands", "shell")``
    - ``"custom:my_tool"``      → ``("custom", "my_tool")``

    Args:
        tool_ref: Tool reference string from agent.yml (``"provider:name"``).

    Returns:
        Tuple of (provider, tool_name).

    Raises:
        ValueError: If the reference does not contain a provider prefix.
    """
    if ":" not in tool_ref:
        raise ValueError(
            f"Tool '{tool_ref}' no tiene proveedor. "
            f"Usa el formato 'proveedor:nombre' (ej: 'user:{tool_ref}', "
            f"'strands:{tool_ref}')."
        )
    provider, _, name = tool_ref.partition(":")
    return provider.strip(), name.strip()


def compute_config_hash(agent_yml_path: str) -> str:
    """Compute the SHA-256 hash of an agent.yml file.

    Args:
        agent_yml_path: Absolute or relative path to the agent.yml file.

    Returns:
        Hex-encoded SHA-256 digest.
    """
    with open(agent_yml_path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()
