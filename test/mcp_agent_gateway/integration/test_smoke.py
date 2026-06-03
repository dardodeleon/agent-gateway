"""Smoke tests for MCP Agent Gateway — requires Docker stack running."""

import pytest
from fastmcp import Client

@pytest.mark.asyncio
@pytest.mark.integration
async def test_smoke_server_tools(mcp_client: Client, server_config):
   
    tools = await mcp_client.list_tools()

    tool_names = {t.name for t in tools}

    expected = set(server_config["expected_tool_names"])
    assert tool_names == expected, (
        f"Missing: {expected - tool_names}, Extra: {tool_names - expected}"
    )

@pytest.mark.asyncio
@pytest.mark.integration
async def test_smoke_send_and_check(mcp_client: Client):

    # Listado de tools
    tools = await mcp_client.list_tools()
    send_tool = next(t for t in tools if t.name == "send_task")

    # Agentes asociados al parametro agent_name
    agent_name_prop = send_tool.inputSchema["properties"]["agent_name"]
    enum_values = agent_name_prop.get("enum", [])
    assert len(enum_values) > 0, "Sin agentes en el enum agent_name"

    # Verifica que existe al menos un agente cómo valor para agent_name
    valid_agents = [v for v in enum_values if v != "NO_AGENTS"]
    assert len(valid_agents) > 0, "No hay agentes activos para el enum agent_name"

    agent = valid_agents[0]

    # Envía una tarea y verifica que fue aceptada
    send_result = await mcp_client.call_tool(
        "send_task",
        arguments={
            "agent_name": agent,
            "task_text": "Smoke test: Hola desde pytest",
        },
    )
    send_text = send_result.content[0].text
    assert any(
        s in send_text for s in ("Tarea completada", "exitosamente", "Tarea enviada")
    ), f"Unexpected send_task response: {send_text[:200]}"
