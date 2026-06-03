"""Dynamic send_task tool with runtime agent enum."""

import asyncio
import enum
import logging
import os
import uuid
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from shared.database import (
    create_message,
    create_task,
    get_agent,
    get_last_message_by_role,
    get_task,
    update_task_status,
)
from shared.rabbitmq import publish_message, TASK_DISPATCH_QUEUE
from shared.telemetry import get_meter, get_tracer, inject_context

logger = logging.getLogger("[AGENT-GATEWAY]")

_meter = get_meter("gateway.tools")
_tasks_created = _meter.create_counter(
    "gateway.tasks.created",
    description="Total tasks created via gateway send_task",
)

def build_agent_enum(agents: list[dict]) -> tuple[type[enum.Enum], str]:
    """Build a Python Enum and a rich description from a list of agent dicts.

    Returns:
        (AgentEnum, description_text)
    """
    enum_values: dict[str, str] = {}
    lines: list[str] = ["Agentes disponibles:"]

    for a in agents:
        key = f"{a['provider']}/{a['name']}"
        enum_values[key] = key
        desc = a.get("description") or ""
        tags = a.get("tags") or []
        tags_str = ", ".join(tags)
        line = f"- {key}: {desc}"
        if tags_str:
            line += f". {tags_str}"
        lines.append(line)

    if not enum_values:
        # FastMCP / Pydantic requires at least one member in an Enum
        enum_values["NO_AGENTS"] = "NO_AGENTS"
        lines = ["No hay agentes disponibles actualmente."]

    AgentEnum = enum.Enum("AgentEnum", enum_values)  # type: ignore[misc]
    return AgentEnum, "\n".join(lines)

def register_send_task(mcp: FastMCP, agents: list[dict], pool, exchange) -> None:
    """(Re-)register the ``send_task`` tool with an up-to-date agent enum."""
    AgentEnum, enum_description = build_agent_enum(agents)

    @mcp.tool(
        name="send_task",
        description=(
            "Delega una tarea a un agente especializado. "
            "Úsala solo cuando el usuario lo solicite explícitamente, "
            "nunca por iniciativa propia."
        ),
    )
    async def send_task(
        agent_name: Annotated[
            AgentEnum,
            Field(description=enum_description),
        ],
        task_text: Annotated[
            str,
            Field(description="Texto de la tarea que se le asigna al agente seleccionado"),
        ],
        wait: Annotated[
            bool,
            Field(
                description=(
                    "true: espera la respuesta del agente y la retorna "
                    "directamente. false: retorna el ID inmediatamente."
                ),
            ),
        ] = True,
    ) -> str:
        """Send a task to the selected agent, optionally waiting for completion."""
        tracer = get_tracer("gateway.tools")

        with tracer.start_as_current_span(
            "tool.send_task",
            attributes={"agent.selection": agent_name.value, "task.wait": wait},
        ) as span:
            raw = agent_name.value
            if "/" not in raw:
                raise ToolError(f"Valor de agente inválido: '{raw}'")

            provider, name = raw.split("/", 1)
            logger.info("send_task called: agent=%s/%s", provider, name)

            # 1. Validate agent exists and is active
            agent = await get_agent(pool, provider, name)
            if not agent:
                raise ToolError(f"El agente '{provider}/{name}' no existe")
            if agent["status"] == "internal":
                raise ToolError(
                    f"El agente '{provider}/{name}' es interno y solo puede "
                    "usarse como sub-agente. No acepta tareas directas."
                )
            if agent["status"] != "active":
                raise ToolError(
                    f"El agente '{provider}/{name}' no está activo "
                    f"(status: {agent['status']})"
                )

            # 2. Create task + initial message in DB
            task_id = uuid.uuid4()
            try:
                await create_task(pool, task_id, provider, name, task_text)
            except Exception as exc:
                error_msg = f"Error al crear tarea: {exc}"
                logger.error(error_msg, exc_info=True)
                span.set_attribute("error", True)
                raise ToolError(error_msg) from exc

            span.set_attribute("task.id", str(task_id))
            _tasks_created.add(1, {"agent.provider": provider, "agent.name": name})

            # 3. Publish to RabbitMQ
            try:
                trace_headers: dict[str, str] = {}
                inject_context(trace_headers)
                await publish_message(
                    exchange,
                    TASK_DISPATCH_QUEUE,
                    {
                        "event": "new_task",
                        "task_id": str(task_id),
                        "agent_provider": provider,
                        "agent_name": name,
                    },
                    trace_headers=trace_headers,
                )
            except Exception as exc:
                error_detail = f"Error al publicar en RabbitMQ: {exc}"
                logger.error(
                    "RabbitMQ publish failed for task %s: %s",
                    task_id,
                    exc,
                    exc_info=True,
                )
                span.set_attribute("error", True)
                try:
                    await update_task_status(pool, task_id, "error")
                    await create_message(pool, task_id, "system", error_detail)
                except Exception as db_exc:
                    logger.error(
                        "Failed to mark task %s as error: %s",
                        task_id,
                        db_exc,
                        exc_info=True,
                    )
                raise ToolError(
                    f"Tarea creada (ID: {task_id}) pero falló la publicación "
                    f"en cola de mensajes: {exc}"
                ) from exc

            logger.info("send_task published: task_id=%s, wait=%s", task_id, wait)

            # 4. Return immediately or wait for completion
            if not wait:
                return f"Tarea enviada exitosamente al agente {provider}/{name} con el ID {task_id}"

            # Poll DB until the task completes, errors, or times out
            timeout = float(os.environ.get("SEND_TASK_WAIT_TIMEOUT", "300"))
            interval = float(os.environ.get("SEND_TASK_POLL_INTERVAL", "3"))
            deadline = asyncio.get_event_loop().time() + timeout

            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(interval)
                task = await get_task(pool, task_id)
                if task and task["status"] in ("completed", "error"):
                    if task["status"] == "completed":
                        msg = await get_last_message_by_role(pool, task_id, "agent")
                        response = msg["content"] if msg else "Sin respuesta"
                        logger.info("send_task completed: task_id=%s", task_id)
                        return (
                            # f"Tarea completada por {provider}/{name}.\n\n"
                            # f"Respuesta del agente:\n{response}"
                            response
                        )
                    else:
                        msg = await get_last_message_by_role(pool, task_id, "system")
                        detail = msg["content"] if msg else "Error desconocido"
                        logger.warning("send_task error: task_id=%s", task_id)
                        raise ToolError(
                            f"Tarea {task_id} falló.\n\nDetalle: {detail}"
                        )

            logger.warning("send_task timeout: task_id=%s, timeout=%s", task_id, timeout)
            return (
                f"Tarea enviada al agente {provider}/{name} (ID: {task_id}) "
                f"pero no completó en {timeout:.0f}s. "
                f"Usa get_task_status para consultar el resultado."
            )
