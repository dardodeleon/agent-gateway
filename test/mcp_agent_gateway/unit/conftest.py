"""Unit test fixtures for MCP Agent Gateway — in-process server with mocks."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastmcp import Client

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
MCP_GATEWAY_DIR = os.path.join(SRC_DIR, "mcp_agent_gateway")

_CONFLICTING = ("server", "tools", "services")
for _mod in list(sys.modules):
    if _mod in _CONFLICTING or _mod.startswith(("tools.", "services.")):
        del sys.modules[_mod]

for p in (SRC_DIR, MCP_GATEWAY_DIR):
    if p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)

import server as gateway_server  # noqa: E402
from tools.send_task import register_send_task  # noqa: E402

# Toma una instantánea de los objetos del módulo que pertenecen a *este* paquete MCP para que podamos
# restaurarlos en sys.modules antes de cada prueba (la otra prueba puede
# sobrescribirlos durante la recopilación).
_gateway_modules = {
    name: sys.modules[name]
    for name in list(sys.modules)
    if name in _CONFLICTING or name.startswith(("tools.", "services."))
}

@pytest.fixture(autouse=True)
def _ensure_gateway_modules(monkeypatch):
    """Restore gateway module references in sys.modules for each test."""
    for name, mod in _gateway_modules.items():
        monkeypatch.setitem(sys.modules, name, mod)

@pytest_asyncio.fixture()
async def mcp_client(server_config):
    gateway_server.db_pool = MagicMock(name="fake_db_pool")
    gateway_server.rmq_exchange = AsyncMock(name="fake_rmq_exchange")

    register_send_task(
        gateway_server.mcp,
        server_config["test_agents"],
        gateway_server.db_pool,
        gateway_server.rmq_exchange,
    )

    async with Client(gateway_server.mcp) as client:
        yield client

    # Cleanup: Eliminar la herramienta dinámica para evitar fugas de estado entre pruebas
    try:
        gateway_server.mcp.local_provider.remove_tool("send_task")
    except Exception:
        pass
