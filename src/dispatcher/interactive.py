#!/usr/bin/env python3
"""Interactive CLI for conversing with dispatcher agents.

Run from outside the container:
    docker compose exec dispatcher python interactive.py
Or via the wrapper script:
    chat.bat
"""

from __future__ import annotations

import io
import os
import signal
import sys
import warnings

# Reconfigure stdout/stderr to UTF-8 with replacement for surrogates
# (fixes encoding issues when Docker pipes output to a Windows terminal)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

from config import load_agent_config, load_models_config
from agent_core import AgentFactory
from shared.agent_context import set_agent_identity

AGENTS_DIR = "/app/agents"
MODELS_PATH = "/app/models.yml"

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def scan_agents(agents_dir: str) -> dict:
    """Scan agents directory and return structured info.

    Returns dict with:
      - active: [(provider, name, display, sub_agents)] selectable agents
      - configs: {(provider, name): AgentConfig} all loaded configs
    """
    configs: dict[tuple[str, str], object] = {}
    if not os.path.isdir(agents_dir):
        return {"active": [], "configs": configs}

    for provider in sorted(os.listdir(agents_dir)):
        provider_path = os.path.join(agents_dir, provider)
        if not os.path.isdir(provider_path):
            continue
        for name in sorted(os.listdir(provider_path)):
            config_path = os.path.join(provider_path, name, "agent.yml")
            if not os.path.isfile(config_path):
                continue
            try:
                config = load_agent_config(os.path.join(provider_path, name))
                configs[(provider, name)] = config
            except Exception:
                pass

    active: list[tuple[str, str, str, str, list[tuple[str, str, str, str]]]] = []
    for (provider, name), config in sorted(configs.items()):
        if config.status != "active":
            continue
        # Collect sub-agents from delegates or swarm
        sub_agents: list[tuple[str, str, str, str]] = []
        agent_refs = []
        if config.delegates:
            agent_refs = config.delegates.agents
        elif config.swarm:
            agent_refs = config.swarm.agents
        for ref in agent_refs:
            sub_prov, sub_name = ref.split(":", 1)
            sub_config = configs.get((sub_prov, sub_name))
            if sub_config:
                sub_display = sub_config.display_name or f"{sub_prov}/{sub_name}"
                sub_agents.append((sub_prov, sub_name, sub_display, sub_config.model))
        display = config.display_name or f"{provider}/{name}"
        active.append((provider, name, display, config.model, sub_agents))

    return {"active": active, "configs": configs}

# ANSI color helpers
DIM = "\033[2m"
RESET = "\033[0m"
CYAN = "\033[36m"

def show_menu(agents: list[tuple[str, str, str, list]]) -> tuple[str, str] | None:
    """Display numbered agent menu. Returns (provider, name) or None to quit."""
    print("\n=== Agentes disponibles ===\n")
    for i, (provider, name, display, model, sub_agents) in enumerate(agents, 1):
        print(f"  {CYAN}{i}.{RESET} {display}  ({provider}/{name})  {DIM}[{model}]{RESET}")
        for sub_prov, sub_name, sub_display, sub_model in sub_agents:
            print(f"  {DIM}     └─ {sub_display}  ({sub_prov}/{sub_name})  [{sub_model}]{RESET}")
    print(f"\n  0. Salir")

    while True:
        try:
            choice = input("\nElige un agente: ").strip()
        except EOFError:
            return None
        if choice == "0":
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(agents):
                return agents[idx][0], agents[idx][1]
        except ValueError:
            pass
        print("Opcion invalida, intenta de nuevo.")


def chat(agent: object, provider: str, name: str) -> None:
    """Conversation loop. Type 'salir' to return to agent menu.

    Strands Agent uses PrintingCallbackHandler by default, which streams
    tokens to stdout as they arrive.  We just call ``agent(prompt)``
    synchronously and let the handler print; no need to re-print the result.
    """
    separator = "-" * 60
    print(f"\n--- Conversacion con {provider}/{name} ---")
    print("(Escribe 'salir' para volver al menu)\n")

    while True:
        try:
            user_input = input("Tu: ").strip()
        except EOFError:
            break
        print(separator)

        if not user_input:
            continue
        if user_input.lower() == "salir":
            break

        set_agent_identity(provider, name)
        try:
            print("\nAgente: ", end="", flush=True)
            agent(user_input)
            print()
        except Exception as exc:
            print(f"\n[Error] {exc}\n")

        print(separator)

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main() -> None:
    models_config = load_models_config(MODELS_PATH)
    factory = AgentFactory(models_config=models_config)

    active_agent = None

    def on_sigint(_sig: int, _frame: object) -> None:
        nonlocal active_agent
        if active_agent is not None:
            print("\n\nAgente eliminado. Saliendo...")
            active_agent = None
        else:
            print("\n\nSaliendo...")
        sys.exit(0)

    signal.signal(signal.SIGINT, on_sigint)

    while True:
        scan = scan_agents(AGENTS_DIR)
        agents = scan["active"]
        if not agents:
            print("No hay agentes disponibles en", AGENTS_DIR)
            return

        selection = show_menu(agents)
        if selection is None:
            print("\nHasta luego!")
            break

        provider, name = selection
        agent_dir = os.path.join(AGENTS_DIR, provider, name)

        try:
            config = load_agent_config(agent_dir)
            active_agent = factory.create_agent(config)
            chat(active_agent, provider, name)
        except Exception as exc:
            print(f"\n[Error creando agente] {exc}\n")
        finally:
            active_agent = None

if __name__ == "__main__":
    main()
