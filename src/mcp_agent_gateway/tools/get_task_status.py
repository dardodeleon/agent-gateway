"""get_task_status tool implementation."""

import logging
from uuid import UUID

from fastmcp.exceptions import ToolError

from shared.database import get_last_message_by_role, get_task
from shared.telemetry import get_tracer

logger = logging.getLogger("[AGENT-GATEWAY]")

async def get_task_status_tool(pool, task_id: str) -> str:
    """Check the current status of a task by its UUID."""
    tracer = get_tracer("gateway.tools")

    with tracer.start_as_current_span(
        "tool.get_task_status",
        attributes={"task.id": task_id},
    ) as span:
        logger.info("get_task_status called: task_id=%s", task_id)

        # Validate UUID format
        try:
            parsed_id = UUID(task_id)
        except (ValueError, AttributeError):
            error_msg = f"ID de tarea inválido: '{task_id}' — debe ser un UUID válido"
            logger.warning(error_msg)
            span.set_attribute("error", True)
            raise ToolError(error_msg)

        try:
            task = await get_task(pool, parsed_id)
        except Exception as exc:
            error_msg = f"Error al consultar estado de tarea: {exc}"
            logger.error(error_msg, exc_info=True)
            span.set_attribute("error", True)
            raise ToolError(error_msg) from exc

        if not task:
            error_msg = f"Tarea no encontrada: {task_id}"
            logger.warning(error_msg)
            span.set_attribute("error", True)
            raise ToolError(error_msg)

        status = task["status"]
        span.set_attribute("task.status", status)
        logger.info(
            "get_task_status result: task_id=%s, status=%s", task_id, status
        )

        if status == "pending":
            return f"Estado de tarea {task_id}: pendiente de asignación."

        if status == "assigned":
            return f"Estado de tarea {task_id}: asignada a agente, pendiente de respuesta."

        if status == "completed":
            last_agent_msg = await get_last_message_by_role(
                pool, parsed_id, "agent"
            )
            response = last_agent_msg["content"] if last_agent_msg else "Sin respuesta"
            return f"Estado de tarea {task_id}: completada.\n\nRespuesta del agente:\n{response}"

        if status == "error":
            last_system_msg = await get_last_message_by_role(
                pool, parsed_id, "system"
            )
            error_detail = last_system_msg["content"] if last_system_msg else "Error desconocido"
            return f"Estado de tarea {task_id}: error.\n\nDetalle: {error_detail}"

        return f"Estado de tarea {task_id}: {status}."
