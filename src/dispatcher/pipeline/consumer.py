"""RabbitMQ task consumer — listens on task_dispatch_queue.

Consumes ``new_task`` messages, loads the target agent configuration,
creates a Strands agent via AgentFactory, runs it with AgentRunner,
and submits the result back through DispatchClient.

Each message is explicitly ACKed or NACKed — never left unacknowledged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from uuid import UUID

import aio_pika

from opentelemetry import trace, context

from agent_core import AgentFactory
from agent_core.runner import AgentRunner, AgentResult
from config import (
    AgentConfig,
    ModelsConfig,
    ConfigError,
    load_agent_config,
    validate_agent_dependencies,
)
from pipeline.client import DispatchClient
from shared.rabbitmq import TASK_DISPATCH_QUEUE
from shared.telemetry import extract_context, get_meter, get_tracer

logger = logging.getLogger("[DISPATCHER]")

_meter = get_meter("dispatcher.consumer")
_tasks_processed = _meter.create_counter(
    "dispatcher.tasks.processed",
    description="Total tasks processed by the dispatcher",
)
_task_duration = _meter.create_histogram(
    "dispatcher.tasks.processing.duration_ms",
    description="Task processing duration in milliseconds",
    unit="ms",
)

class TaskConsumer:
    """Consumes tasks from RabbitMQ and orchestrates agent execution."""

    def __init__(
        self,
        channel: aio_pika.Channel,
        dispatch_client: DispatchClient,
        agent_factory: AgentFactory,
        models_config: ModelsConfig,
        agents_dir: str = "/app/agents",
    ) -> None:
        self.channel = channel
        self.dispatch_client = dispatch_client
        self.agent_factory = agent_factory
        self.models_config = models_config
        self.agents_dir = agents_dir
        self.runner = AgentRunner()

        # Concurrency control
        prefetch = int(os.environ.get("DISPATCHER_PREFETCH", "1"))
        self.prefetch = max(1, prefetch)
        self.semaphore = asyncio.Semaphore(self.prefetch)
        self._stop_event = asyncio.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Declare queue, configure QoS, and start consuming messages."""
        await self.channel.set_qos(prefetch_count=self.prefetch)

        queue = await self.channel.declare_queue(
            TASK_DISPATCH_QUEUE, durable=True
        )

        logger.info(
            "Consumer started on queue '%s' (prefetch=%d)",
            TASK_DISPATCH_QUEUE,
            self.prefetch,
        )

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                if self._stop_event.is_set():
                    break
                # Process in the background so the iterator can keep
                # pulling messages up to the prefetch limit.
                asyncio.create_task(self._safe_process(message))

    async def stop(self) -> None:
        """Signal the consumer to stop after finishing current work."""
        logger.info("Consumer stop requested")
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    async def _safe_process(self, message: aio_pika.IncomingMessage) -> None:
        """Wrapper that ensures every message is ACKed or NACKed."""
        async with self.semaphore:
            try:
                await self._process_message(message)
                await message.ack()
            except Exception as exc:
                logger.error(
                    "Unexpected error processing message: %s",
                    exc,
                    exc_info=True,
                )
                await message.nack(requeue=False)

    async def _process_message(
        self, message: aio_pika.IncomingMessage
    ) -> None:
        """Full task processing pipeline.

        1. Parse JSON payload
        2. Validate agent directory
        3. Assign task via DispatchClient
        4. Retrieve task messages
        5. Load agent config, create agent
        6. Execute agent with timeout
        7. Submit response
        """
        # --- 1. Parse message ---
        try:
            body = json.loads(message.body)
        except json.JSONDecodeError as exc:
            logger.error("Malformed message body: %s", exc)
            return

        task_id_str: str = body.get("task_id", "")
        agent_provider: str = body.get("agent_provider", "")
        agent_name: str = body.get("agent_name", "")

        try:
            task_id = UUID(task_id_str)
        except (ValueError, AttributeError):
            logger.error("Invalid task_id in message: '%s'", task_id_str)
            return

        log_prefix = f"[task={task_id} agent={agent_provider}/{agent_name}]"
        logger.info("%s Processing task", log_prefix)

        # Extract trace context from RabbitMQ message headers
        msg_headers = dict(message.headers) if message.headers else {}
        parent_ctx = extract_context(msg_headers)
        tracer = get_tracer("dispatcher.consumer")

        with tracer.start_as_current_span(
            "task.process",
            context=parent_ctx,
            attributes={
                "task.id": str(task_id),
                "agent.provider": agent_provider,
                "agent.name": agent_name,
            },
        ) as span:
            await self._process_task(
                span, task_id, agent_provider, agent_name, log_prefix
            )

    async def _process_task(
        self,
        span: trace.Span,
        task_id: UUID,
        agent_provider: str,
        agent_name: str,
        log_prefix: str,
    ) -> None:
        """Inner task processing with tracing spans."""
        tracer = get_tracer("dispatcher.consumer")
        t_start = time.monotonic()

        # --- 2. Validate agent directory ---
        agent_dir = os.path.join(
            self.agents_dir, agent_provider, agent_name
        )
        config_path = os.path.join(agent_dir, "agent.yml")

        if not os.path.isfile(config_path):
            error_msg = (
                f"Agente '{agent_provider}/{agent_name}' no encontrado "
                f"en el directorio de agentes"
            )
            logger.error("%s %s", log_prefix, error_msg)
            span.set_attribute("error", True)
            span.add_event("agent_not_found")
            # Try to assign first so we can submit the error response
            await self.dispatch_client.assign_task(task_id)
            await self.dispatch_client.submit_response(
                task_id, error_msg, is_error=True
            )
            return

        # --- 3. Assign task ---
        with tracer.start_as_current_span("task.assign"):
            assigned = await self.dispatch_client.assign_task(task_id)
        if not assigned:
            logger.warning(
                "%s Task could not be assigned (already taken or not pending)",
                log_prefix,
            )
            span.add_event("task_already_taken")
            return

        # --- 4. Get task messages ---
        with tracer.start_as_current_span("task.get_messages"):
            messages = await self.dispatch_client.get_task_messages(task_id)
        if not messages:
            logger.warning(
                "%s No messages found for task", log_prefix
            )

        # --- 5. Load agent config and create agent ---
        try:
            agent_config = load_agent_config(agent_dir)
        except ConfigError as exc:
            error_msg = (
                f"Configuración inválida para agente "
                f"'{agent_provider}/{agent_name}': {exc}"
            )
            logger.error("%s %s", log_prefix, error_msg)
            span.set_attribute("error", True)
            span.add_event("config_error", {"error": str(exc)})
            await self.dispatch_client.submit_response(
                task_id, error_msg, is_error=True
            )
            return

        # Defense-in-depth: reject agents that shouldn't receive direct tasks
        if agent_config.status != "active":
            if agent_config.status == "internal":
                error_msg = (
                    f"Agente '{agent_provider}/{agent_name}' es interno y no acepta "
                    f"tareas directas (status: internal)"
                )
            else:
                error_msg = (
                    f"Agente '{agent_provider}/{agent_name}' no esta activo "
                    f"(status: {agent_config.status})"
                )
            logger.error("%s %s", log_prefix, error_msg)
            span.set_attribute("error", True)
            await self.dispatch_client.submit_response(
                task_id, error_msg, is_error=True
            )
            return

        # Validate dependencies
        dep_errors = validate_agent_dependencies(
            agent_config,
            self.models_config,
            tools_base=self.agent_factory.tools_base,
            skills_base=self.agent_factory.skills_base,
            agents_base=self.agent_factory.agents_base,
        )
        if dep_errors:
            error_msg = (
                f"Dependencias inválidas para agente "
                f"'{agent_provider}/{agent_name}': "
                + "; ".join(dep_errors)
            )
            logger.error("%s %s", log_prefix, error_msg)
            span.set_attribute("error", True)
            await self.dispatch_client.submit_response(
                task_id, error_msg, is_error=True
            )
            return

        # --- 5b. Create agent, swarm, or orchestrator with delegates ---
        is_swarm = agent_config.swarm is not None
        has_delegates = agent_config.delegates is not None

        try:
            if is_swarm:
                runnable = self.agent_factory.create_swarm(
                    agent_config,
                    parent_provider=agent_provider,
                    parent_name=agent_name,
                )
                logger.info("%s Created swarm with %d sub-agents", log_prefix, len(agent_config.swarm.agents))
            elif has_delegates:
                runnable = self.agent_factory.create_agent_with_delegates(
                    agent_config,
                    parent_provider=agent_provider,
                    parent_name=agent_name,
                )
                logger.info("%s Created agent with %d delegates", log_prefix, len(agent_config.delegates.agents))
            else:
                runnable = self.agent_factory.create_agent(agent_config)
        except Exception as exc:
            if is_swarm:
                label = "swarm"
            elif has_delegates:
                label = "agente con delegados"
            else:
                label = "agente"
            error_msg = (
                f"Error creando {label} '{agent_provider}/{agent_name}': {exc}"
            )
            logger.error("%s %s", log_prefix, error_msg, exc_info=True)
            span.set_attribute("error", True)
            await self.dispatch_client.submit_response(
                task_id, error_msg, is_error=True
            )
            return

        # --- 6. Run agent or swarm ---
        timeout = int(
            os.environ.get(
                "TASK_TIMEOUT_SECONDS",
                str(agent_config.timeout_seconds),
            )
        )

        if is_swarm:
            logger.info(
                "%s Executing swarm (timeout=%ds)", log_prefix, timeout
            )
            result: AgentResult = await self.runner.run_swarm(
                runnable,
                messages,
                timeout_seconds=timeout,
                agent_provider=agent_provider,
                agent_name=agent_name,
            )
        else:
            exec_label = "agent with delegates" if has_delegates else "agent"
            logger.info(
                "%s Executing %s (timeout=%ds)", log_prefix, exec_label, timeout
            )
            result: AgentResult = await self.runner.run(
                runnable,
                messages,
                timeout_seconds=timeout,
                agent_provider=agent_provider,
                agent_name=agent_name,
            )

        # --- 7. Submit response ---
        if result.is_error:
            logger.error(
                "%s Agent execution failed: %s",
                log_prefix,
                result.response_text[:200],
            )
            span.set_attribute("error", True)
            span.add_event("agent_error", {"error": result.response_text[:200]})
        else:
            logger.info("%s Agent execution succeeded", log_prefix)
            span.add_event("agent_success")

        with tracer.start_as_current_span("task.submit_response"):
            await self.dispatch_client.submit_response(
                task_id, result.response_text, is_error=result.is_error
            )

        # Record metrics
        duration_ms = (time.monotonic() - t_start) * 1000
        attrs = {
            "agent.provider": agent_provider,
            "agent.name": agent_name,
            "status": "error" if result.is_error else "completed",
        }
        _tasks_processed.add(1, attrs)
        _task_duration.record(duration_ms, attrs)

        logger.info("%s Task processing complete", log_prefix)
