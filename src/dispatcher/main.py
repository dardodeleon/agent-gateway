"""Dispatcher entry point — starts consumer and watcher.

This is the main process for Module 3 of the multi-agent task dispatch
system.  It:

1. Loads ``models.yml`` and validates it.
2. Connects to PostgreSQL and RabbitMQ.
3. Performs an initial scan of the ``agents/`` directory.
4. Starts the RabbitMQ task consumer and the filesystem watcher as
   concurrent asyncio tasks.
5. Handles SIGTERM / SIGINT for graceful shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

# Ensure shared module is importable when running inside Docker (/app)
sys.path.insert(0, "/app")
# Also support running from the src/ directory during local development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.database import create_pool, close_pool
from shared.rabbitmq import create_connection, setup_infrastructure
from shared.telemetry import (
    init_telemetry_with_asyncpg,
    shutdown_telemetry,
    TraceContextFormatter,
    TRACE_LOG_FORMAT,
)

from config import load_models_config
from agent_core import AgentFactory
from pipeline import TaskConsumer, DispatchClient
from watcher import AgentWatcher

# ---------------------------------------------------------------------------
# Logging (trace-correlated format)
# ---------------------------------------------------------------------------

_formatter = TraceContextFormatter(TRACE_LOG_FORMAT)
_handler = logging.StreamHandler()
_handler.setFormatter(_formatter)

_root = logging.getLogger()
_root.setLevel(logging.INFO)
_root.handlers.clear()
_root.addHandler(_handler)

logger = logging.getLogger("[DISPATCHER]")

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://dispatcher:dispatcher_secret@localhost:5432/task_dispatcher",
)
RABBITMQ_URL = os.environ.get(
    "RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"
)
MODELS_PATH = os.environ.get("MODELS_PATH", "/app/models.yml")
AGENTS_DIR = os.environ.get("AGENTS_DIR", "/app/agents")
TOOLS_DIR = os.environ.get("TOOLS_DIR", "/app/tools")
SKILLS_DIR = os.environ.get("SKILLS_DIR", "/app/skills")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    """Initialise all components and run consumer + watcher concurrently."""
    # --- 0. Initialize OpenTelemetry ---
    service_name = os.environ.get("OTEL_SERVICE_NAME", "dispatcher")
    init_telemetry_with_asyncpg(service_name)

    # --- 1. Load models.yml ---
    logger.info("Loading models configuration from '%s'", MODELS_PATH)
    models_config = load_models_config(MODELS_PATH)

    # --- 2. Connect to PostgreSQL ---
    logger.info("Connecting to PostgreSQL ...")
    db_pool = await create_pool(DATABASE_URL)

    # --- 3. Connect to RabbitMQ ---
    logger.info("Connecting to RabbitMQ ...")
    rmq_connection = await create_connection(RABBITMQ_URL)
    rmq_channel = await rmq_connection.channel()
    exchange, task_queue, events_queue = await setup_infrastructure(rmq_channel)

    # --- 4. Create dispatch client and agent factory ---
    dispatch_client = DispatchClient(db_pool)
    agent_factory = AgentFactory(
        models_config,
        tools_base=TOOLS_DIR,
        skills_base=SKILLS_DIR,
        agents_base=AGENTS_DIR,
    )

    # --- 5. Create watcher and perform initial scan ---
    loop = asyncio.get_running_loop()
    watcher = AgentWatcher(
        agents_dir=AGENTS_DIR,
        models_config=models_config,
        exchange=exchange,
        db_pool=db_pool,
        loop=loop,
        tools_base=TOOLS_DIR,
        skills_base=SKILLS_DIR,
    )
    logger.info("Performing initial agent scan ...")
    await watcher.initial_scan()

    # --- 6. Create consumer ---
    consumer = TaskConsumer(
        channel=rmq_channel,
        dispatch_client=dispatch_client,
        agent_factory=agent_factory,
        models_config=models_config,
        agents_dir=AGENTS_DIR,
    )

    # --- 7. Graceful shutdown handler ---
    shutdown_event = asyncio.Event()

    async def _shutdown() -> None:
        """Stop consumer and watcher, close connections."""
        logger.info("Initiating graceful shutdown ...")
        shutdown_event.set()

        await consumer.stop()
        await watcher.stop()

        # Close RabbitMQ
        if not rmq_channel.is_closed:
            await rmq_channel.close()
        if not rmq_connection.is_closed:
            await rmq_connection.close()
        logger.info("RabbitMQ connections closed")

        # Close DB pool
        await close_pool(db_pool)
        logger.info("Database pool closed")

        # Shutdown telemetry
        shutdown_telemetry()

    def _signal_handler() -> None:
        logger.info("Received shutdown signal")
        asyncio.ensure_future(_shutdown())

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows does not support add_signal_handler
            pass

    # --- 8. Run consumer and watcher concurrently ---
    logger.info("Dispatcher is ready — starting consumer and watcher")

    try:
        await asyncio.gather(
            consumer.start(),
            watcher.start(),
        )
    except asyncio.CancelledError:
        logger.info("Tasks cancelled during shutdown")
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received")
    finally:
        if not shutdown_event.is_set():
            await _shutdown()

    logger.info("Dispatcher shut down cleanly")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Dispatcher interrupted by user")
