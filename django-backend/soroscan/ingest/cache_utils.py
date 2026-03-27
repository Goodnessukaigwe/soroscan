"""
Redis-backed caching for expensive REST and GraphQL queries (issue #131).
"""
import hashlib
import json
from functools import wraps
from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.core.cache import cache


def query_cache_ttl() -> int:
    return int(getattr(settings, "QUERY_CACHE_TTL_SECONDS", 60))


def stable_cache_key(prefix: str, payload: dict[str, Any]) -> str:
    """Deterministic key from a prefix and sorted JSON payload."""
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    digest = hashlib.sha256(blob).hexdigest()[:32]
    return f"soroscan:{prefix}:{digest}"


_SENTINEL = object()


def get_or_set_json(key: str, ttl: int, factory: Callable[[], Any]) -> Any:
    """Return cached value or compute and store (including cached ``None``)."""
    cached = cache.get(key, _SENTINEL)
    if cached is not _SENTINEL:
        return cached
    value = factory()
    cache.set(key, value, timeout=ttl)
    return value


def invalidate_contract_query_cache(contract_id: str) -> None:
    """Best-effort: drop stats cache for a contract (pattern-free delete)."""
    # Stats key uses contract_id in payload; callers can delete by known prefixes
    cache.delete(stable_cache_key("contract_stats", {"contract_id": contract_id}))


def cache_result(ttl: int) -> Callable:
    """Cache successful DRF function-view responses for ``ttl`` seconds."""

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            query_items = sorted(request.query_params.items()) if hasattr(request, "query_params") else []
            payload = {
                "path": request.path,
                "query": query_items,
                "kwargs": kwargs,
            }
            if getattr(request, "user", None) and request.user.is_authenticated:
                payload["user_id"] = request.user.id

            key = stable_cache_key(f"rest_view:{view_func.__name__}", payload)
            cached = cache.get(key, _SENTINEL)
            if cached is not _SENTINEL:
                from rest_framework.response import Response  # noqa: PLC0415

                return Response(cached["data"], status=cached["status"])

            response = view_func(request, *args, **kwargs)
            status_code = getattr(response, "status_code", 500)
            if status_code < 400 and hasattr(response, "data"):
                cache.set(
                    key,
                    {"status": status_code, "data": response.data},
                    timeout=ttl,
                )
            return response

        return wrapped

    return decorator
