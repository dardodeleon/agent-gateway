"""Dispatch client — thin wrapper over shared.database for task operations.

Uses direct database access for task workflow operations (assign, get
messages, submit response, update agent status).
"""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg

from shared import database

logger = logging.getLogger("[DISPATCHER]")

class DispatchClient:
    """Facade over shared.database for the dispatcher's task workflow."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def assign_task(self, task_id: UUID) -> dict | None:
        """Atomically transition a task from pending to assigned.

        Returns the updated task dict, or ``None`` if the task was
        already taken or does not exist.
        """
        result = await database.assign_task(self.pool, task_id)
        if result:
            logger.info("Task %s assigned successfully", task_id)
        else:
            logger.warning(
                "Task %s could not be assigned (not pending or not found)",
                task_id,
            )
        return result

    async def get_task_messages(self, task_id: UUID) -> list[dict]:
        """Retrieve all messages for a task in chronological order."""
        messages = await database.get_task_messages(self.pool, task_id)
        logger.debug(
            "Retrieved %d message(s) for task %s",
            len(messages),
            task_id,
        )
        return messages

    async def submit_response(
        self,
        task_id: UUID,
        response_text: str,
        is_error: bool = False,
    ) -> dict | None:
        """Submit the agent's response and mark the task completed/error.

        Returns the updated task dict, or ``None`` if the task was not
        in ``assigned`` state.
        """
        result = await database.submit_response(
            self.pool, task_id, response_text, is_error=is_error
        )
        status = "error" if is_error else "completed"
        if result:
            logger.info("Task %s marked as %s", task_id, status)
        else:
            logger.warning(
                "Task %s could not be updated to %s (not in assigned state)",
                task_id,
                status,
            )
        return result

    async def update_agent_status(
        self,
        provider: str,
        name: str,
        status: str,
        reason: str = "",
    ) -> dict | None:
        """Update the status of a registered agent.

        Returns the updated agent dict, or ``None`` if the agent was
        not found.
        """
        result = await database.update_agent_status(
            self.pool, provider, name, status
        )
        if result:
            logger.info(
                "Agent %s/%s status -> %s%s",
                provider,
                name,
                status,
                f" (reason: {reason})" if reason else "",
            )
        else:
            logger.warning("Agent %s/%s not found for status update", provider, name)
        return result
