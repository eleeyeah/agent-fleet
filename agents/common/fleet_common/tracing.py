"""Logging + optional OpenTelemetry tracing (risk #6).

Every log line carries the correlation_id from the current task/brief via a
contextvar, so one `kubectl logs | grep <cid>` follows a project across agents.
If FLEET_OTEL_ENDPOINT is set, spans are exported over OTLP/HTTP; otherwise
tracing is a no-op and logging still works.
"""

from __future__ import annotations

import contextvars
import logging
import sys

correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="-")


class _CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.cid = correlation_id.get()
        return True


def setup(service_name: str, otel_endpoint: str = "") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_CorrelationFilter())
    handler.setFormatter(
        logging.Formatter(
            fmt=f"%(asctime)s %(levelname)s {service_name} cid=%(cid)s %(name)s: %(message)s",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if otel_endpoint:
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otel_endpoint)))
            trace.set_tracer_provider(provider)
            logging.getLogger(__name__).info("OTel tracing enabled -> %s", otel_endpoint)
        except Exception:  # pragma: no cover - optional dependency path
            logging.getLogger(__name__).warning("OTel setup failed; continuing without tracing")
