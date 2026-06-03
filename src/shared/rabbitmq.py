"""Async RabbitMQ utilities using aio-pika."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Awaitable

import aio_pika
from aio_pika import ExchangeType, Message, DeliveryMode

from shared.telemetry import extract_context, get_tracer

logger = logging.getLogger("[SHARED]")

EXCHANGE_NAME = "task_exchange"
TASK_DISPATCH_QUEUE = "task_dispatch_queue"
AGENT_REGISTRY_EVENTS_QUEUE = "agent_registry_events"
AGENT_GATEWAY_EVENTS_QUEUE = "agent_gateway_events"

async def create_connection(rabbitmq_url: str) -> aio_pika.RobustConnection:
    """Create a robust RabbitMQ connection with auto-reconnect."""
    connection = await aio_pika.connect_robust(rabbitmq_url)
    logger.info("RabbitMQ connection established")
    return connection

async def setup_infrastructure(
    channel: aio_pika.Channel,
) -> tuple[aio_pika.Exchange, aio_pika.Queue, aio_pika.Queue]:
    """Declare exchange, queues, and bindings. Returns (exchange, task_queue, events_queue)."""
    exchange = await channel.declare_exchange(
        EXCHANGE_NAME,
        ExchangeType.DIRECT,
        durable=True,
    )

    task_queue = await channel.declare_queue(
        TASK_DISPATCH_QUEUE,
        durable=True,
    )
    await task_queue.bind(exchange, routing_key=TASK_DISPATCH_QUEUE)

    events_queue = await channel.declare_queue(
        AGENT_REGISTRY_EVENTS_QUEUE,
        durable=True,
    )
    await events_queue.bind(exchange, routing_key=AGENT_REGISTRY_EVENTS_QUEUE)

    logger.info(
        "RabbitMQ infrastructure ready: exchange=%s, queues=[%s, %s]",
        EXCHANGE_NAME,
        TASK_DISPATCH_QUEUE,
        AGENT_REGISTRY_EVENTS_QUEUE,
    )
    return exchange, task_queue, events_queue

async def publish_message(
    exchange: aio_pika.Exchange,
    routing_key: str,
    body: dict,
    trace_headers: dict | None = None,
) -> None:
    """Publish a JSON message to the exchange with a routing key.

    When *trace_headers* is provided, they are included as AMQP message
    headers so that consumers can extract the W3C TraceContext and
    continue the distributed trace.
    """
    message = Message(
        body=json.dumps(body, default=str).encode(),
        delivery_mode=DeliveryMode.PERSISTENT,
        content_type="application/json",
        headers=trace_headers or {},
    )
    await exchange.publish(message, routing_key=routing_key)
    logger.debug("Published message to %s: %s", routing_key, body.get("event"))

async def consume_agent_events(
    queue: aio_pika.Queue,
    handler: Callable[[dict[str, Any]], Awaitable[None]],
    tracer_name: str,
    span_name: str = "agent.event.process",
) -> None:
    """Consume agent lifecycle events from a RabbitMQ queue.

    Handles JSON parsing, W3C trace context extraction, structured logging,
    and error handling.  The caller only provides the business logic via
    *handler*.

    Args:
        queue: The aio-pika queue to consume from.
        handler: Async callback receiving the parsed event dict.
        tracer_name: OpenTelemetry tracer scope name.
        span_name: Name for the processing span.
    """
    logger.info("Starting agent events listener on queue '%s'", queue.name)
    tracer = get_tracer(tracer_name)
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            async with message.process():
                try:
                    data = json.loads(message.body)

                    msg_headers = dict(message.headers) if message.headers else {}
                    parent_ctx = extract_context(msg_headers)

                    with tracer.start_as_current_span(
                        span_name,
                        context=parent_ctx,
                        attributes={
                            "agent.event": data.get("event", ""),
                            "agent.provider": data.get("provider", ""),
                            "agent.name": data.get("name", ""),
                        },
                    ):
                        logger.info(
                            "Received agent event: %s for %s/%s",
                            data.get("event"),
                            data.get("provider"),
                            data.get("name"),
                        )
                        await handler(data)
                except json.JSONDecodeError as exc:
                    logger.error(
                        "Malformed message body (not valid JSON): %s — %s",
                        message.body[:200],
                        exc,
                    )
                except Exception as exc:
                    logger.error(
                        "Error processing agent event: %s", exc, exc_info=True
                    )
