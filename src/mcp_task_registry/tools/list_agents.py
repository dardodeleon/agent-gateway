"""Tool 1.1: list_agents — List available agents in the system."""

from __future__ import annotations

import logging

import asyncpg
from fastmcp.exceptions import ToolError

from services.agent_registry import list_agents as _list_agents
from shared.telemetry import get_tracer

logger = logging.getLogger("[TASK-REGISTRY]")

async def list_agents_tool(
    pool: asyncpg.Pool,
    tag: str | None = None,
    limit: int = 10,
) -> dict:
    """Lista los agentes disponibles en el sistema.

    Permite filtrar por tag y controlar la cantidad de resultados.

    Args:
        pool: Database connection pool.
        tag: Tag para filtrar agentes (optional).
        limit: Cantidad maxima de agentes a retornar (default 10).

    Returns:
        Dict with agents list, total count, and applied filter.
    """
    tracer = get_tracer("registry.tools")

    with tracer.start_as_current_span(
        "tool.list_agents",
        attributes={"filter.tag": tag or "", "filter.limit": limit},
    ) as span:
        logger.info("list_agents called: tag=%s, limit=%d", tag, limit)

        try:
            result = await _list_agents(pool, tag=tag, limit=limit)
            span.set_attribute("agents.count", result.total)
            logger.info("list_agents result: %d agent(s) found", result.total)
            return result.model_dump(mode="json")
        except Exception as exc:
            error_msg = f"Error al consultar agentes: {exc}"
            logger.error(error_msg, exc_info=True)
            span.set_attribute("error", True)
            raise ToolError(error_msg) from exc
