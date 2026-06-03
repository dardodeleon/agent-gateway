"""MCP Task Registry — Module 1 server.

FastMCP server on port 8001 that exposes 3 tools for external task
registration.  Connects to both PostgreSQL and RabbitMQ (publisher +
event listener for agent lifecycle changes).
"""

from __future__ import annotations

import asyncio
import os
import sys

# Ensure shared module is importable inside Docker and local development
sys.path.insert(0, "/app")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastmcp import FastMCP

import aio_pika

from shared.database import create_pool, close_pool, DEFAULT_DATABASE_URL
from shared.mcp_utils import (
    load_instructions,
    setup_logging,
    create_health_handler,
    run_mcp_server,
)
from shared.rabbitmq import (
    create_connection,
    setup_infrastructure,
    consume_agent_events,
    AGENT_REGISTRY_EVENTS_QUEUE,
)

from services.agent_registry import handle_agent_event
from tools.list_tags import list_tags_tool
from tools.list_agents import list_agents_tool
from tools.send_task import send_task_tool
from tools.check_task_status import check_task_status_tool
from prompts import load_prompt

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = setup_logging("[TASK-REGISTRY]")

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

db_pool = None
rmq_connection = None
rmq_channel = None
rmq_exchange = None
_listener_task: asyncio.Task | None = None

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("MCP Task Registry", instructions=load_instructions(__file__))

# ---------------------------------------------------------------------------
# Tool registrations
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Lista todos los tags (categorias) disponibles de agentes activos "
        "junto con la cantidad de agentes en cada tag. "
        "IMPORTANTE: Invoca esta herramienta ANTES de buscar agentes con "
        "list_agents para conocer las categorias disponibles y seleccionar "
        "el tag mas relevante para tu busqueda."
    ),
)
async def list_tags() -> dict:
    """List all available tags from active agents with counts."""
    return await list_tags_tool(db_pool)

@mcp.tool(
    description=(
        "Lista los agentes disponibles en el sistema. "
        "Permite filtrar por tag y controlar la cantidad de resultados. "
        "Consejo: usa list_tags primero para descubrir los tags disponibles."
    ),
)
async def list_agents(tag: str | None = None, limit: int = 10) -> dict:
    """List available agents, optionally filtered by tag."""
    return await list_agents_tool(db_pool, tag=tag, limit=limit)

@mcp.tool(
    description=(
        "Envia una tarea a un agente especifico identificado por su "
        "proveedor y nombre. Retorna el ID de la tarea creada."
    ),
)
async def send_task(
    agent_provider: str, agent_name: str, task_text: str
) -> dict:
    """Send a task to a specific agent."""
    return await send_task_tool(
        db_pool, rmq_exchange, agent_provider, agent_name, task_text
    )

@mcp.tool(
    description=(
        "Consulta el estado actual de una tarea por su ID. Retorna el "
        "estado y, si la tarea ya fue completada, la respuesta del agente."
    ),
)
async def check_task_status(task_id: str) -> dict:
    """Check the current status of a task by its UUID."""
    return await check_task_status_tool(db_pool, task_id)

# ---------------------------------------------------------------------------
# Prompt registrations
# ---------------------------------------------------------------------------

@mcp.prompt(
    description=(
        "Guia paso a paso para descubrir los agentes IA disponibles "
        "en el sistema, sus categorias y capacidades."
    ),
)
async def discover_agents() -> str:
    """Discover available agents step by step."""
    return load_prompt("discover_agents.md")

@mcp.prompt(
    description=(
        "Busca el agente mas adecuado y enviale una tarea. "
        "Incluye descubrimiento automatico del agente correcto."
    ),
)
async def send_task_prompt(
    task_description: str = "[Describe aqui la tarea que deseas enviar a un agente]",
) -> str:
    """Find the right agent and send a task."""
    return load_prompt("send_task.md", task_description=task_description)

@mcp.prompt(
    description=(
        "Consulta el estado de una tarea enviada previamente "
        "e interpreta el resultado."
    ),
)
async def check_task(
    task_id: str = "[Pega aqui el task_id (UUID) de la tarea a consultar]",
) -> str:
    """Check the status of a previously sent task."""
    return load_prompt("check_task.md", task_id=task_id)

@mcp.prompt(
    description=(
        "Flujo completo: descubre agentes, envia la tarea al mas adecuado, "
        "espera el resultado y lo presenta."
    ),
)
async def full_workflow(
    task_description: str = "[Describe aqui la tarea completa que deseas realizar]",
) -> str:
    """Complete workflow: discover, send, wait, and present results."""
    return load_prompt("full_workflow.md", task_description=task_description)

# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

mcp.custom_route("/health", methods=["GET"])(
    create_health_handler(lambda: db_pool, lambda: rmq_connection)
)

# ---------------------------------------------------------------------------
# Background listener for agent_registry_events
# ---------------------------------------------------------------------------

async def agent_events_listener(queue: aio_pika.Queue) -> None:
    """Consume agent_registry_events and update the local agents table."""
    await consume_agent_events(
        queue,
        handler=lambda data: handle_agent_event(db_pool, data),
        tracer_name="registry.agent_listener",
        span_name="agent.event.process",
    )

# ---------------------------------------------------------------------------
# Startup / shutdown helpers
# ---------------------------------------------------------------------------

async def startup() -> None:
    """Initialise database pool, RabbitMQ connection, and background tasks."""
    global db_pool, rmq_connection, rmq_channel, rmq_exchange, _listener_task

    database_url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    rabbitmq_url = os.environ.get(
        "RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"
    )

    # 1. Database pool
    logger.info("Connecting to PostgreSQL ...")
    db_pool = await create_pool(database_url)

    # 2. RabbitMQ connection + infrastructure
    logger.info("Connecting to RabbitMQ ...")
    rmq_connection = await create_connection(rabbitmq_url)
    rmq_channel = await rmq_connection.channel()
    await rmq_channel.set_qos(prefetch_count=10)

    rmq_exchange, _task_queue, events_queue = await setup_infrastructure(
        rmq_channel
    )

    # 3. Start background listener for agent events
    _listener_task = asyncio.create_task(
        agent_events_listener(events_queue),
        name="agent-events-listener",
    )

    logger.info("MCP Task Registry started successfully")

async def shutdown() -> None:
    """Gracefully close resources."""
    global _listener_task

    logger.info("Shutting down MCP Task Registry ...")

    # Cancel listener
    if _listener_task and not _listener_task.done():
        _listener_task.cancel()
        try:
            await _listener_task
        except asyncio.CancelledError:
            pass

    # Close RabbitMQ
    if rmq_channel and not rmq_channel.is_closed:
        await rmq_channel.close()
    if rmq_connection and not rmq_connection.is_closed:
        await rmq_connection.close()
        logger.info("RabbitMQ connection closed")

    # Close DB pool
    if db_pool:
        await close_pool(db_pool)

    logger.info("MCP Task Registry shut down cleanly")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    """Initialise infrastructure then run the MCP server."""
    await run_mcp_server(mcp, "MCP_PORT", 8001, startup, shutdown, logger)

if __name__ == "__main__":
    asyncio.run(main())
