"""Tool 1.2: send_task — Send a task to a specific agent."""

from __future__ import annotations

import logging

import aio_pika
import asyncpg
from fastmcp.exceptions import ToolError

from services.task_service import send_task as _send_task, mark_task_error
from services.rabbitmq_publisher import publish_new_task
from shared.telemetry import get_meter, get_tracer

logger = logging.getLogger("[TASK-REGISTRY]")

_meter = get_meter("registry.tools")
_tasks_created = _meter.create_counter(
    "registry.tasks.created",
    description="Total tasks created via send_task",
)

async def send_task_tool(
    pool: asyncpg.Pool,
    exchange: aio_pika.Exchange,
    agent_provider: str,
    agent_name: str,
    task_text: str,
) -> dict:
    """Envia una tarea a un agente especifico identificado por su proveedor y nombre.

    Retorna el ID de la tarea creada.

    Args:
        pool: Database connection pool.
        exchange: RabbitMQ exchange for publishing.
        agent_provider: Nombre del proveedor del agente.
        agent_name: Nombre del agente.
        task_text: Texto/contenido de la tarea.

    Returns:
        Dict with task_id, status, and message.
    """
    tracer = get_tracer("registry.tools")

    with tracer.start_as_current_span(
        "tool.send_task",
        attributes={
            "agent.provider": agent_provider,
            "agent.name": agent_name,
        },
    ) as span:
        logger.info(
            "send_task called: agent=%s/%s", agent_provider, agent_name
        )

        # 1. Validate agent and create task + message in DB
        try:
            result = await _send_task(pool, agent_provider, agent_name, task_text)
        except ValueError as exc:
            error_msg = str(exc)
            logger.warning("send_task validation error: %s", error_msg)
            span.set_attribute("error", True)
            raise ToolError(error_msg) from exc
        except Exception as exc:
            error_msg = f"Error al crear tarea: {exc}"
            logger.error(error_msg, exc_info=True)
            span.set_attribute("error", True)
            raise ToolError(error_msg) from exc

        span.set_attribute("task.id", str(result.task_id))
        _tasks_created.add(
            1,
            {"agent.provider": agent_provider, "agent.name": agent_name},
        )

        # 2. Publish to RabbitMQ
        try:
            await publish_new_task(
                exchange, result.task_id, agent_provider, agent_name
            )
        except Exception as exc:
            # Task was created in DB but RabbitMQ publish failed.
            # Set task to error status and record the failure.
            error_detail = f"Error al publicar en RabbitMQ: {exc}"
            logger.error(
                "RabbitMQ publish failed for task %s: %s",
                result.task_id,
                exc,
                exc_info=True,
            )
            span.set_attribute("error", True)
            span.add_event("rabbitmq_publish_failed", {"error": str(exc)})
            try:
                await mark_task_error(pool, result.task_id, error_detail)
            except Exception as db_exc:
                logger.error(
                    "Failed to mark task %s as error after RabbitMQ failure: %s",
                    result.task_id,
                    db_exc,
                    exc_info=True,
                )

            raise ToolError(
                f"Tarea creada (ID: {result.task_id}) pero falló la publicación "
                f"en cola de mensajes: {exc}"
            ) from exc

        logger.info("send_task completed: task_id=%s", result.task_id)
        return result.model_dump(mode="json")
