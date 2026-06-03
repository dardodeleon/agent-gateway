import pytest
from fastmcp import Client

@pytest.mark.asyncio
async def test_server_tools_count(mcp_client: Client, server_config):
    tools = await mcp_client.list_tools()

    expected = server_config["expected_tool_names"]

    assert len(tools) == len(expected), f"Expected {len(expected)} tools, got {len(tools)}: {[t.name for t in tools]}"

@pytest.mark.asyncio
async def test_server_tool_names(mcp_client: Client, server_config):
    tools = await mcp_client.list_tools()

    tool_names = {t.name for t in tools}

    expected = set(server_config["expected_tool_names"])

    assert tool_names == expected, (
        f"Missing: {expected - tool_names}, Extra: {tool_names - expected}"
    )
