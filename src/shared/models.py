"""Pydantic models shared across all modules."""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

# --- Enums ---

class AgentStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    INTERNAL = "internal"
    ERROR = "error"

class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    COMPLETED = "completed"
    ERROR = "error"

class MessageRole(str, enum.Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"

# --- Database record models ---

class AgentRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: str
    name: str
    display_name: str | None = None
    description: str | None = None
    tags: list[str] = []
    status: AgentStatus
    config_hash: str | None = None
    registered_at: datetime
    updated_at: datetime

class TaskRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_provider: str
    agent_name: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime

class TaskMessageRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    role: MessageRole
    content: str
    created_at: datetime

# --- RabbitMQ message models ---

class NewTaskMessage(BaseModel):
    event: str = "new_task"
    task_id: UUID
    agent_provider: str
    agent_name: str
    timestamp: datetime

class AgentChangeMessage(BaseModel):
    event: str  # agent_added | agent_removed | agent_updated
    provider: str
    name: str
    display_name: str | None = None
    description: str | None = None
    tags: list[str] = []
    status: str | None = None  # active | inactive | internal
    config_hash: str | None = None
    timestamp: datetime
