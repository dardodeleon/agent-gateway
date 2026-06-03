"""MCP Agent Gateway — simplified two-tool MCP server with dynamic agent enum.

Exposes:
  - send_task:       Unified tool with a dynamic enum of available agents.
  - get_task_status:  Check the current status of a task by ID.

The agent enum is rebuilt at runtime whenever agents change in the DB,
triggered by messages on the ``agent_gateway_events`` RabbitMQ queue.
Connected MCP clients receive ``notifications/tools/list_changed`` so they
can re-fetch ``tools/list`` and see updated enum values.
"""

import asyncio
import os
import sys

# Ensure shared module is importable inside Docker and local development
sys.path.insert(0, "/app")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import aio_pika
from fastmcp import FastMCP

from shared.database import (
    close_pool,
    create_pool,
    DEFAULT_DATABASE_URL,
    get_active_agents,
)
from shared.mcp_utils import (
    create_health_handler,
    load_instructions,
    run_mcp_server,
    setup_logging,
)
from shared.rabbitmq import (
    AGENT_GATEWAY_EVENTS_QUEUE,
    AGENT_REGISTRY_EVENTS_QUEUE,
    consume_agent_events,
    create_connection,
    EXCHANGE_NAME,
)

# Import must happen before FastMCP starts so the monkey-patch is in place
from services.session_notifier import notify_all_sessions  # noqa: E402
from tools.get_task_status import get_task_status_tool
from tools.send_task import register_send_task

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = setup_logging("[AGENT-GATEWAY]")

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

mcp = FastMCP("MCP Agent Gateway", instructions=load_instructions(__file__))

# ---------------------------------------------------------------------------
# Static tool: get_task_status
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Consulta el estado actual de una tarea por su ID. Retorna el "
        "estado y, si la tarea ya fue completada, la respuesta del agente."
    ),
)
async def get_task_status(task_id: str) -> str:
    """Check the current status of a task by its UUID."""
    return await get_task_status_tool(db_pool, task_id)

# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

mcp.custom_route("/health", methods=["GET"])(
    create_health_handler(lambda: db_pool, lambda: rmq_connection)
)

# ---------------------------------------------------------------------------
# Hot-reload: refresh tools from DB
# ---------------------------------------------------------------------------

async def refresh_tools() -> None:
    """Re-read agents from the DB and re-register ``send_task`` with fresh enum."""
    logger.info("Refreshing agent catalog ...")
    agents = await get_active_agents(db_pool, limit=10000)
    logger.info("Found %d active agent(s)", len(agents))

    # Remove current send_task and re-register with updated enum
    try:
        mcp.local_provider.remove_tool("send_task")
    except Exception:
        pass  # May not exist on first call

    register_send_task(mcp, agents, db_pool, rmq_exchange)

    # Notify all connected MCP clients
    await notify_all_sessions()
    logger.info("Tool refresh complete — clients notified")

# ---------------------------------------------------------------------------
# Background listener for agent_gateway_events
# ---------------------------------------------------------------------------

async def agent_events_listener(queue: aio_pika.Queue) -> None:
    """Consume agent_gateway_events and refresh the dynamic tool catalog."""
    await consume_agent_events(
        queue,
        handler=lambda _data: refresh_tools(),
        tracer_name="gateway.agent_listener",
        span_name="agent.event.refresh",
    )

# ---------------------------------------------------------------------------
# Startup / shutdown helpers
# ---------------------------------------------------------------------------

async def startup() -> None:
    """Initialise database pool, RabbitMQ, register tools, and start listener."""
    global db_pool, rmq_connection, rmq_channel, rmq_exchange, _listener_task

    database_url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    rabbitmq_url = os.environ.get(
        "RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"
    )

    # 1. Database pool
    logger.info("Connecting to PostgreSQL ...")
    db_pool = await create_pool(database_url)

    # 2. RabbitMQ connection
    logger.info("Connecting to RabbitMQ ...")
    rmq_connection = await create_connection(rabbitmq_url)
    rmq_channel = await rmq_connection.channel()
    await rmq_channel.set_qos(prefetch_count=10)

    # 3. Declare exchange (idempotent) and gateway-specific queue
    rmq_exchange = await rmq_channel.declare_exchange(
        EXCHANGE_NAME,
        aio_pika.ExchangeType.DIRECT,
        durable=True,
    )
    gateway_queue = await rmq_channel.declare_queue(
        AGENT_GATEWAY_EVENTS_QUEUE,
        durable=True,
    )
    # Bind to the SAME routing key as the registry events queue so both
    # queues receive a copy of every agent change message.
    await gateway_queue.bind(rmq_exchange, routing_key=AGENT_REGISTRY_EVENTS_QUEUE)

    # 4. Initial tool registration with current agents from DB
    agents = await get_active_agents(db_pool, limit=10000)
    logger.info("Initial catalog: %d active agent(s)", len(agents))
    register_send_task(mcp, agents, db_pool, rmq_exchange)

    # 5. Start background listener for agent events
    _listener_task = asyncio.create_task(
        agent_events_listener(gateway_queue),
        name="agent-gateway-events-listener",
    )

    logger.info("MCP Agent Gateway started successfully")

async def shutdown() -> None:
    """Gracefully close resources."""
    global _listener_task

    logger.info("Shutting down MCP Agent Gateway ...")

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

    logger.info("MCP Agent Gateway shut down cleanly")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    """Initialise infrastructure then run the MCP server."""
    await run_mcp_server(mcp, "MCP_PORT", 8003, startup, shutdown, logger)

if __name__ == "__main__":
    asyncio.run(main())
