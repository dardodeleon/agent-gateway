"""Filesystem watcher for the agents/ directory.

Uses the ``watchdog`` library to monitor the agents/ directory tree for
changes (creation, modification, deletion of agent.yml files) and
publishes ``agent_added``, ``agent_updated``, or ``agent_removed``
events to the ``agent_registry_events`` RabbitMQ queue.

Because watchdog runs callbacks in its own thread, we bridge events to
the asyncio event loop via ``asyncio.run_coroutine_threadsafe``.

A 2-second debounce window per ``{provider}/{name}`` path prevents
duplicate notifications when files are copied or saved multiple times
in quick succession.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any

import aio_pika
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from config import (
    AgentConfig,
    ConfigError,
    ModelsConfig,
    compute_config_hash,
    load_agent_config,
    validate_agent_dependencies,
)
from shared.database import (
    deactivate_agents_not_in_set,
    get_active_agents,
    get_agents_by_provider,
    update_agent_status,
    upsert_agent,
)
from shared.rabbitmq import AGENT_REGISTRY_EVENTS_QUEUE, publish_message
from shared.telemetry import get_meter, get_tracer, inject_context

logger = logging.getLogger("[DISPATCHER]")

_meter = get_meter("dispatcher.watcher")
_agent_events = _meter.create_counter(
    "dispatcher.agent.events",
    description="Agent lifecycle events (added, updated, removed)",
)

# Debounce window in seconds
DEBOUNCE_SECONDS = 2.0

class AgentWatcher:
    """Watch the agents/ directory and publish lifecycle events."""

    def __init__(
        self,
        agents_dir: str,
        models_config: ModelsConfig,
        exchange: aio_pika.Exchange,
        db_pool: Any,
        loop: asyncio.AbstractEventLoop | None = None,
        tools_base: str = "/app/tools",
        skills_base: str = "/app/skills",
    ) -> None:
        self.agents_dir = os.path.abspath(agents_dir)
        self.models_config = models_config
        self.exchange = exchange
        self.db_pool = db_pool
        self.loop = loop
        self.tools_base = tools_base
        self.skills_base = skills_base

        self._observer: Observer | None = None
        self._stop_event = asyncio.Event()

        # Use polling observer to detect changes in Docker bind-mounted
        # volumes.  inotify (the default Observer backend) does NOT receive
        # events for modifications made on the host because the kernel
        # events are generated on the host's filesystem, not inside the
        # container.  PollingObserver periodically stats files instead,
        # which works reliably with bind mounts.
        self._use_polling = os.environ.get(
            "WATCHER_USE_POLLING", "true"
        ).lower() in ("1", "true", "yes")
        self._poll_interval = int(
            os.environ.get("WATCHER_POLL_INTERVAL", "5")
        )

        # Debounce state: {agent_key: scheduled_time}
        self._debounce_lock = Lock()
        self._debounce_timers: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Initial scan
    # ------------------------------------------------------------------

    async def initial_scan(self) -> None:
        """Walk agents/ and publish agent_added for each valid agent.

        After registering all agents found on disk, any agent that is
        still marked as ``active`` in the database but was **not** found
        during this scan is set to ``inactive`` and an ``agent_removed``
        event is published.  This handles provider renames, agent
        deletions, and any other changes that happened while the
        dispatcher was not running.
        """
        if not os.path.isdir(self.agents_dir):
            logger.warning(
                "Agents directory does not exist: %s", self.agents_dir
            )
            return

        count_ok = 0
        count_err = 0
        discovered: set[tuple[str, str]] = set()

        for provider_name in sorted(os.listdir(self.agents_dir)):
            provider_path = os.path.join(self.agents_dir, provider_name)
            if not os.path.isdir(provider_path):
                continue

            for agent_name in sorted(os.listdir(provider_path)):
                agent_path = os.path.join(provider_path, agent_name)
                config_path = os.path.join(agent_path, "agent.yml")
                if not os.path.isfile(config_path):
                    continue

                try:
                    config = load_agent_config(agent_path)
                    errors = validate_agent_dependencies(
                        config,
                        self.models_config,
                        tools_base=self.tools_base,
                        skills_base=self.skills_base,
                        agents_base=self.agents_dir,
                    )
                    if errors:
                        logger.warning(
                            "Agent %s/%s has dependency errors: %s",
                            provider_name,
                            agent_name,
                            errors,
                        )
                        count_err += 1
                        continue

                    config_hash = compute_config_hash(config_path)

                    # Upsert agent in DB
                    await upsert_agent(
                        self.db_pool,
                        provider=provider_name,
                        name=agent_name,
                        display_name=config.display_name,
                        description=config.description,
                        tags=config.tags,
                        config_hash=config_hash,
                        status=config.status,
                    )

                    # Publish event
                    await self._publish_event(
                        "agent_added",
                        provider_name,
                        agent_name,
                        config,
                        config_hash,
                    )
                    discovered.add((provider_name, agent_name))
                    count_ok += 1

                except Exception as exc:
                    logger.error(
                        "Error loading agent %s/%s: %s",
                        provider_name,
                        agent_name,
                        exc,
                    )
                    count_err += 1

        # Deactivate agents in DB that no longer exist on disk
        stale = await deactivate_agents_not_in_set(self.db_pool, discovered)
        for agent in stale:
            logger.info(
                "Deactivated stale agent %s/%s (no longer on disk)",
                agent["provider"],
                agent["name"],
            )
            await self._publish_event(
                "agent_removed", agent["provider"], agent["name"]
            )

        logger.info(
            "Initial scan complete: %d agent(s) registered, %d error(s), %d stale deactivated",
            count_ok,
            count_err,
            len(stale),
        )

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the watchdog Observer in a background thread."""
        if self.loop is None:
            self.loop = asyncio.get_running_loop()

        handler = _AgentEventHandler(self)
        if self._use_polling:
            self._observer = PollingObserver(timeout=self._poll_interval)
            logger.info(
                "Using PollingObserver (interval=%ds) — works with Docker bind mounts",
                self._poll_interval,
            )
        else:
            self._observer = Observer()
            logger.info("Using native Observer (inotify)")
        self._observer.schedule(handler, self.agents_dir, recursive=True)
        self._observer.daemon = True
        self._observer.start()

        logger.info("Watcher started on '%s'", self.agents_dir)

        # Keep running until stop is requested
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(1)
        finally:
            if self._observer:
                self._observer.stop()
                self._observer.join(timeout=5)
                logger.info("Watcher observer stopped")

    async def stop(self) -> None:
        """Signal the watcher to stop."""
        logger.info("Watcher stop requested")
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Event handling (called from watchdog thread)
    # ------------------------------------------------------------------

    def on_filesystem_event(self, event: FileSystemEvent) -> None:
        """Handle a watchdog event (called from the observer thread).

        Extracts provider/name from the path, debounces, and schedules
        async processing on the event loop.
        """
        src_path = event.src_path
        parsed = self._parse_agent_path(src_path)

        if parsed is None:
            # Check if this is a provider-level event (rename/delete of
            # an entire provider directory).
            provider_only = self._parse_provider_path(src_path)
            if provider_only and self.loop and self.loop.is_running():
                now = time.monotonic()
                agent_key = f"__provider__/{provider_only}"
                with self._debounce_lock:
                    self._debounce_timers[agent_key] = now
                asyncio.run_coroutine_threadsafe(
                    self._debounced_provider_process(
                        agent_key, provider_only, now
                    ),
                    self.loop,
                )
            return

        provider, name = parsed
        agent_key = f"{provider}/{name}"

        # Debounce: schedule processing after DEBOUNCE_SECONDS
        now = time.monotonic()
        with self._debounce_lock:
            self._debounce_timers[agent_key] = now

        # Schedule a delayed check on the asyncio loop
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._debounced_process(agent_key, provider, name, now),
                self.loop,
            )

    async def _debounced_process(
        self,
        agent_key: str,
        provider: str,
        name: str,
        scheduled_at: float,
    ) -> None:
        """Wait for the debounce window, then process if still current."""
        await asyncio.sleep(DEBOUNCE_SECONDS)

        with self._debounce_lock:
            last_time = self._debounce_timers.get(agent_key)
            if last_time != scheduled_at:
                # A newer event superseded this one
                return
            # Clean up
            self._debounce_timers.pop(agent_key, None)

        await self._handle_agent_change(provider, name)

    async def _handle_agent_change(
        self, provider: str, name: str
    ) -> None:
        """Determine the type of change and publish the appropriate event."""
        agent_dir = os.path.join(self.agents_dir, provider, name)
        config_path = os.path.join(agent_dir, "agent.yml")

        # Deletion
        if not os.path.isdir(agent_dir) or not os.path.isfile(config_path):
            logger.info(
                "Agent %s/%s removed (dir or config missing)", provider, name
            )
            await update_agent_status(self.db_pool, provider, name, "inactive")
            await self._publish_event(
                "agent_removed", provider, name
            )
            return

        # Creation or modification
        try:
            config = load_agent_config(agent_dir)
            errors = validate_agent_dependencies(
                config,
                self.models_config,
                tools_base=self.tools_base,
                skills_base=self.skills_base,
            )
            if errors:
                logger.warning(
                    "Agent %s/%s has dependency errors after change: %s",
                    provider,
                    name,
                    errors,
                )
                return

            config_hash = compute_config_hash(config_path)

            # Upsert in DB
            await upsert_agent(
                self.db_pool,
                provider=provider,
                name=name,
                display_name=config.display_name,
                description=config.description,
                tags=config.tags,
                config_hash=config_hash,
                status=config.status,
            )

            # Determine if it is a new agent or an update
            # (we use agent_updated for simplicity — MCP 1 handles both)
            event_type = "agent_updated"
            logger.info("Agent %s/%s updated/added", provider, name)

            await self._publish_event(
                event_type, provider, name, config, config_hash
            )

        except ConfigError as exc:
            logger.warning(
                "Agent %s/%s config invalid after change: %s",
                provider,
                name,
                exc,
            )
        except Exception as exc:
            logger.error(
                "Error processing agent change %s/%s: %s",
                provider,
                name,
                exc,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Provider-level change handling
    # ------------------------------------------------------------------

    async def _debounced_provider_process(
        self,
        agent_key: str,
        provider: str,
        scheduled_at: float,
    ) -> None:
        """Wait for the debounce window, then process provider change."""
        await asyncio.sleep(DEBOUNCE_SECONDS)

        with self._debounce_lock:
            last_time = self._debounce_timers.get(agent_key)
            if last_time != scheduled_at:
                return
            self._debounce_timers.pop(agent_key, None)

        await self._handle_provider_change(provider)

    async def _handle_provider_change(self, provider: str) -> None:
        """Handle a provider-level rename or deletion.

        If the provider directory no longer exists on disk, deactivate
        all its agents in the DB and publish ``agent_removed`` events.
        """
        provider_dir = os.path.join(self.agents_dir, provider)
        if os.path.isdir(provider_dir):
            # Provider still exists — individual agent events will handle it
            return

        # Provider directory gone: deactivate all its agents in DB
        agents = await get_agents_by_provider(self.db_pool, provider)
        for agent in agents:
            await update_agent_status(
                self.db_pool, provider, agent["name"], "inactive"
            )
            logger.info(
                "Deactivated agent %s/%s (provider directory removed)",
                provider,
                agent["name"],
            )
            await self._publish_event(
                "agent_removed", provider, agent["name"]
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_agent_path(self, path: str) -> tuple[str, str] | None:
        """Extract (provider, name) from a filesystem path inside agents/.

        Returns ``None`` if the path does not correspond to a valid
        agent location (e.g. provider-level paths).
        """
        # Normalise path separators
        path = os.path.normpath(path)
        agents_dir = os.path.normpath(self.agents_dir)

        if not path.startswith(agents_dir):
            return None

        rel = os.path.relpath(path, agents_dir)
        parts = rel.replace("\\", "/").split("/")

        # We need at least provider/name for agent-level events
        if len(parts) < 2:
            return None

        provider = parts[0]
        name = parts[1]
        return provider, name

    def _parse_provider_path(self, path: str) -> str | None:
        """Extract provider name from a provider-level path inside agents/.

        Returns ``None`` if the path is not a direct child of agents_dir.
        """
        path = os.path.normpath(path)
        agents_dir = os.path.normpath(self.agents_dir)

        if not path.startswith(agents_dir):
            return None

        rel = os.path.relpath(path, agents_dir)
        parts = rel.replace("\\", "/").split("/")

        if len(parts) == 1 and parts[0] != ".":
            return parts[0]
        return None

    async def _publish_event(
        self,
        event: str,
        provider: str,
        name: str,
        config: AgentConfig | None = None,
        config_hash: str | None = None,
    ) -> None:
        """Publish an agent lifecycle event to RabbitMQ."""
        tracer = get_tracer("dispatcher.watcher")

        with tracer.start_as_current_span(
            "agent.watch.notify",
            attributes={
                "agent.event": event,
                "agent.provider": provider,
                "agent.name": name,
            },
        ):
            body: dict[str, Any] = {
                "event": event,
                "provider": provider,
                "name": name,
                "tags": config.tags if config else [],
                "display_name": config.display_name if config else None,
                "description": config.description if config else None,
                "status": config.status if config else None,
                "config_hash": config_hash,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            trace_headers: dict[str, Any] = {}
            inject_context(trace_headers)
            try:
                await publish_message(
                    self.exchange,
                    AGENT_REGISTRY_EVENTS_QUEUE,
                    body,
                    trace_headers=trace_headers,
                )
                _agent_events.add(
                    1,
                    {"event": event, "agent.provider": provider, "agent.name": name},
                )
                logger.debug("Published event '%s' for %s/%s", event, provider, name)
            except Exception as exc:
                logger.error(
                    "Failed to publish event '%s' for %s/%s: %s",
                    event,
                    provider,
                    name,
                    exc,
                )

# ---------------------------------------------------------------------------
# Watchdog event handler (runs in observer thread)
# ---------------------------------------------------------------------------

class _AgentEventHandler(FileSystemEventHandler):
    """Bridge watchdog filesystem events to the AgentWatcher."""

    def __init__(self, watcher: AgentWatcher) -> None:
        super().__init__()
        self.watcher = watcher

    def on_created(self, event: FileSystemEvent) -> None:
        self.watcher.on_filesystem_event(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        self.watcher.on_filesystem_event(event)

    def on_deleted(self, event: FileSystemEvent) -> None:
        self.watcher.on_filesystem_event(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        # Process both source (old) and destination (new) paths so that
        # a rename of a provider or agent directory correctly triggers
        # removal of the old entry and registration of the new one.
        self.watcher.on_filesystem_event(event)
        if hasattr(event, "dest_path") and event.dest_path:
            # Create a synthetic event for the new path so it gets
            # picked up as an addition/update.
            from watchdog.events import FileCreatedEvent, DirCreatedEvent

            if event.is_directory:
                synthetic = DirCreatedEvent(event.dest_path)
            else:
                synthetic = FileCreatedEvent(event.dest_path)
            self.watcher.on_filesystem_event(synthetic)
