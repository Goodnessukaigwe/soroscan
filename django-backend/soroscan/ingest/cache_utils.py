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

# Imported at module level so patch('soroscan.ingest.cache_utils.TrackedContract…') works.
# The lazy import inside get_cached_contract is replaced by this top-level reference.
from .models import TrackedContract
from .telemetry import tracer


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


# Soroban RPC simulation cache (issue #1402).
# Short TTL so contract state reads stay fresh while shielding us from RPC
# rate limits during traffic spikes.
SIMULATION_CACHE_TTL = 60  # seconds


def simulation_cache_key(contract_id: str, function_name: str, args: Any = None) -> str:
    """Deterministic Redis key for a Soroban RPC simulation.

    Key material is ``contract_id`` + ``function_name`` + the encoded call
    arguments, so identical simulations always map to the same entry.
    """
    return stable_cache_key(
        "simulation",
        {
            "contract_id": contract_id,
            "function_name": function_name,
            "args": args if args is not None else [],
        },
    )


def get_cached_simulation_result(
    contract_id: str,
    function_name: str,
    args: Any,
    factory: Callable[[], Any],
) -> Any:
    """Return the cached simulation result, or compute it via ``factory``.

    Successful results are cached for ``SIMULATION_CACHE_TTL`` (60s).
    ``factory`` raising propagates the error uncached, so transient RPC
    failures are never stored.
    """
    key = simulation_cache_key(contract_id, function_name, args)
    return get_or_set_json(key, SIMULATION_CACHE_TTL, factory)


def invalidate_contract_query_cache(contract_id: str) -> None:
    """Best-effort: drop stats cache for a contract (pattern-free delete)."""
    # Stats key uses contract_id in payload; callers can delete by known prefixes
    cache.delete(stable_cache_key("contract_stats", {"contract_id": contract_id}))


def contract_cache_key(contract_id: str) -> str:
    """Return the Redis key for a cached TrackedContract object."""
    return f"soroscan:contract:obj:{contract_id}"


# 24-hour TTL for contract-name cache entries (Issue #778)
CONTRACT_NAME_CACHE_TTL = 86_400


def contract_name_cache_key(contract_id: str) -> str:
    """Return the Redis key for the contract_address → contract_name mapping.

    Used by ``warm_contract_name_cache`` to pre-populate a lightweight lookup
    that does not require loading full TrackedContract instances.

    Key pattern: ``soroscan:contract:name:{contract_id}``
    TTL: 24 hours (see CONTRACT_NAME_CACHE_TTL).
    """
    return f"soroscan:contract:name:{contract_id}"


def get_cached_contract(contract_id: str) -> Any:
    """Get a TrackedContract instance from cache, or load from DB and cache it."""
    with tracer.start_as_current_span(
        "ingest.contract_lookup",
        attributes={"contract_id": contract_id},
    ):
        key = contract_cache_key(contract_id)
        contract = cache.get(key)
        if contract is not None:
            return contract

        try:
            with tracer.start_as_current_span(
                "db.query.contract_lookup",
                attributes={"contract_id": contract_id},
            ):
                contract = TrackedContract.objects.get(contract_id=contract_id)
            cache.set(key, contract, timeout=3600)  # 1 hour TTL
            return contract
        except TrackedContract.DoesNotExist:
            return None


def invalidate_cached_contract(contract_id: str) -> None:
    """Invalidate the cached TrackedContract object."""
    cache.delete(contract_cache_key(contract_id))



def get_event_count(contract_id: str) -> int:
    """Get cached event count for a contract with 5-minute TTL."""
    from .metrics import cache_hits_total, cache_misses_total
    
    key = f"event_count:{contract_id}"
    count = cache.get(key)
    if count is None:
        cache_misses_total.labels(cache_type="event_count").inc()
        from .models import ContractEvent
        count = ContractEvent.objects.filter(contract__contract_id=contract_id).count()
        cache.set(key, count, 300)  # 5 min TTL
    else:
        cache_hits_total.labels(cache_type="event_count").inc()
    return count


def invalidate_event_count_cache(contract_id: str) -> None:
    """Invalidate event count cache for a contract."""
    key = f"event_count:{contract_id}"
    cache.delete(key)


DECODED_PAYLOAD_TTL = 86_400  # 24 hours


def decoded_payload_cache_key(event_id: int) -> str:
    """Return the Redis key for a cached decoded payload."""
    return f"soroscan:decoded:{event_id}"


def get_cached_decoded_payload(event_id: int) -> Any:
    """Return cached decoded payload or _SENTINEL if not cached."""
    return cache.get(decoded_payload_cache_key(event_id), _SENTINEL)


def set_cached_decoded_payload(event_id: int, payload: Any) -> None:
    """Store decoded payload in cache with 24-hour TTL."""
    cache.set(decoded_payload_cache_key(event_id), payload, timeout=DECODED_PAYLOAD_TTL)


def invalidate_decoded_payload_cache(event_id: int) -> None:
    """Invalidate the decoded payload cache for a specific event."""
    cache.delete(decoded_payload_cache_key(event_id))


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
