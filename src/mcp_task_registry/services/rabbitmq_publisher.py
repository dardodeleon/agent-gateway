"""RabbitMQ publisher — publishes new task messages to the dispatch queue."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import aio_pika

from shared.rabbitmq import publish_message, TASK_DISPATCH_QUEUE
from shared.models import NewTaskMessage
from shared.telemetry import get_tracer, inject_context

logger = logging.getLogger("[TASK-REGISTRY]")

async def publish_new_task(
    exchange: aio_pika.Exchange,
    task_id: UUID,
    agent_provider: str,
    agent_name: str,
) -> None:
    """Publish a new_task event to the task_dispatch_queue.

    Uses shared.rabbitmq.publish_message to send a persistent JSON message
    through the task_exchange with the task_dispatch_queue routing key.
    Injects W3C TraceContext headers for distributed tracing.
    """
    tracer = get_tracer("registry.rabbitmq_publisher")

    with tracer.start_as_current_span(
        "task.publish",
        attributes={
            "task.id": str(task_id),
            "agent.provider": agent_provider,
            "agent.name": agent_name,
        },
    ):
        message = NewTaskMessage(
            event="new_task",
            task_id=task_id,
            agent_provider=agent_provider,
            agent_name=agent_name,
            timestamp=datetime.now(timezone.utc),
        )

        trace_headers: dict[str, Any] = {}
        inject_context(trace_headers)

        await publish_message(
            exchange,
            routing_key=TASK_DISPATCH_QUEUE,
            body=message.model_dump(mode="json"),
            trace_headers=trace_headers,
        )

        logger.info(
            "Published new_task event: task_id=%s, agent=%s/%s",
            task_id,
            agent_provider,
            agent_name,
        )
