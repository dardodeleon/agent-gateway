"""Tool 1.4: list_tags — List all available tags for agent search."""

from __future__ import annotations

import logging

import asyncpg
from fastmcp.exceptions import ToolError

from shared.database import get_all_tags
from shared.telemetry import get_tracer

logger = logging.getLogger("[TASK-REGISTRY]")

async def list_tags_tool(pool: asyncpg.Pool) -> dict:
    """Retorna todos los tags disponibles de agentes activos con conteo.

    Args:
        pool: Database connection pool.

    Returns:
        Dict with tags list (each with tag name and agent count) and total.
    """
    tracer = get_tracer("registry.tools")

    with tracer.start_as_current_span("tool.list_tags") as span:
        logger.info("list_tags called")

        try:
            rows = await get_all_tags(pool)
            tags = [
                {"tag": r["tag"], "agent_count": r["agent_count"]}
                for r in rows
            ]
            span.set_attribute("tags.count", len(tags))
            logger.info("list_tags result: %d tag(s) found", len(tags))
            return {"tags": tags, "total": len(tags)}
        except Exception as exc:
            error_msg = f"Error al consultar tags: {exc}"
            logger.error(error_msg, exc_info=True)
            span.set_attribute("error", True)
            raise ToolError(error_msg) from exc
