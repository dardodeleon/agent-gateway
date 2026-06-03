"""Task service — create tasks and check their status."""

from __future__ import annotations

import logging
import uuid

import asyncpg

from shared.database import (
    get_agent,
    create_task,
    get_task,
    get_last_message_by_role,
    update_task_status,
    create_message,
)
from models.task import TaskResponse

logger = logging.getLogger("[TASK-REGISTRY]")

async def send_task(
    pool: asyncpg.Pool,
    agent_provider: str,
    agent_name: str,
    task_text: str,
) -> TaskResponse:
    """Validate agent, create task + initial message, return task_id.

    The caller (tool) is responsible for publishing the RabbitMQ message
    after this function succeeds, and for handling publish failures.
    """
    # 1. Validate agent exists and is active
    agent = await get_agent(pool, agent_provider, agent_name)
    if not agent:
        raise ValueError(
            f"El agente '{agent_provider}/{agent_name}' no existe"
        )
    if agent["status"] == "internal":
        raise ValueError(
            f"El agente '{agent_provider}/{agent_name}' es interno y solo puede "
            f"usarse como sub-agente en swarms. No acepta tareas directas."
        )
    if agent["status"] != "active":
        raise ValueError(
            f"El agente '{agent_provider}/{agent_name}' no esta activo "
            f"(status: {agent['status']})"
        )

    # 2. Generate task ID in Python so the same UUID goes to DB and RabbitMQ
    task_id = uuid.uuid4()

    # 3. Create task and initial user message in a single transaction
    await create_task(pool, task_id, agent_provider, agent_name, task_text)

    logger.info(
        "Task created: task_id=%s, agent=%s/%s",
        task_id,
        agent_provider,
        agent_name,
    )

    return TaskResponse(
        task_id=task_id,
        status="pending",
        message=f"Tarea enviada exitosamente al agente {agent_provider}/{agent_name}",
    )

async def mark_task_error(
    pool: asyncpg.Pool,
    task_id: uuid.UUID,
    error_detail: str,
) -> None:
    """Set a task to error status and record a system message."""
    await update_task_status(pool, task_id, "error")
    await create_message(pool, task_id, "system", error_detail)
    logger.error("Task %s set to error: %s", task_id, error_detail)

async def check_task_status(
    pool: asyncpg.Pool,
    task_id: uuid.UUID,
) -> TaskResponse:
    """Look up a task and return its current status with relevant details."""
    task = await get_task(pool, task_id)
    if not task:
        raise ValueError(f"Tarea no encontrada: {task_id}")

    status = task["status"]

    if status == "pending":
        return TaskResponse(
            task_id=task_id,
            status="pending",
            message="Pendiente de asignacion",
        )

    if status == "assigned":
        return TaskResponse(
            task_id=task_id,
            status="assigned",
            message="Pendiente de respuesta — tarea asignada a agente",
        )

    if status == "completed":
        last_agent_msg = await get_last_message_by_role(
            pool, task_id, "agent"
        )
        response_text = (
            last_agent_msg["content"] if last_agent_msg else None
        )
        return TaskResponse(
            task_id=task_id,
            status="completed",
            response=response_text,
        )

    if status == "error":
        last_system_msg = await get_last_message_by_role(
            pool, task_id, "system"
        )
        error_text = (
            last_system_msg["content"] if last_system_msg else "Error desconocido"
        )
        return TaskResponse(
            task_id=task_id,
            status="error",
            error_message=error_text,
        )

    # Fallback for unexpected status values
    return TaskResponse(
        task_id=task_id,
        status=status,
        message=f"Estado desconocido: {status}",
    )
