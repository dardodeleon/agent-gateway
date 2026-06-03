"""Agent runner — executes a Strands agent or swarm with task messages.

Wraps the synchronous Strands agent/swarm call inside ``asyncio.to_thread``
so that the async event loop is not blocked during execution.  Applies
a configurable timeout via ``asyncio.wait_for``.
"""

from __future__ import annotations

import asyncio
import logging
import time

from pydantic import BaseModel
from strands import Agent
from strands.multiagent import Swarm

from shared.agent_context import set_agent_identity
from shared.telemetry import get_meter, get_tracer

logger = logging.getLogger("[DISPATCHER]")

_meter = get_meter("dispatcher.agent_runner")
_agent_duration = _meter.create_histogram(
    "dispatcher.agent.execution.duration_ms",
    description="Agent/swarm execution duration in milliseconds",
    unit="ms",
)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class AgentResult(BaseModel):
    """Outcome of running an agent against a set of task messages."""

    response_text: str
    is_error: bool = False


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class AgentRunner:
    """Execute a Strands agent asynchronously with timeout protection."""

    async def run(
        self,
        agent: Agent,
        messages: list[dict],
        timeout_seconds: int = 300,
        agent_provider: str = "",
        agent_name: str = "",
    ) -> AgentResult:
        """Run *agent* with the given task *messages*.

        The messages are converted to a single prompt string that the
        agent can process.  Execution happens in a background thread
        (Strands agents are synchronous) and is guarded by a timeout.

        Args:
            agent: A fully configured Strands Agent.
            messages: List of dicts with ``role`` and ``content`` keys,
                      as returned by ``get_task_messages``.
            timeout_seconds: Maximum wall-clock seconds to allow.

        Returns:
            An ``AgentResult`` containing the response or an error
            description.
        """
        prompt = self._build_prompt(messages)
        logger.info(
            "Running agent (timeout=%ds, prompt_len=%d)",
            timeout_seconds,
            len(prompt),
        )

        tracer = get_tracer("dispatcher.agent_runner")

        def _run_with_context() -> object:
            set_agent_identity(agent_provider, agent_name)
            return agent(prompt)

        t_start = time.monotonic()

        with tracer.start_as_current_span(
            "agent.run",
            attributes={
                "agent.provider": agent_provider,
                "agent.name": agent_name,
                "agent.timeout": timeout_seconds,
                "agent.prompt_len": len(prompt),
            },
        ) as span:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(_run_with_context),
                    timeout=timeout_seconds,
                )
                response_text = str(result)
                logger.info(
                    "Agent finished successfully (response_len=%d)",
                    len(response_text),
                )
                span.add_event("agent_finished", {"response_len": len(response_text)})
                return AgentResult(response_text=response_text, is_error=False)

            except asyncio.TimeoutError:
                msg = (
                    f"Timeout: el agente excedió el límite de "
                    f"{timeout_seconds}s"
                )
                logger.error(msg)
                span.set_attribute("error", True)
                span.add_event("agent_timeout")
                return AgentResult(response_text=msg, is_error=True)

            except Exception as exc:
                msg = f"Error durante ejecución del agente: {exc}"
                logger.error(msg, exc_info=True)
                span.set_attribute("error", True)
                span.add_event("agent_error", {"error": str(exc)})
                return AgentResult(response_text=msg, is_error=True)

            finally:
                duration_ms = (time.monotonic() - t_start) * 1000
                _agent_duration.record(
                    duration_ms,
                    {
                        "agent.provider": agent_provider,
                        "agent.name": agent_name,
                        "type": "agent",
                    },
                )

    async def run_swarm(
        self,
        swarm: Swarm,
        messages: list[dict],
        timeout_seconds: int = 900,
        agent_provider: str = "",
        agent_name: str = "",
    ) -> AgentResult:
        """Run a Strands *swarm* with the given task *messages*.

        The swarm's own ``execution_timeout`` acts as an internal guard,
        but we also wrap with ``asyncio.wait_for`` as an external safety net.

        Args:
            swarm: A fully configured Strands Swarm.
            messages: List of dicts with ``role`` and ``content`` keys.
            timeout_seconds: External wall-clock timeout (should be >= swarm execution_timeout).
            agent_provider: Provider of the parent agent.
            agent_name: Name of the parent agent.

        Returns:
            An ``AgentResult`` containing the swarm's final response or an error.
        """
        prompt = self._build_prompt(messages)
        logger.info(
            "Running swarm '%s/%s' (timeout=%ds, prompt_len=%d)",
            agent_provider,
            agent_name,
            timeout_seconds,
            len(prompt),
        )

        tracer = get_tracer("dispatcher.agent_runner")

        def _run_swarm_sync() -> object:
            set_agent_identity(agent_provider, agent_name)
            return swarm(prompt)

        t_start = time.monotonic()

        with tracer.start_as_current_span(
            "swarm.run",
            attributes={
                "agent.provider": agent_provider,
                "agent.name": agent_name,
                "agent.timeout": timeout_seconds,
                "agent.prompt_len": len(prompt),
                "swarm": True,
            },
        ) as span:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(_run_swarm_sync),
                    timeout=timeout_seconds,
                )

                # Extract meaningful text from SwarmResult
                response_text = self._extract_swarm_response(result)
                status = getattr(result, "status", None)

                is_error = status is not None and str(status) != "Status.COMPLETED"
                if is_error:
                    logger.warning(
                        "Swarm finished with status=%s", status
                    )
                    span.set_attribute("error", True)
                    span.add_event("swarm_non_completed", {"status": str(status)})
                else:
                    logger.info(
                        "Swarm finished successfully (response_len=%d)",
                        len(response_text),
                    )
                    span.add_event("swarm_finished", {"response_len": len(response_text)})

                return AgentResult(response_text=response_text, is_error=is_error)

            except asyncio.TimeoutError:
                msg = (
                    f"Timeout: el swarm excedió el límite de "
                    f"{timeout_seconds}s"
                )
                logger.error(msg)
                span.set_attribute("error", True)
                span.add_event("swarm_timeout")
                return AgentResult(response_text=msg, is_error=True)

            except Exception as exc:
                msg = f"Error durante ejecución del swarm: {exc}"
                logger.error(msg, exc_info=True)
                span.set_attribute("error", True)
                span.add_event("swarm_error", {"error": str(exc)})
                return AgentResult(response_text=msg, is_error=True)

            finally:
                duration_ms = (time.monotonic() - t_start) * 1000
                _agent_duration.record(
                    duration_ms,
                    {
                        "agent.provider": agent_provider,
                        "agent.name": agent_name,
                        "type": "swarm",
                    },
                )

    @staticmethod
    def _extract_swarm_response(result: object) -> str:
        """Extract a readable response string from a SwarmResult."""
        # SwarmResult has .results dict[str, NodeResult] and .node_history
        results = getattr(result, "results", None)
        node_history = getattr(result, "node_history", [])

        if results and node_history:
            # Get the last agent's result
            last_node = node_history[-1]
            last_id = getattr(last_node, "node_id", None)
            if last_id and last_id in results:
                node_result = results[last_id]
                inner = getattr(node_result, "result", None)
                if inner is not None:
                    return str(inner)

        # Fallback: stringify the whole result
        return str(result)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(messages: list[dict]) -> str:
        """Convert task messages into a single prompt string.

        - ``user`` messages are kept as primary input.
        - ``system`` messages are included as context.
        - ``agent`` messages (from prior turns) are included for
          continuation scenarios.
        """
        parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                parts.append(content)
            elif role == "system":
                parts.append(f"[Sistema] {content}")
            elif role == "agent":
                parts.append(f"[Respuesta previa del agente] {content}")
        return "\n\n".join(parts)
