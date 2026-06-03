"""Shared utilities for MCP servers."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import Callable

def load_instructions(module_file: str) -> str | None:
    """Load instructions.md from the same directory as the calling module.

    Args:
        module_file: Pass ``__file__`` from the calling module.

    Returns:
        The stripped file contents, or *None* if the file does not exist.
    """
    path = os.path.join(os.path.dirname(module_file), "instructions.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

def setup_logging(prefix: str) -> logging.Logger:
    """Configure structured logging with trace correlation and return a prefixed logger.

    Log lines include ``trace_id`` and ``span_id`` when inside an active
    OpenTelemetry span, enabling log-to-trace correlation in Jaeger.

    Args:
        prefix: Logger name / prefix, e.g. ``"[TASK-REGISTRY]"``.
    """
    from shared.telemetry import TraceContextFormatter, TRACE_LOG_FORMAT

    formatter = TraceContextFormatter(TRACE_LOG_FORMAT)
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)

    return logging.getLogger(prefix)

def register_shutdown_signals(shutdown_coro_fn) -> None:
    """Register SIGTERM/SIGINT handlers that schedule *shutdown_coro_fn*.

    Safe to call on Windows where ``add_signal_handler`` is not supported.
    """
    loop = asyncio.get_running_loop()

    def _handler():
        asyncio.ensure_future(shutdown_coro_fn())

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handler)
        except NotImplementedError:
            pass  # Windows

def create_health_handler(
    db_pool_fn: Callable,
    rmq_connection_fn: Callable | None = None,
):
    """Create a reusable ``/health`` endpoint handler for MCP servers.

    Args:
        db_pool_fn: Callable returning the current asyncpg pool (e.g. ``lambda: db_pool``).
        rmq_connection_fn: Optional callable returning the aio-pika connection.

    Returns:
        An async handler suitable for ``@mcp.custom_route("/health")``.
    """

    async def health(request):
        from starlette.responses import JSONResponse

        checks: dict[str, str] = {}
        healthy = True

        # Database check
        pool = db_pool_fn()
        if pool is None:
            checks["database"] = "error: pool not initialised"
            healthy = False
        else:
            try:
                async with pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                checks["database"] = "ok"
            except Exception as exc:
                checks["database"] = f"error: {exc}"
                healthy = False

        # Optional RabbitMQ check
        if rmq_connection_fn is not None:
            try:
                conn = rmq_connection_fn()
                if conn and not conn.is_closed:
                    checks["rabbitmq"] = "ok"
                else:
                    checks["rabbitmq"] = "error: connection closed"
                    healthy = False
            except Exception as exc:
                checks["rabbitmq"] = f"error: {exc}"
                healthy = False

        status_code = 200 if healthy else 503
        return JSONResponse(
            {"status": "healthy" if healthy else "unhealthy", "checks": checks},
            status_code=status_code,
        )

    return health

async def run_mcp_server(
    mcp,
    port_env: str,
    default_port: int,
    startup_fn: Callable,
    shutdown_fn: Callable,
    logger: logging.Logger,
) -> None:
    """Run a FastMCP server with standard lifecycle management.

    Handles telemetry init/shutdown, startup/shutdown callbacks,
    signal registration, and the server event loop.

    Args:
        mcp: The FastMCP instance.
        port_env: Environment variable name for the port (e.g. ``"MCP_PORT"``).
        default_port: Fallback port if env var is unset.
        startup_fn: Async callable for service-specific initialisation.
        shutdown_fn: Async callable for service-specific teardown.
        logger: Logger instance for status messages.
    """
    from shared.telemetry import init_telemetry_with_asyncpg, shutdown_telemetry

    init_telemetry_with_asyncpg()
    await startup_fn()

    register_shutdown_signals(shutdown_fn)

    port = int(os.environ.get(port_env, str(default_port)))
    logger.info("Starting MCP server on port %d (streamable-http) ...", port)

    try:
        await mcp.run_async(transport="streamable-http", host="0.0.0.0", port=port)
    finally:
        await shutdown_fn()
        shutdown_telemetry()
