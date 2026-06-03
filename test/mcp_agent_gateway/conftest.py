import pytest_asyncio
from fastmcp import Client

@pytest_asyncio.fixture()
async def mcp_client(server_config):
    async with Client(server_config["url"]) as client:
        yield client