import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

TASK_ID = str(uuid.uuid4())

@pytest.mark.asyncio
async def test_invalid_uuid(mcp_client: Client):
    with pytest.raises(ToolError, match="inválido"):
        await mcp_client.call_tool(
            "get_task_status", arguments={"task_id": "not-a-uuid"}
        )

@pytest.mark.asyncio
async def test_task_not_found(mcp_client: Client):
    with patch("tools.get_task_status.get_task", new_callable=AsyncMock, return_value=None):
        with pytest.raises(ToolError, match="no encontrada"):
            await mcp_client.call_tool(
                "get_task_status", arguments={"task_id": TASK_ID}
            )

@pytest.mark.asyncio
async def test_status_pending(mcp_client: Client):
    task = {"id": TASK_ID, "status": "pending"}
    with patch("tools.get_task_status.get_task", new_callable=AsyncMock, return_value=task):
        result = await mcp_client.call_tool(
            "get_task_status", arguments={"task_id": TASK_ID}
        )

    text = result.content[0].text
    assert "pendiente de asignación" in text
    assert TASK_ID in text

@pytest.mark.asyncio
async def test_status_assigned(mcp_client: Client):
    task = {"id": TASK_ID, "status": "assigned"}
    with patch("tools.get_task_status.get_task", new_callable=AsyncMock, return_value=task):
        result = await mcp_client.call_tool(
            "get_task_status", arguments={"task_id": TASK_ID}
        )

    text = result.content[0].text
    assert "asignada a agente" in text
    assert TASK_ID in text

@pytest.mark.asyncio
async def test_status_completed(mcp_client: Client):
    task = {"id": TASK_ID, "status": "completed"}
    agent_msg = {"content": "La respuesta es 42"}
    with (
        patch("tools.get_task_status.get_task", new_callable=AsyncMock, return_value=task),
        patch("tools.get_task_status.get_last_message_by_role", new_callable=AsyncMock, return_value=agent_msg),
    ):
        result = await mcp_client.call_tool(
            "get_task_status", arguments={"task_id": TASK_ID}
        )

    text = result.content[0].text
    assert "completada" in text
    assert "La respuesta es 42" in text

@pytest.mark.asyncio
async def test_status_error(mcp_client: Client):
    task = {"id": TASK_ID, "status": "error"}
    system_msg = {"content": "Modelo no configurado"}
    with (
        patch("tools.get_task_status.get_task", new_callable=AsyncMock, return_value=task),
        patch("tools.get_task_status.get_last_message_by_role", new_callable=AsyncMock, return_value=system_msg),
    ):
        result = await mcp_client.call_tool(
            "get_task_status", arguments={"task_id": TASK_ID}
        )

    text = result.content[0].text
    assert "error" in text
    assert "Modelo no configurado" in text

@pytest.mark.asyncio
async def test_db_error(mcp_client: Client):
    with patch(
        "tools.get_task_status.get_task", new_callable=AsyncMock, side_effect=Exception("connection timeout"),
    ):
        with pytest.raises(ToolError, match="Error al consultar estado"):
            await mcp_client.call_tool(
                "get_task_status", arguments={"task_id": TASK_ID}
            )
