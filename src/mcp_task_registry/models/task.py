"""Pydantic models for task-related data in MCP Task Registry."""

from __future__ import annotations
from uuid import UUID
from pydantic import BaseModel

class TaskResponse(BaseModel):
    """Response model for task operations."""

    task_id: UUID
    status: str
    message: str | None = None
    response: str | None = None
    error_message: str | None = None
