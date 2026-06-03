"""Tool 1.3: check_task_status — Check the current status of a task."""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg
from fastmcp.exceptions import ToolError

from services.task_service import check_task_status as _check_task_status
from shared.telemetry import get_tracer

logger = logging.getLogger("[TASK-REGISTRY]")

async def check_task_status_tool(
    pool: asyncpg.Pool,
    task_id: str,
) -> dict:
    """Consulta el estado actual de una tarea por su ID.

    Retorna el estado y, si la tarea ya fue completada, la respuesta del agente.

    Args:
        pool: Database connection pool.
        task_id: UUID de la tarea a consultar.

    Returns:
        Dict with task_id, status, and relevant message/response/error.
    """
    tracer = get_tracer("registry.tools")

    with tracer.start_as_current_span(
        "tool.check_task_status",
        attributes={"task.id": task_id},
    ) as span:
        logger.info("check_task_status called: task_id=%s", task_id)

        # Validate UUID format
        try:
            parsed_id = UUID(task_id)
        except (ValueError, AttributeError):
            error_msg = f"ID de tarea invalido: '{task_id}' — debe ser un UUID valido"
            logger.warning(error_msg)
            span.set_attribute("error", True)
            raise ToolError(error_msg)

        try:
            result = await _check_task_status(pool, parsed_id)
            span.set_attribute("task.status", result.status)
            logger.info(
                "check_task_status result: task_id=%s, status=%s",
                task_id,
                result.status,
            )
            return result.model_dump(mode="json")
        except ToolError:
            raise
        except ValueError as exc:
            error_msg = str(exc)
            logger.warning("check_task_status not found: %s", error_msg)
            span.set_attribute("error", True)
            raise ToolError(error_msg) from exc
        except Exception as exc:
            error_msg = f"Error al consultar estado de tarea: {exc}"
            logger.error(error_msg, exc_info=True)
            span.set_attribute("error", True)
            raise ToolError(error_msg) from exc
