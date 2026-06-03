"""Agent registry service — queries and event handling for agents table."""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

from shared.database import get_active_agents, upsert_agent, update_agent_status
from models.agent import AgentRecord, AgentListResponse

logger = logging.getLogger("[TASK-REGISTRY]")

async def list_agents(
    pool: asyncpg.Pool,
    tag: str | None = None,
    limit: int = 10,
) -> AgentListResponse:
    """Query active agents, optionally filtered by tag.

    Uses shared.database.get_active_agents which handles the JSONB @>
    operator for tag filtering.
    """
    rows = await get_active_agents(pool, tag=tag, limit=limit)

    agents = [
        AgentRecord(
            provider=row["provider"],
            name=row["name"],
            display_name=row.get("display_name") or "",
            description=row.get("description") or "",
            tags=row.get("tags", []),
            status=row["status"],
            registered_at=row["registered_at"],
        )
        for row in rows
    ]

    return AgentListResponse(
        agents=agents,
        total=len(agents),
        filter_tag=tag,
    )

async def handle_agent_event(
    pool: asyncpg.Pool,
    event_data: dict[str, Any],
) -> None:
    """Process an agent lifecycle event received from RabbitMQ.

    Supported events:
    - agent_added: upsert the agent with status='active'.
    - agent_removed: set agent status to 'inactive'.
    - agent_updated: upsert the agent with new tags/config_hash.
    """
    event = event_data.get("event")
    provider = event_data.get("provider")
    name = event_data.get("name")

    if not event or not provider or not name:
        logger.warning(
            "Ignoring malformed agent event — missing required fields: %s",
            event_data,
        )
        return

    if event == "agent_added":
        result = await upsert_agent(
            pool,
            provider=provider,
            name=name,
            display_name=event_data.get("display_name"),
            description=event_data.get("description"),
            tags=event_data.get("tags", []),
            config_hash=event_data.get("config_hash"),
            status=event_data.get("status", "active"),
        )
        logger.info(
            "Agent added/updated: %s/%s (id=%s)",
            provider,
            name,
            result.get("id"),
        )

    elif event == "agent_removed":
        result = await update_agent_status(pool, provider, name, "inactive")
        if result:
            logger.info("Agent removed (set inactive): %s/%s", provider, name)
        else:
            logger.warning(
                "Agent not found for removal: %s/%s", provider, name
            )

    elif event == "agent_updated":
        result = await upsert_agent(
            pool,
            provider=provider,
            name=name,
            display_name=event_data.get("display_name"),
            description=event_data.get("description"),
            tags=event_data.get("tags", []),
            config_hash=event_data.get("config_hash"),
            status=event_data.get("status", "active"),
        )
        logger.info(
            "Agent updated: %s/%s (id=%s)",
            provider,
            name,
            result.get("id"),
        )

    else:
        logger.warning("Unknown agent event type '%s': %s", event, event_data)
