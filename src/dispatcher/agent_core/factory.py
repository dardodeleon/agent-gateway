"""Agent factory — dynamically creates Strands agents from configuration.

Given an AgentConfig (loaded from agent.yml) and the global ModelsConfig,
this module resolves the LLM model, loads tools via importlib, reads skill
files, builds the final system prompt, and returns a ready-to-run Strands
Agent instance.  Also supports creating Strands Swarms for multi-agent
orchestration.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from typing import Any

from strands import Agent, tool
from strands.multiagent import Swarm

from config import (
    AgentConfig,
    ModelsConfig,
    ToolNotFoundError,
    SkillNotFoundError,
    ConfigError,
    parse_tool_ref,
    parse_skill_ref,
    parse_agent_ref,
    load_agent_config,
)
from skill_loader import (
    SkillMetadata,
    load_skill_metadata,
    generate_skills_catalog,
    create_skill_tools,
)
from agent_core.model_resolver import resolve_model
from shared.telemetry import get_tracer

logger = logging.getLogger("[DISPATCHER]")


class AgentFactory:
    """Create Strands Agent and Swarm instances from declarative YAML configuration."""

    def __init__(
        self,
        models_config: ModelsConfig,
        tools_base: str = "/app/tools",
        skills_base: str = "/app/skills",
        agents_base: str = "/app/agents",
    ) -> None:
        self.models_config = models_config
        self.tools_base = tools_base
        self.skills_base = skills_base
        self.agents_base = agents_base

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_agent(
        self,
        agent_config: AgentConfig,
        extra_tools: list[Any] | None = None,
    ) -> Agent:
        """Create a fully configured Strands Agent.

        Args:
            agent_config: Validated agent configuration.
            extra_tools: Additional tools to inject (e.g. delegate tools).

        Returns:
            A Strands ``Agent`` ready to be invoked.

        Raises:
            ModelNotFoundError: If the referenced model is not in models.yml.
            ToolNotFoundError: If a referenced tool cannot be loaded.
            SkillNotFoundError: If a referenced skill directory is missing.
        """
        tracer = get_tracer("dispatcher.agent_factory")

        with tracer.start_as_current_span(
            "agent.create",
            attributes={
                "agent.model": agent_config.model,
                "agent.tools_count": len(agent_config.tools),
                "agent.skills_count": len(agent_config.skills),
            },
        ):
            # 1. Resolve model
            model = resolve_model(agent_config.model, self.models_config)

            # 2. Load tools
            tools = self._load_tools(agent_config.tools)
            if extra_tools:
                tools.extend(extra_tools)

            # 3. Load skill metadata, build prompt with catalog, inject tools
            skill_metas = self._load_skill_metas(agent_config.skills)

            system_prompt = self._build_system_prompt(
                agent_config.system_prompt, skill_metas
            )

            if skill_metas:
                skill_tools = create_skill_tools(skill_metas)
                tools.extend(skill_tools)
                logger.debug(
                    "Injected %d skill tool(s)",
                    len(skill_tools),
                )

            # 4. Create Strands agent
            agent = Agent(
                model=model,
                system_prompt=system_prompt,
                tools=tools if tools else None,
            )

            logger.info(
                "Created agent with model='%s', %d tool(s), %d skill(s)",
                agent_config.model,
                len(tools),
                len(agent_config.skills),
            )
            return agent

    def create_swarm(
        self,
        agent_config: AgentConfig,
        parent_provider: str = "",
        parent_name: str = "",
    ) -> Swarm:
        """Create a Strands Swarm from an agent config that has a ``swarm:`` section.

        The parent agent (``agent_config``) becomes a node in the swarm.
        Each sub-agent referenced in ``swarm.agents`` is loaded from its
        own ``agent.yml`` and added as a peer node.

        Args:
            agent_config: Validated agent configuration with a swarm section.
            parent_provider: Provider of the parent agent (for naming).
            parent_name: Name of the parent agent (for naming).

        Returns:
            A Strands ``Swarm`` ready to be invoked.

        Raises:
            ConfigError: If a sub-agent cannot be loaded.
            ModelNotFoundError: If a referenced model is not in models.yml.
        """
        if agent_config.swarm is None:
            raise ConfigError("Agent config does not have a swarm section")

        tracer = get_tracer("dispatcher.agent_factory")
        swarm_cfg = agent_config.swarm

        with tracer.start_as_current_span(
            "swarm.create",
            attributes={
                "swarm.parent": f"{parent_provider}/{parent_name}",
                "swarm.sub_agents_count": len(swarm_cfg.agents),
            },
        ):
            # 1. Create the parent agent (the orchestrator node)
            parent_agent = self.create_agent(agent_config)
            parent_agent.name = parent_name or "orchestrator"

            # 2. Create each sub-agent
            nodes: list[Agent] = [parent_agent]
            agent_map: dict[str, Agent] = {"self": parent_agent}

            for agent_ref in swarm_cfg.agents:
                provider, name = parse_agent_ref(agent_ref)
                agent_dir = os.path.join(self.agents_base, provider, name)

                try:
                    sub_config = load_agent_config(agent_dir)
                except ConfigError as exc:
                    raise ConfigError(
                        f"Error cargando sub-agente '{agent_ref}': {exc}"
                    ) from exc

                sub_agent = self.create_agent(sub_config)
                sub_agent.name = name

                nodes.append(sub_agent)
                agent_map[agent_ref] = sub_agent

                logger.info(
                    "Swarm: loaded sub-agent '%s' (model=%s, tools=%d)",
                    agent_ref,
                    sub_config.model,
                    len(sub_config.tools),
                )

            # 3. Determine entry point
            if swarm_cfg.entry_point == "self":
                entry = parent_agent
            else:
                entry = agent_map.get(swarm_cfg.entry_point)
                if entry is None:
                    raise ConfigError(
                        f"Swarm entry_point '{swarm_cfg.entry_point}' not found"
                    )

            # 4. Resolve safety parameters (agent overrides + global defaults)
            safety = swarm_cfg.resolve_defaults(self.models_config.swarm_defaults)

            # 5. Build the Swarm
            # https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/swarm/
            swarm = Swarm(
                nodes,
                entry_point=entry,
                max_handoffs=safety["max_handoffs"],
                max_iterations=safety["max_iterations"],
                execution_timeout=safety["execution_timeout"],
                node_timeout=safety["node_timeout"],
                # prevent ping-pong behavior, minimum number of agents at a handrail window
                repetitive_handoff_detection_window=safety["repetitive_handoff_detection_window"],
                repetitive_handoff_min_unique_agents=safety["repetitive_handoff_min_unique_agents"],
            )

            logger.info(
                "Created swarm for '%s/%s' with %d nodes (entry=%s, max_handoffs=%d, timeout=%.0fs)",
                parent_provider,
                parent_name,
                len(nodes),
                entry.name,
                safety["max_handoffs"],
                safety["execution_timeout"],
            )
            return swarm

    def create_agent_with_delegates(
        self,
        agent_config: AgentConfig,
        parent_provider: str = "",
        parent_name: str = "",
    ) -> Agent:
        """Create an Agent with sub-agents injected as tool functions.

        Each delegate referenced in ``delegates.agents`` is loaded from its
        own ``agent.yml``, wrapped as a ``@tool`` function, and added to
        the orchestrator's tool list.  The orchestrator is a regular
        ``Agent`` (not a ``Swarm``), so it maintains full control.

        Args:
            agent_config: Validated agent configuration with a delegates section.
            parent_provider: Provider of the orchestrator agent.
            parent_name: Name of the orchestrator agent.

        Returns:
            A Strands ``Agent`` with delegate tools in its tools list.

        Raises:
            ConfigError: If a delegate cannot be loaded.
            ModelNotFoundError: If a referenced model is not in models.yml.
        """
        if agent_config.delegates is None:
            raise ConfigError("Agent config does not have a delegates section")

        tracer = get_tracer("dispatcher.agent_factory")
        delegates_cfg = agent_config.delegates

        with tracer.start_as_current_span(
            "delegates.create",
            attributes={
                "delegates.parent": f"{parent_provider}/{parent_name}",
                "delegates.count": len(delegates_cfg.agents),
            },
        ):
            # 1. Build delegate tool functions
            delegate_tools: list[Any] = []
            for agent_ref in delegates_cfg.agents:
                provider, name = parse_agent_ref(agent_ref)
                agent_dir = os.path.join(self.agents_base, provider, name)

                try:
                    sub_config = load_agent_config(agent_dir)
                except ConfigError as exc:
                    raise ConfigError(
                        f"Error cargando delegado '{agent_ref}': {exc}"
                    ) from exc

                delegate_tool = self._create_delegate_tool(
                    delegate_name=name,
                    delegate_config=sub_config,
                    parent_provider=parent_provider,
                    parent_name=parent_name,
                )
                delegate_tools.append(delegate_tool)

                logger.info(
                    "Delegates: created tool for '%s' (model=%s, tools=%d)",
                    agent_ref,
                    sub_config.model,
                    len(sub_config.tools),
                )

            # 2. Create orchestrator with extra delegate tools
            orchestrator = self.create_agent(
                agent_config, extra_tools=delegate_tools
            )

            logger.info(
                "Created orchestrator '%s/%s' with %d delegate(s)",
                parent_provider,
                parent_name,
                len(delegate_tools),
            )
            return orchestrator

    def _create_delegate_tool(
        self,
        delegate_name: str,
        delegate_config: AgentConfig,
        parent_provider: str,
        parent_name: str,
    ) -> Any:
        """Wrap a sub-agent as a @tool function for delegation.

        Uses the closure factory pattern (same as skill_loader.create_skill_tools)
        to ensure the function name and docstring are set before ``@tool``
        processes them.
        """
        from shared.agent_context import get_agent_identity, set_agent_identity

        # Create the sub-agent eagerly (at orchestrator build time)
        sub_agent = self.create_agent(delegate_config)

        # Derive valid Python identifier for the tool name
        tool_fn_name = delegate_name.replace("-", "_")
        description = (
            delegate_config.description
            or f"Delegar tarea al agente {delegate_name}"
        )

        # Closure factory: set function metadata before @tool decoration
        def _make_delegate(fn_name, desc, agent, del_name, p_provider, p_name):
            def delegate_fn(query: str) -> str:
                """Placeholder docstring replaced below."""
                try:
                    set_agent_identity(p_provider, del_name)
                    result = agent(query)
                    return str(result)
                except Exception as exc:
                    logger.error(
                        "Delegate '%s' failed: %s",
                        del_name,
                        exc,
                        exc_info=True,
                    )
                    return f"Error en delegado '{del_name}': {exc}"
                finally:
                    set_agent_identity(p_provider, p_name)

            delegate_fn.__name__ = fn_name
            delegate_fn.__qualname__ = fn_name
            delegate_fn.__doc__ = desc
            return tool(delegate_fn)

        return _make_delegate(
            tool_fn_name,
            description,
            sub_agent,
            delegate_name,
            parent_provider,
            parent_name,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_tools(self, tool_refs: list[str]) -> list[Any]:
        """Dynamically load tools by reference.

        All references must include a provider prefix:
        - ``"user:calculator"``   — local tool from ``/tools/user/calculator/tool.py``
        - ``"strands:shell"``     — import from ``strands_tools`` package
        - ``"custom:my_tool"``    — local tool from ``/tools/custom/my_tool/tool.py``
        """
        loaded: list[Any] = []
        for ref in tool_refs:
            provider, tool_name = parse_tool_ref(ref)

            if provider == "strands":
                tool_fn = self._load_strands_tool(tool_name)
                loaded.append(tool_fn)
                logger.debug("Loaded strands tool '%s'", tool_name)
            else:
                tool_path = os.path.join(
                    self.tools_base, provider, tool_name, "tool.py"
                )
                if not os.path.isfile(tool_path):
                    raise ToolNotFoundError(
                        f"Tool '{ref}' no encontrada en {tool_path}"
                    )
                tool_fn = self._import_tool(tool_name, tool_path)
                loaded.append(tool_fn)
                logger.debug(
                    "Loaded tool '%s' from provider '%s' at %s",
                    tool_name, provider, tool_path,
                )

        return loaded

    @staticmethod
    def _load_strands_tool(tool_name: str) -> Any:
        """Import a tool from the ``strands_tools`` package.

        Tries two strategies:
        1. ``from strands_tools import {tool_name}``
        2. ``from strands_tools.{tool_name} import {tool_name}``
           (for tools in submodules like ``tavily_search``)
        """
        import importlib

        # Strategy 1: top-level attribute
        try:
            mod = importlib.import_module("strands_tools")
            if hasattr(mod, tool_name):
                return getattr(mod, tool_name)
        except ImportError:
            pass

        # Strategy 2: submodule
        try:
            sub = importlib.import_module(f"strands_tools.{tool_name}")
            if hasattr(sub, tool_name):
                return getattr(sub, tool_name)
        except ImportError:
            pass

        raise ToolNotFoundError(
            f"Tool 'strands:{tool_name}' no encontrada en el paquete "
            "strands_tools. Verifica que el nombre sea correcto y que "
            "strands-agents-tools esté instalado."
        )

    @staticmethod
    def _import_tool(tool_name: str, tool_path: str) -> Any:
        """Import a single tool module and find the decorated tool function.

        The module is expected to contain at least one callable decorated
        with ``@tool`` from ``strands``.  We look for the
        ``tool_name`` attribute that Strands adds, or fall back to any
        callable with tool-related metadata.
        """
        spec = importlib.util.spec_from_file_location(
            f"tools.{tool_name}", tool_path
        )
        if spec is None or spec.loader is None:
            raise ToolNotFoundError(
                f"Cannot create import spec for tool '{tool_name}' at {tool_path}"
            )

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Strategy 1: look for an exported TOOL variable
        if hasattr(module, "TOOL"):
            return module.TOOL

        # Strategy 2: find callables with Strands @tool metadata
        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue
            attr = getattr(module, attr_name)
            if callable(attr) and hasattr(attr, "tool_name"):
                return attr

        # Strategy 3: find any callable with __tool_metadata__ or similar
        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue
            attr = getattr(module, attr_name)
            if callable(attr) and (
                hasattr(attr, "__tool_metadata__")
                or hasattr(attr, "tool_spec")
                or hasattr(attr, "TOOL_SPEC")
            ):
                return attr

        raise ToolNotFoundError(
            f"No se encontró una tool válida en {tool_path}. "
            "El archivo debe exportar una función decorada con @tool "
            "o una variable TOOL."
        )

    def _load_skill_metas(
        self, skill_refs: list[str]
    ) -> list[SkillMetadata]:
        """Load and validate SkillMetadata for each skill reference."""
        metas: list[SkillMetadata] = []
        for skill_ref in skill_refs:
            provider, skill_name = parse_skill_ref(skill_ref)
            skill_dir = os.path.join(self.skills_base, provider, skill_name)
            if not os.path.isdir(skill_dir):
                raise SkillNotFoundError(
                    f"Skill '{skill_ref}' no encontrada en {skill_dir}"
                )
            try:
                meta = load_skill_metadata(skill_dir)
                metas.append(meta)
            except (FileNotFoundError, ValueError) as exc:
                raise SkillNotFoundError(
                    f"Skill '{skill_ref}' inválida: {exc}"
                ) from exc
        return metas

    def _build_system_prompt(
        self, base_prompt: str, skill_metas: list[SkillMetadata]
    ) -> str:
        """Build the final system prompt with a lightweight skill catalog.

        Instead of injecting full skill content, appends an XML catalog
        (~100 tokens per skill) and instructions for using the
        ``load_skill`` tool to load full instructions on demand.
        """
        if not skill_metas:
            return base_prompt

        catalog = generate_skills_catalog(skill_metas)

        instructions = (
            "Tienes skills disponibles que puedes cargar bajo demanda. "
            "Antes de usar una skill, llama a la herramienta "
            "`load_skill` con el nombre de la skill para obtener sus "
            "instrucciones detalladas. Si necesitas un archivo "
            "adicional de la skill, usa `load_skill_resource`."
        )

        return (
            f"{base_prompt}\n\n"
            f"## Skills disponibles\n\n"
            f"{instructions}\n\n"
            f"{catalog}"
        )
