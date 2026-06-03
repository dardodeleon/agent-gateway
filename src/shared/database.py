"""Async PostgreSQL database utilities using asyncpg."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

import asyncpg

DEFAULT_DATABASE_URL = (
    "postgresql://dispatcher:dispatcher_secret@localhost:5432/task_dispatcher"
)

logger = logging.getLogger("[SHARED]")

# --- Pool management ---

async def create_pool(database_url: str, **kwargs) -> asyncpg.Pool:
    """Create an asyncpg connection pool."""
    pool = await asyncpg.create_pool(
        database_url,
        min_size=2,
        max_size=10,
        **kwargs,
    )
    logger.info("Database pool created")
    return pool

async def close_pool(pool: asyncpg.Pool) -> None:
    """Close the asyncpg connection pool."""
    await pool.close()
    logger.info("Database pool closed")

# --- Agents CRUD ---

async def get_active_agents(
    pool: asyncpg.Pool,
    tag: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Get active agents, optionally filtered by tag."""
    async with pool.acquire() as conn:
        if tag:
            rows = await conn.fetch(
                """
                SELECT id, provider, name, display_name, description,
                       tags, status, config_hash, registered_at, updated_at
                FROM agents
                WHERE status = 'active' AND tags @> $1::jsonb
                ORDER BY registered_at DESC
                LIMIT $2
                """,
                json.dumps([tag]),
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, provider, name, display_name, description,
                       tags, status, config_hash, registered_at, updated_at
                FROM agents
                WHERE status = 'active'
                ORDER BY registered_at DESC
                LIMIT $1
                """,
                limit,
            )
    return [_record_to_dict(r) for r in rows]

async def get_agent(
    pool: asyncpg.Pool, provider: str, name: str
) -> dict | None:
    """Get a single agent by provider and name."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, provider, name, display_name, description,
                   tags, status, config_hash, registered_at, updated_at
            FROM agents
            WHERE provider = $1 AND name = $2
            """,
            provider,
            name,
        )
    return _record_to_dict(row) if row else None

async def upsert_agent(
    pool: asyncpg.Pool,
    provider: str,
    name: str,
    display_name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    config_hash: str | None = None,
    status: str = "active",
) -> dict:
    """Insert or update an agent record."""
    tags_json = json.dumps(tags or [])
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO agents (provider, name, display_name, description, tags, status, config_hash)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
            ON CONFLICT (provider, name)
            DO UPDATE SET
                display_name = EXCLUDED.display_name,
                description = EXCLUDED.description,
                tags = EXCLUDED.tags,
                status = EXCLUDED.status,
                config_hash = EXCLUDED.config_hash,
                updated_at = NOW()
            RETURNING id, provider, name, display_name, description,
                      tags, status, config_hash, registered_at, updated_at
            """,
            provider,
            name,
            display_name,
            description,
            tags_json,
            status,
            config_hash,
        )
    return _record_to_dict(row)

async def update_agent_status(
    pool: asyncpg.Pool,
    provider: str,
    name: str,
    status: str,
) -> dict | None:
    """Update the status of an agent."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE agents
            SET status = $3, updated_at = NOW()
            WHERE provider = $1 AND name = $2
            RETURNING id, provider, name, display_name, description,
                      tags, status, config_hash, registered_at, updated_at
            """,
            provider,
            name,
            status,
        )
    return _record_to_dict(row) if row else None

async def deactivate_agents_not_in_set(
    pool: asyncpg.Pool,
    active_set: set[tuple[str, str]],
) -> list[dict]:
    """Mark as inactive all active agents whose (provider, name) is NOT in *active_set*.

    Returns the list of agents that were deactivated.
    """
    async with pool.acquire() as conn:
        # Fetch all non-inactive agents (active + internal)
        rows = await conn.fetch(
            """
            SELECT id, provider, name, display_name, description,
                   tags, status, config_hash, registered_at, updated_at
            FROM agents
            WHERE status IN ('active', 'internal')
            """
        )

        deactivated: list[dict] = []
        for row in rows:
            if (row["provider"], row["name"]) not in active_set:
                updated = await conn.fetchrow(
                    """
                    UPDATE agents
                    SET status = 'inactive', updated_at = NOW()
                    WHERE id = $1
                    RETURNING id, provider, name, display_name, description,
                              tags, status, config_hash, registered_at, updated_at
                    """,
                    row["id"],
                )
                if updated:
                    deactivated.append(_record_to_dict(updated))

    return deactivated

async def get_all_tags(pool: asyncpg.Pool) -> list[dict]:
    """Get all distinct tags from active agents with usage counts."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT tag, COUNT(*) as agent_count
            FROM agents, jsonb_array_elements_text(tags) AS tag
            WHERE status = 'active'
            GROUP BY tag
            ORDER BY agent_count DESC, tag ASC
            """
        )
    return [dict(r) for r in rows]

async def get_agents_by_provider(
    pool: asyncpg.Pool,
    provider: str,
    statuses: tuple[str, ...] = ("active", "internal"),
) -> list[dict]:
    """Get agents for a specific provider filtered by statuses."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, provider, name, display_name, description,
                   tags, status, config_hash, registered_at, updated_at
            FROM agents
            WHERE provider = $1 AND status = ANY($2::text[])
            ORDER BY registered_at DESC
            """,
            provider,
            list(statuses),
        )
    return [_record_to_dict(r) for r in rows]

# --- Tasks CRUD ---

async def create_task(
    pool: asyncpg.Pool,
    task_id: uuid.UUID,
    agent_provider: str,
    agent_name: str,
    initial_message: str,
) -> dict:
    """Create a task and its initial user message in a transaction."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO tasks (id, agent_provider, agent_name, status)
                VALUES ($1, $2, $3, 'pending')
                RETURNING id, agent_provider, agent_name, status, created_at, updated_at
                """,
                task_id,
                agent_provider,
                agent_name,
            )
            await conn.execute(
                """
                INSERT INTO task_messages (task_id, role, content)
                VALUES ($1, 'user', $2)
                """,
                task_id,
                initial_message,
            )
    return _record_to_dict(row)

async def get_task(pool: asyncpg.Pool, task_id: uuid.UUID) -> dict | None:
    """Get a single task by ID."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, agent_provider, agent_name, status, created_at, updated_at
            FROM tasks WHERE id = $1
            """,
            task_id,
        )
    return _record_to_dict(row) if row else None


async def assign_task(pool: asyncpg.Pool, task_id: uuid.UUID) -> dict | None:
    """Atomically assign a task (pending -> assigned). Returns None if already taken."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE tasks
            SET status = 'assigned', updated_at = NOW()
            WHERE id = $1 AND status = 'pending'
            RETURNING id, agent_provider, agent_name, status, created_at, updated_at
            """,
            task_id,
        )
    return _record_to_dict(row) if row else None

async def submit_response(
    pool: asyncpg.Pool,
    task_id: uuid.UUID,
    response_text: str,
    is_error: bool = False,
) -> dict | None:
    """Submit agent response and mark task completed/error. Transactional."""
    new_status = "error" if is_error else "completed"
    role = "system" if is_error else "agent"

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                UPDATE tasks
                SET status = $2, updated_at = NOW()
                WHERE id = $1 AND status = 'assigned'
                RETURNING id, agent_provider, agent_name, status, created_at, updated_at
                """,
                task_id,
                new_status,
            )
            if row:
                await conn.execute(
                    """
                    INSERT INTO task_messages (task_id, role, content)
                    VALUES ($1, $2, $3)
                    """,
                    task_id,
                    role,
                    response_text,
                )
    return _record_to_dict(row) if row else None

async def update_task_status(
    pool: asyncpg.Pool,
    task_id: uuid.UUID,
    status: str,
) -> dict | None:
    """Generic task status update."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE tasks SET status = $2, updated_at = NOW()
            WHERE id = $1
            RETURNING id, agent_provider, agent_name, status, created_at, updated_at
            """,
            task_id,
            status,
        )
    return _record_to_dict(row) if row else None

# --- Task Messages CRUD ---

async def create_message(
    pool: asyncpg.Pool,
    task_id: uuid.UUID,
    role: str,
    content: str,
) -> dict:
    """Insert a new task message."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO task_messages (task_id, role, content)
            VALUES ($1, $2, $3)
            RETURNING id, task_id, role, content, created_at
            """,
            task_id,
            role,
            content,
        )
    return _record_to_dict(row)

async def get_task_messages(
    pool: asyncpg.Pool, task_id: uuid.UUID
) -> list[dict]:
    """Get all messages for a task, ordered chronologically."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, task_id, role, content, created_at
            FROM task_messages
            WHERE task_id = $1
            ORDER BY created_at ASC
            """,
            task_id,
        )
    return [_record_to_dict(r) for r in rows]

async def get_last_message_by_role(
    pool: asyncpg.Pool,
    task_id: uuid.UUID,
    role: str,
) -> dict | None:
    """Get the most recent message with a given role for a task."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, task_id, role, content, created_at
            FROM task_messages
            WHERE task_id = $1 AND role = $2
            ORDER BY created_at DESC
            LIMIT 1
            """,
            task_id,
            role,
        )
    return _record_to_dict(row) if row else None

# --- Helpers ---

def _record_to_dict(record: asyncpg.Record) -> dict:
    """Convert an asyncpg Record to a plain dict, handling JSONB fields."""
    d = dict(record)
    # asyncpg returns JSONB as str; parse it
    if "tags" in d and isinstance(d["tags"], str):
        d["tags"] = json.loads(d["tags"])
    return d
