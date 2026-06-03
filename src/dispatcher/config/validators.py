"""Dependency validation for agent configurations."""

from __future__ import annotations

import os

from config.models import AgentConfig, ConfigError, ModelsConfig
from config.loaders import load_agent_config
from config.parsers import parse_agent_ref, parse_skill_ref, parse_tool_ref
from skill_loader import validate_skill_frontmatter


def validate_agent_dependencies(
    config: AgentConfig,
    models_config: ModelsConfig,
    tools_base: str = "/app/tools",
    skills_base: str = "/app/skills",
    agents_base: str = "/app/agents",
) -> list[str]:
    """Validate that all external dependencies of an agent exist.

    Checks:
    - The referenced model exists in models_config.
    - Each tool has a ``tool.py`` file in the tools directory.
    - Each skill has a directory in the skills directory.
    - If swarm is configured, each sub-agent exists and does not
      define its own swarm (max 1 level of nesting).
    - If delegates is configured, each sub-agent exists and does not
      define its own swarm or delegates (max 1 level of nesting).

    Args:
        config: The agent configuration to validate.
        models_config: The loaded models configuration.
        tools_base: Base directory for tools.
        skills_base: Base directory for skills.
        agents_base: Base directory for agents.

    Returns:
        A list of error strings. An empty list means all dependencies are valid.
    """
    errors: list[str] = []

    # Check model exists
    if config.model not in models_config.models:
        errors.append(
            f"Modelo '{config.model}' no encontrado en models.yml"
        )

    # Check tools exist
    for tool_ref in config.tools:
        provider, tool_name = parse_tool_ref(tool_ref)
        if provider == "strands":
            continue
        tool_path = os.path.join(tools_base, provider, tool_name, "tool.py")
        if not os.path.isfile(tool_path):
            errors.append(
                f"Tool '{tool_ref}' no encontrada en {tool_path}"
            )

    # Check skills exist and have valid frontmatter
    for skill_ref in config.skills:
        provider, skill_name = parse_skill_ref(skill_ref)
        skill_dir = os.path.join(skills_base, provider, skill_name)
        if not os.path.isdir(skill_dir):
            errors.append(
                f"Skill '{skill_ref}' no encontrada en {skill_dir}"
            )
            continue

        # Deep validation: SKILL.md existence, frontmatter, name match
        skill_errors = validate_skill_frontmatter(skill_dir)
        for se in skill_errors:
            errors.append(f"Skill '{skill_ref}': {se}")

    # Check swarm sub-agents
    if config.swarm:
        seen_refs: set[str] = set()
        for agent_ref in config.swarm.agents:
            if agent_ref in seen_refs:
                errors.append(
                    f"Swarm: agente '{agent_ref}' referenciado más de una vez"
                )
                continue
            seen_refs.add(agent_ref)

            provider, agent_name = parse_agent_ref(agent_ref)
            agent_dir = os.path.join(agents_base, provider, agent_name)
            config_path = os.path.join(agent_dir, "agent.yml")
            if not os.path.isfile(config_path):
                errors.append(
                    f"Swarm: agente '{agent_ref}' no encontrado en {agent_dir}"
                )
                continue

            try:
                sub_config = load_agent_config(agent_dir)
                if sub_config.swarm is not None:
                    errors.append(
                        f"Swarm: agente '{agent_ref}' define su propio swarm. "
                        "Anidamiento de swarms no permitido (máximo 1 nivel)."
                    )
            except ConfigError as exc:
                errors.append(
                    f"Swarm: error cargando config de '{agent_ref}': {exc}"
                )

        # Validate entry_point reference
        if config.swarm.entry_point != "self":
            if config.swarm.entry_point not in seen_refs:
                errors.append(
                    f"Swarm: entry_point '{config.swarm.entry_point}' no está "
                    "en la lista de agentes del swarm"
                )

    # Check delegate sub-agents
    if config.delegates:
        seen_delegate_refs: set[str] = set()
        # Collect orchestrator tool names to detect collisions
        orchestrator_tool_names: set[str] = set()
        for tool_ref in config.tools:
            _, tool_name = parse_tool_ref(tool_ref)
            orchestrator_tool_names.add(tool_name.replace("-", "_"))

        for agent_ref in config.delegates.agents:
            if agent_ref in seen_delegate_refs:
                errors.append(
                    f"Delegates: agente '{agent_ref}' referenciado más de una vez"
                )
                continue
            seen_delegate_refs.add(agent_ref)

            provider, agent_name = parse_agent_ref(agent_ref)
            agent_dir = os.path.join(agents_base, provider, agent_name)
            config_path = os.path.join(agent_dir, "agent.yml")
            if not os.path.isfile(config_path):
                errors.append(
                    f"Delegates: agente '{agent_ref}' no encontrado en {agent_dir}"
                )
                continue

            # Check tool name collision
            delegate_tool_name = agent_name.replace("-", "_")
            if delegate_tool_name in orchestrator_tool_names:
                errors.append(
                    f"Delegates: nombre de tool '{delegate_tool_name}' del agente "
                    f"'{agent_ref}' colisiona con una tool del orquestador"
                )

            try:
                sub_config = load_agent_config(agent_dir)
                if sub_config.swarm is not None:
                    errors.append(
                        f"Delegates: agente '{agent_ref}' define un swarm. "
                        "Sub-agentes delegados no pueden tener swarm."
                    )
                if sub_config.delegates is not None:
                    errors.append(
                        f"Delegates: agente '{agent_ref}' define sus propios delegates. "
                        "Anidamiento de delegates no permitido (máximo 1 nivel)."
                    )
            except ConfigError as exc:
                errors.append(
                    f"Delegates: error cargando config de '{agent_ref}': {exc}"
                )

    return errors
