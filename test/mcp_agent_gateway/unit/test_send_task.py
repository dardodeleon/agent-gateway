import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

ACTIVE_AGENT = {"provider": "custom", "name": "calculator", "status": "active"}
INACTIVE_AGENT = {"provider": "custom", "name": "calculator", "status": "inactive"}
INTERNAL_AGENT = {"provider": "custom", "name": "calculator", "status": "internal"}

@pytest.mark.asyncio
async def test_send_task_no_wait(mcp_client: Client):
    """Returns immediately with task ID when wait=False."""
    with (
        patch("tools.send_task.get_agent", new_callable=AsyncMock, return_value=ACTIVE_AGENT),
        patch("tools.send_task.create_task", new_callable=AsyncMock),
        patch("tools.send_task.publish_message", new_callable=AsyncMock),
    ):
        result = await mcp_client.call_tool(
            "send_task",
            arguments={
                "agent_name": "custom/calculator",
                "task_text": "Cuanto es 2+2?",
                "wait": False,
            },
        )

    text = result.content[0].text
    assert "exitosamente" in text
    assert "custom/calculator" in text
    # Extract and validate UUID from response text
    parts = text.split("ID ")
    assert len(parts) == 2
    uuid.UUID(parts[1]) 

@pytest.mark.asyncio
async def test_send_task_agent_not_found(mcp_client: Client):
    with patch("tools.send_task.get_agent", new_callable=AsyncMock, return_value=None):
        with pytest.raises(ToolError, match="no existe"):
            await mcp_client.call_tool(
                "send_task",
                arguments={
                    "agent_name": "custom/calculator",
                    "task_text": "test",
                    "wait": False,
                },
            )

@pytest.mark.asyncio
async def test_send_task_agent_inactive(mcp_client: Client):
    with patch("tools.send_task.get_agent", new_callable=AsyncMock, return_value=INACTIVE_AGENT):
        with pytest.raises(ToolError, match="no está activo"):
            await mcp_client.call_tool(
                "send_task",
                arguments={
                    "agent_name": "custom/calculator",
                    "task_text": "test",
                    "wait": False,
                },
            )

@pytest.mark.asyncio
async def test_send_task_agent_internal(mcp_client: Client):
    with patch("tools.send_task.get_agent", new_callable=AsyncMock, return_value=INTERNAL_AGENT):
        with pytest.raises(ToolError, match="interno"):
            await mcp_client.call_tool(
                "send_task",
                arguments={
                    "agent_name": "custom/calculator",
                    "task_text": "test",
                    "wait": False,
                },
            )

@pytest.mark.asyncio
async def test_send_task_db_error_on_create(mcp_client: Client):
    with (
        patch("tools.send_task.get_agent", new_callable=AsyncMock, return_value=ACTIVE_AGENT),
        patch("tools.send_task.create_task", new_callable=AsyncMock, side_effect=Exception("db write error"),),
    ):
        with pytest.raises(ToolError, match="Error al crear tarea"):
            await mcp_client.call_tool(
                "send_task",
                arguments={
                    "agent_name": "custom/calculator",
                    "task_text": "test",
                    "wait": False,
                },
            )

@pytest.mark.asyncio
async def test_send_task_rmq_publish_failure(mcp_client: Client):
    with (
        patch("tools.send_task.get_agent", new_callable=AsyncMock, return_value=ACTIVE_AGENT),
        patch("tools.send_task.create_task", new_callable=AsyncMock),
        patch("tools.send_task.publish_message", new_callable=AsyncMock, side_effect=Exception("connection lost"),),
        patch("tools.send_task.update_task_status", new_callable=AsyncMock),
        patch("tools.send_task.create_message", new_callable=AsyncMock),
    ):
        with pytest.raises(ToolError, match="cola de mensajes"):
            await mcp_client.call_tool(
                "send_task",
                arguments={
                    "agent_name": "custom/calculator",
                    "task_text": "test",
                    "wait": False,
                },
            )

# ---------------------------------------------------------------------------
# wait=True tests (polling)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_task_wait_completed(mcp_client: Client):

    agent_msg = {"content": "La respuesta es 4."}

    with (
        patch("tools.send_task.get_agent", new_callable=AsyncMock, return_value=ACTIVE_AGENT),
        patch("tools.send_task.create_task", new_callable=AsyncMock),
        patch("tools.send_task.publish_message", new_callable=AsyncMock),
        patch("tools.send_task.asyncio.sleep", new_callable=AsyncMock),
        patch("tools.send_task.get_task", new_callable=AsyncMock, return_value={"status": "completed"}),
        patch("tools.send_task.get_last_message_by_role", new_callable=AsyncMock, return_value=agent_msg),
    ):
        result = await mcp_client.call_tool(
            "send_task",
            arguments={
                "agent_name": "custom/calculator",
                "task_text": "Cuanto es 2+2?",
                "wait": True,
            },
        )

    text = result.content[0].text
    assert len(text) > 0
    assert "La respuesta es 4." in text

@pytest.mark.asyncio
async def test_send_task_wait_error(mcp_client: Client):

    system_msg = {"content": "Modelo no disponible"}

    with (
        patch("tools.send_task.get_agent", new_callable=AsyncMock, return_value=ACTIVE_AGENT),
        patch("tools.send_task.create_task", new_callable=AsyncMock),
        patch("tools.send_task.publish_message", new_callable=AsyncMock),
        patch("tools.send_task.asyncio.sleep", new_callable=AsyncMock),
        patch("tools.send_task.get_task", new_callable=AsyncMock, return_value={"status": "error"}),
        patch("tools.send_task.get_last_message_by_role", new_callable=AsyncMock, return_value=system_msg),
    ):
        with pytest.raises(ToolError, match="falló"):
            await mcp_client.call_tool(
                "send_task",
                arguments={
                    "agent_name": "custom/calculator",
                    "task_text": "test",
                    "wait": True,
                },
            )

@pytest.mark.asyncio
async def test_send_task_wait_timeout(mcp_client: Client, monkeypatch):

    monkeypatch.setenv("SEND_TASK_WAIT_TIMEOUT", "0.1")
    monkeypatch.setenv("SEND_TASK_POLL_INTERVAL", "0.05")

    with (
        patch("tools.send_task.get_agent", new_callable=AsyncMock, return_value=ACTIVE_AGENT),
        patch("tools.send_task.create_task", new_callable=AsyncMock),
        patch("tools.send_task.publish_message", new_callable=AsyncMock),
        patch("tools.send_task.get_task", new_callable=AsyncMock, return_value={"status": "pending"}),
    ):
        result = await mcp_client.call_tool(
            "send_task",
            arguments={
                "agent_name": "custom/calculator",
                "task_text": "test",
                "wait": True,
            },
        )

    text = result.content[0].text
    assert len(text) > 0
    assert "get_task_status" in text
