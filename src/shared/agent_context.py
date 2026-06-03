"""Agent execution context — thread-safe identity for the running agent.

Uses ``contextvars.ContextVar`` so each agent thread gets its own
isolated identity, even when multiple agents run concurrently via
``asyncio.to_thread``.

Usage from tools:

    from shared.agent_context import get_agent_identity
    provider, name = get_agent_identity()

Usage from the dispatcher (before running an agent):

    from shared.agent_context import set_agent_identity
    set_agent_identity("custom", "assistant")
"""

from __future__ import annotations

from contextvars import ContextVar

_agent_provider: ContextVar[str] = ContextVar("agent_provider", default="")
_agent_name: ContextVar[str] = ContextVar("agent_name", default="")

def set_agent_identity(provider: str, name: str) -> None:
    """Set the identity of the currently executing agent."""
    _agent_provider.set(provider)
    _agent_name.set(name)

def get_agent_identity() -> tuple[str, str]:
    """Return ``(provider, name)`` of the currently executing agent.

    Returns:
        Tuple of (provider, agent_name).  Both default to ``""``
        if no identity has been set.
    """
    return _agent_provider.get(), _agent_name.get()
