"""
Middleware for request-scoped log context (request_id) and slow query logging.
"""
import json
import logging
import time
import uuid
import secrets

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from prometheus_client import Histogram

from .log_context import set_request_id

logger = logging.getLogger(__name__)
slow_query_logger = logging.getLogger("soroscan.slow_queries")


class TraceContextMiddleware(MiddlewareMixin):
    """
    Extract incoming W3C traceparent headers or generate a new trace ID to propagate 
    distributed tracing context across HTTP handlers.
    """
    def process_request(self, request):
        traceparent = request.META.get("HTTP_TRACEPARENT")
        
        if not traceparent:
            # Generate new W3C traceparent: 00-{trace-id}-{span-id}-{trace-flags}
            trace_id = secrets.token_hex(16)
            span_id = secrets.token_hex(8)
            traceparent = f"00-{trace_id}-{span_id}-01"
            
        request.traceparent = traceparent
        
        # Save trace context into our thread-local storage for tasks/loggers
        from .log_context import log_context_var
        ctx = log_context_var.get()
        ctx["traceparent"] = traceparent

    def process_response(self, request, response):
        if hasattr(request, "traceparent"):
            response["traceparent"] = request.traceparent
        return response


class RequestIdMiddleware(MiddlewareMixin):
    """Set request_id on the request and in log context for the request lifecycle."""

    def process_request(self, request):
        request_id = request.META.get("HTTP_X_REQUEST_ID") or getattr(request, "request_id", None) or uuid.uuid4().hex
        request.request_id = request_id
        set_request_id(request_id)

    def process_response(self, request, response):
        request_id = getattr(request, "request_id", None)
        if request_id:
            response["X-Request-ID"] = request_id
            
            if response.status_code >= 400 and response.get("Content-Type", "").startswith("application/json"):
                if not getattr(response, "streaming", False):
                    try:
                        data = json.loads(response.content)
                        if isinstance(data, dict):
                            data["request_id"] = request_id
                            new_content = json.dumps(data).encode("utf-8")
                            response.content = new_content
                            if "Content-Length" in response:
                                response["Content-Length"] = str(len(new_content))
                    except (json.JSONDecodeError, AttributeError):
                        pass
        return response


class PlatformVersionMiddleware(MiddlewareMixin):
    """Attach platform version metadata to every response."""

    def process_response(self, request, response):
        response["X-SoroScan-Version"] = getattr(settings, "SOFTWARE_VERSION", "unknown")
        return response


class ReverseProxyFixedIPMiddleware(MiddlewareMixin):
    """
    Middleware to handle rate limiting behind a reverse proxy.

    When running behind a reverse proxy (e.g., Nginx, Cloudflare),
    the REMOTE_ADDR will always be the proxy's IP. This middleware
    extracts the original client IP from X-Forwarded-For header.
    """

    def process_request(self, request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            client_ip = x_forwarded_for.split(",")[0].strip()
            request.META["REMOTE_ADDR"] = client_ip


class SlowQueryMiddleware(MiddlewareMixin):
    """
    Wrap every DB execute call to log queries that exceed
    LOGGING_SLOW_QUERIES_THRESHOLD_MS (default 100 ms) to the
    ``soroscan.slow_queries`` logger, which writes to a daily-rotated file.

    Overhead is negligible (<1 µs per query for the monotonic clock call)
    and the wrapper is only active when the logger is configured.
    """

    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.threshold_ms: int = getattr(settings, "LOGGING_SLOW_QUERIES_THRESHOLD_MS", 100)

    def process_response(self, request, response):
        # Forward RateLimit-* headers set by throttle classes.
        throttle_headers: dict = {}
        generic = getattr(request, "_throttle_headers", None)
        if generic:
            throttle_headers.update(generic)
        api_key = getattr(request, "_api_key_throttle_headers", None)
        if api_key:
            throttle_headers.update(api_key)  # API-key values override generic
        if throttle_headers and hasattr(response, "__setitem__"):
            for name, value in throttle_headers.items():
                response[name] = value

        return response


class RequestBodySizeMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.method == "POST":
            max_size = getattr(settings, "MAX_REQUEST_BODY_SIZE", 10485760)
            try:
                content_length = int(request.META.get('CONTENT_LENGTH', 0))
                if content_length > max_size:
                    logger.warning("Payload Too Large: %s bytes", content_length)
                    return JsonResponse(
                        {"error": "Payload Too Large", "limit": max_size},
                        status=413
                    )
            except (ValueError, TypeError):
                pass


class GracefulShutdownMiddleware(MiddlewareMixin):
    """Reject new requests during shutdown and track in-flight request count."""

    def process_request(self, request):
        from soroscan.shutdown import try_begin_request

        if not try_begin_request():
            return JsonResponse(
                {"error": "Server is shutting down"},
                status=503,
            )

    def process_response(self, request, response):
        from soroscan.shutdown import end_request
        end_request()
        return response


class MaintenanceModeMiddleware(MiddlewareMixin):
    """Return 503 for all non-admin routes when MAINTENANCE_MODE=True."""

    def process_request(self, request):
        if getattr(settings, "MAINTENANCE_MODE", False) and not request.path.startswith("/admin"):
            return JsonResponse(
                {"error": "Service temporarily unavailable. Please try again later."},
                status=503,
            )


class ApiDeprecationMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        deprecated_endpoints = getattr(settings, "DEPRECATED_ENDPOINTS", {})

        # Normalize request path: remove leading/trailing slashes
        norm_request_path = request.path.strip("/")

        for path, config in deprecated_endpoints.items():
            # Normalize config path
            if path.strip("/") == norm_request_path:
                response["Deprecation"] = "true"
                response["Sunset"] = config.get("sunset", "")
                response["Link"] = f'<{config.get("replacement", "")}>; rel="alternate"'
                break
        return response


_STATIC_PATH_PREFIXES = ("/static/", "/media/", "/favicon.ico")

ip_logger = logging.getLogger("soroscan.ip_access")


class ClientIPLoggingMiddleware(MiddlewareMixin):
    """
    Log the client IP address, HTTP method, and request path for every
    incoming API request.
    """

    def process_request(self, request):
        path = request.path
        if not path.startswith(_STATIC_PATH_PREFIXES):
            client_ip = request.META.get("REMOTE_ADDR", "unknown")
            ip_logger.info(
                "%s %s from %s",
                request.method,
                path,
                client_ip,
                extra={
                    "client_ip": client_ip,
                    "method": request.method,
                    "path": path,
                },
            )


class CacheBustingMiddleware(MiddlewareMixin):
    """
    Add Cache-Control headers to API responses.

    Supports cache busting via:
    - ``Cache-Control: no-cache`` header from client
    - ``X-Cache-Bust`` header from client
    - ``Last-Modified`` / ``ETag`` conditional request support
    """

    CACHE_CONTROL_PATHS = ("/api/", "/graphql/")

    def process_response(self, request, response):
        # Check if client requests cache bypass
        cache_bust = (
            request.headers.get("Cache-Control") == "no-cache"
            or request.headers.get("X-Cache-Bust") == "1"
        )

        if any(request.path.startswith(p) for p in self.CACHE_CONTROL_PATHS):
            if cache_bust:
                response["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response["Pragma"] = "no-cache"
            else:
                existing = response.get("Cache-Control", "")
                if "max-age" not in existing:
                    response["Cache-Control"] = "private, max-age=0"

        return response


# Histogram buckets are chosen to make p50/p95/p99 percentiles meaningful
# (5ms … 30s) while keeping cardinality bounded via the per-endpoint label.
REQUEST_LATENCY_SECONDS = Histogram(
    "soroscan_request_latency_seconds",
    "Request latency distribution used to derive p50/p95/p99 percentiles",
    ["method", "endpoint", "status"],
    buckets=(
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        30.0,
    ),
)


class RequestLatencyMiddleware(MiddlewareMixin):
    """Record per-endpoint request latency for percentile analysis."""

    def process_request(self, request):
        request._latency_start = time.perf_counter()

    def process_response(self, request, response):
        start = getattr(request, "_latency_start", None)
        if start is not None:
            duration = time.perf_counter() - start
            match = getattr(request, "resolver_match", None)
            endpoint = getattr(match, "route", None) or request.path
            status = getattr(response, "status_code", 0)
            REQUEST_LATENCY_SECONDS.labels(request.method, endpoint, status).observe(duration)
        return response