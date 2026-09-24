"""Small tracing and payload-compression helpers for ingest flows."""

from __future__ import annotations

import contextlib
import json
import os
import zlib
from typing import Any, Iterator, Mapping, Optional

from opentelemetry import propagate, trace

from .metrics import event_payload_compression_ratio

tracer = trace.get_tracer("soroscan.ingest")


def configure_tracing() -> None:
    """Optionally wire an OTLP span exporter.

    Active only when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is configured. The
    exporter dependency is imported best-effort so the application still
    boots in environments where the optional package is not installed.
    """
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # noqa: PLC0415
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource  # noqa: PLC0415
        from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
        from opentelemetry.sdk.trace.export import (  # noqa: PLC0415
            BatchSpanProcessor,
        )
    except Exception:  # pragma: no cover - optional dependency
        return

    provider = TracerProvider(
        resource=Resource.create(
            {SERVICE_NAME: os.environ.get("OTEL_SERVICE_NAME", "soroscan")}
        )
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    try:
        trace.set_tracer_provider(provider)
    except Exception:  # pragma: no cover - already configured (e.g. tests)
        trace._TRACER_PROVIDER = provider


@contextlib.contextmanager
def span(
    name: str,
    attributes: Optional[Mapping[str, Any]] = None,
    kind: int = trace.SpanKind.INTERNAL,
) -> Iterator[Any]:
    """Convenience context manager that starts and ends a span."""
    with tracer.start_as_current_span(
        name, attributes=attributes or {}, kind=kind
    ) as active_span:
        yield active_span


def payload_compression_ratio(payload: dict[str, Any]) -> float | None:
    """Observe and return the zlib compression ratio for a JSON payload."""
    if not isinstance(payload, dict) or not payload:
        return None

    raw_payload = json.dumps(
        payload,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")
    if not raw_payload:
        return None

    compressed_payload = zlib.compress(raw_payload)
    ratio = len(compressed_payload) / len(raw_payload)
    event_payload_compression_ratio.observe(ratio)
    return ratio


def inject_trace_headers(headers: dict[str, str]) -> None:
    """Inject the current trace context into an outbound HTTP header map."""
    propagate.inject(headers)
    if "traceparent" not in {k.lower() for k in headers}:
        current_span = trace.get_current_span()
        span_ctx = current_span.get_span_context() if current_span else None
        if span_ctx and span_ctx.is_valid:
            headers["traceparent"] = f"00-{span_ctx.trace_id:032x}-{span_ctx.span_id:016x}-{span_ctx.trace_flags:02x}"
        else:
            headers["traceparent"] = "00-00000000000000000000000000000001-0000000000000001-01"
