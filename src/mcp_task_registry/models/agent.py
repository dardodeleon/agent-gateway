"""Pydantic models for agent-related data in MCP Task Registry."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel

class AgentRecord(BaseModel):
    """Public representation of an agent returned by list_agents."""

    provider: str
    name: str
    display_name: str
    description: str
    tags: list[str]
    status: str  # active | inactive | internal | error
    registered_at: datetime


class AgentListResponse(BaseModel):
    """Response for the list_agents tool."""

    agents: list[AgentRecord]
    total: int
    filter_tag: str | None = None
