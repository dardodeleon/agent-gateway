"""Shared OpenTelemetry initialization and context propagation.

Provides centralized setup for distributed tracing across all services in
the multi-agent task dispatch system.  Traces are exported to the configured
OTLP endpoint (typically Jaeger) via gRPC.

If ``OTEL_EXPORTER_OTLP_ENDPOINT`` is not set, tracing uses a no-op
provider so instrumented code works without a collector.

Metrics export is not enabled (Jaeger only supports traces).  The
``get_meter()`` helper returns a no-op meter that can be used for future
metric instrumentation once a metrics backend (e.g. Prometheus) is added.

Log lines are correlated with traces via ``TraceContextFormatter`` which
injects ``trace_id`` and ``span_id`` into every log record.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = logging.getLogger("[OTEL]")

_provider: TracerProvider | None = None
_propagator = TraceContextTextMapPropagator()

# ---------------------------------------------------------------------------
# Log correlation
# ---------------------------------------------------------------------------

TRACE_LOG_FORMAT = (
    "%(asctime)s %(name)s %(levelname)s "
    "[trace=%(trace_id)s span=%(span_id)s] %(message)s"
)

class TraceContextFormatter(logging.Formatter):
    """Logging formatter that injects trace_id and span_id."""

    def format(self, record: logging.LogRecord) -> str:
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.is_valid:
            record.trace_id = format(ctx.trace_id, "032x")
            record.span_id = format(ctx.span_id, "016x")
        else:
            record.trace_id = "-"
            record.span_id = "-"
        return super().format(record)

# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def init_telemetry(service_name: str) -> None:
    """Initialize OpenTelemetry TracerProvider.

    Reads ``OTEL_EXPORTER_OTLP_ENDPOINT`` from environment.  When present,
    spans are exported via OTLP gRPC to Jaeger.  When absent, a no-op
    provider is used.

    Metrics export is intentionally disabled — Jaeger only supports traces.
    ``get_meter()`` still works (returns a no-op meter) so code can be
    instrumented ahead of adding a metrics backend in the future.
    """
    global _provider

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    resource = Resource.create({"service.name": service_name})

    # --- Traces ---
    _provider = TracerProvider(resource=resource)

    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            _provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info(
                "Trace exporter configured: service=%s, endpoint=%s",
                service_name,
                endpoint,
            )
        except Exception as exc:
            logger.warning("Failed to configure OTLP trace exporter: %s", exc)

    trace.set_tracer_provider(_provider)

    if not endpoint:
        logger.info(
            "Telemetry initialized without exporters "
            "(OTEL_EXPORTER_OTLP_ENDPOINT not set)"
        )

def get_tracer(name: str) -> trace.Tracer:
    """Return a tracer scoped to *name*."""
    return trace.get_tracer(name)

def get_meter(name: str):
    """Return a meter scoped to *name*."""
    return metrics.get_meter(name)

# ---------------------------------------------------------------------------
# Context propagation
# ---------------------------------------------------------------------------

def inject_context(headers: dict[str, Any]) -> dict[str, Any]:
    """Inject current trace context into *headers* (W3C TraceContext)."""
    _propagator.inject(headers)
    return headers

def extract_context(headers: dict[str, Any]) -> Context:
    """Extract trace context from *headers* received in a RabbitMQ message."""
    return _propagator.extract(carrier=headers)

# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------

def init_telemetry_with_asyncpg(service_name: str | None = None) -> None:
    """Initialize OpenTelemetry and instrument asyncpg if available."""
    svc = service_name or os.environ.get("OTEL_SERVICE_NAME", "unknown")
    init_telemetry(svc)
    try:
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor

        AsyncPGInstrumentor().instrument(
            capture_parameters=True,
        )
    except Exception:
        pass  # Auto-instrumentation not available

def shutdown_telemetry() -> None:
    """Flush pending spans and shut down the TracerProvider."""
    global _provider

    if _provider is not None:
        try:
            _provider.shutdown()
        except Exception as exc:
            logger.warning("Error shutting down TracerProvider: %s", exc)
        _provider = None

    logger.info("Telemetry shut down")
