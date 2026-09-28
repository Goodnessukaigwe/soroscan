"""
Custom throttle classes for SoroScan API rate limiting.

Rate-limit response headers
---------------------------
Every throttle class in this module sets standardised RateLimit-* headers on
``request._throttle_headers`` (a dict) so that ``SlowQueryMiddleware`` can
copy them onto the outgoing response.  The headers follow the IETF draft
specification (https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/):

    RateLimit-Limit     – maximum requests allowed in the current window
    RateLimit-Remaining – requests remaining in the current window
    RateLimit-Reset     – Unix timestamp (UTC) at which the window resets

``APIKeyThrottle`` writes to ``request._api_key_throttle_headers`` (kept for
backwards-compatibility) and *also* to ``request._throttle_headers``.
``SlowQueryMiddleware`` merges both dicts, with API-key headers winning on
conflict so that callers with explicit key quotas always see their own limits.
"""
import logging
import math
import time

from django.core.cache import cache
from rest_framework.settings import api_settings
from rest_framework.throttling import BaseThrottle, SimpleRateThrottle, ScopedRateThrottle

logger = logging.getLogger(__name__)

# Header names returned on every response
HEADER_LIMIT = "RateLimit-Limit"
HEADER_REMAINING = "RateLimit-Remaining"
HEADER_RESET = "RateLimit-Reset"

# TTL of Redis counter bucket (1 hour)
_BUCKET_TTL = 3600
_HISTORY_TTL = 3600 * 24 * 8


class RateLimitHeaderMixin:
    """
    Mixin for ``SimpleRateThrottle`` subclasses that writes standardised
    ``RateLimit-*`` headers to ``request._throttle_headers`` after each
    ``allow_request()`` call.

    Subclasses must call ``super().allow_request(request, view)`` and this
    mixin will decorate the request object with header values derived from the
    throttle's internal history cache.
    """

    def allow_request(self, request, view):
        allowed = super().allow_request(request, view)
        self._write_ratelimit_headers(request, allowed)
        return allowed

    def _write_ratelimit_headers(self, request, allowed: bool) -> None:
        """Compute and store RateLimit-* header values on the request."""
        try:
            num_requests = getattr(self, "num_requests", None)
            duration = getattr(self, "duration", None)
            if num_requests is None or duration is None:
                return

            # History is a list of Unix timestamps stored by SimpleRateThrottle
            history = getattr(self, "history", [])
            now = getattr(self, "now", time.time())

            # Count requests still inside the current window
            window_start = now - duration
            in_window = sum(1 for t in history if t > window_start)

            # If throttled, all slots are consumed
            if not allowed:
                remaining = 0
            else:
                remaining = max(0, num_requests - in_window)

            # Reset time: when the oldest in-window request ages out
            if history:
                oldest_in_window = min((t for t in history if t > window_start), default=now)
                reset_ts = math.ceil(oldest_in_window + duration)
            else:
                reset_ts = math.ceil(now + duration)

            headers = getattr(request, "_throttle_headers", {})
            # Only write if no higher-priority throttle (APIKeyThrottle) already wrote
            if HEADER_LIMIT not in headers:
                headers[HEADER_LIMIT] = str(num_requests)
                headers[HEADER_REMAINING] = str(remaining)
                headers[HEADER_RESET] = str(reset_ts)
                request._throttle_headers = headers
        except Exception:
            # Never let header computation break a request
            logger.debug("RateLimitHeaderMixin: failed to compute headers", exc_info=True)


class APIKeyThrottle(BaseThrottle):
    """
    Per-API-key tiered rate limiting with Redis counters.

    Reads the ``Authorization: ApiKey <token>`` header or the ``?api_key=``
    query parameter.  Falls through transparently (allow) when no API key is
    present so that the standard anon/user throttles still apply.

    Sets ``request._api_key_headers`` dict so middleware can
    populate RateLimit-* response headers.
    """

    CACHE_PREFIX = "soroscan_api_key_quota"

    def get_ident(self, request):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if auth.lower().startswith("apikey "):
            return auth[7:].strip()
        return request.GET.get("api_key") or request.POST.get("api_key")

    def _cache_key(self, api_key_id: int) -> str:
        # Bucket resets at the start of every calendar hour
        bucket_hour = int(time.time()) // _BUCKET_TTL
        return f"{self.CACHE_PREFIX}:{api_key_id}:{bucket_hour}"

    def allow_request(self, request, view):
        key_str = self.get_ident(request)
        if not key_str:
            # No API key — let other throttles handle this request
            return True

        from soroscan.ingest.models import APIKey, ContractQuota

        # Check if the key was already authenticated and attached to the request
        api_key = getattr(request, "api_key", None)

        if not api_key:
            try:
                api_key = APIKey.objects.select_related("user").get(
                    key=key_str, is_active=True
                )
            except APIKey.DoesNotExist:
                # Invalid / revoked key → reject
                self._set_headers(request, limit=0, remaining=0, reset=self._next_reset())
                return False

        # Determine effective quota (contract-level override wins when lower)
        quota = api_key.quota_per_hour
        contract_id = (
            view.kwargs.get("contract_id")
            or request.GET.get("contract_id")
            or (request.data.get("contract_id") if hasattr(request, "data") else None)
        )
        if contract_id:
            override = (
                ContractQuota.objects.filter(
                    api_key=api_key,
                    contract__contract_id=contract_id,
                )
                .values_list("quota_per_hour", flat=True)
                .first()
            )
            if override is not None:
                quota = min(quota, override)

        cache_key = self._cache_key(api_key.id)
        bucket_hour = int(time.time()) // _BUCKET_TTL
        history_key = f"{self.CACHE_PREFIX}_history:{api_key.id}:{bucket_hour}"
        count = cache.get(cache_key, 0)
        remaining = max(0, quota - count)
        reset_ts = self._next_reset()

        if count >= quota:
            self._set_headers(request, limit=quota, remaining=0, reset=reset_ts)
            logger.warning(
                "API key %s quota exhausted (%d/%d req/hr)",
                api_key.id,
                count,
                quota,
                extra={"api_key_id": api_key.id},
            )
            return False

        # Increment atomically via add+incr pattern
        if not cache.add(cache_key, 1, timeout=_BUCKET_TTL):
            cache.incr(cache_key)

        # Keep an hourly history series for analytics dashboard windows.
        if not cache.add(history_key, 1, timeout=_HISTORY_TTL):
            cache.incr(history_key)

        # Stamp last_used_at without blocking request (fire-and-forget via ORM)
        from django.utils import timezone

        APIKey.objects.filter(pk=api_key.pk).update(last_used_at=timezone.now())

        self._set_headers(request, limit=quota, remaining=remaining - 1, reset=reset_ts)
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _next_reset() -> int:
        """Unix timestamp of the start of the next 1-hour bucket."""
        now = int(time.time())
        return (now // _BUCKET_TTL + 1) * _BUCKET_TTL

    @staticmethod
    def _set_headers(request, *, limit: int, remaining: int, reset: int) -> None:
        headers = {
            HEADER_LIMIT: str(limit),
            HEADER_REMAINING: str(remaining),
            HEADER_RESET: str(reset),
        }
        # Backwards-compatible attribute used by SlowQueryMiddleware
        request._api_key_throttle_headers = headers
        # Also write to the shared _throttle_headers dict so that the
        # middleware has a single place to look for all throttle headers.
        # API-key headers take precedence: overwrite whatever a simpler
        # throttle may have written earlier.
        request._throttle_headers = headers

    def wait(self):
        return max(0.0, self._next_reset() - time.time())


class IngestRateThrottle(RateLimitHeaderMixin, SimpleRateThrottle):
    """
    Stricter rate limit for the ingest endpoint (POST /api/ingest/record/).

    Sets ``RateLimit-*`` headers on every response via ``RateLimitHeaderMixin``.
    """

    scope = "ingest"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}

    def throttle_failure(self):
        return None  # Use default DRF throttle failure behaviour


class GraphQLRateThrottle(RateLimitHeaderMixin, SimpleRateThrottle):
    """
    Rate limit specifically for GraphQL endpoints.

    Sets ``RateLimit-*`` headers on every response via ``RateLimitHeaderMixin``.
    """

    scope = "graphql"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class DBExplainThrottle(SimpleRateThrottle):
    """
    Rate limit for the admin DB EXPLAIN endpoint (issue #1291 / #491).

    Strict limit (10/min by default, configurable via
    ENDPOINT_RATE_LIMIT_DB_EXPLAIN) to prevent abuse of potentially
    expensive EXPLAIN ANALYZE queries even by staff users.
    """

    scope = "db_explain"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class DynamicEndpointThrottle(RateLimitHeaderMixin, ScopedRateThrottle):
    """
    Dynamically applies a throttle scope to a ViewSet action or APIView.
    Checks for `action_throttle_scopes` dictionary on the view to map an action to a scope.
    Falls back to `throttle_scope` if defined.

    Bypasses ScopedRateThrottle.allow_request() entirely to prevent it from
    overwriting the dynamically resolved ``self.scope`` with the view's static
    ``throttle_scope`` attribute (which may be absent or None).

    Sets ``RateLimit-*`` headers on every response via ``RateLimitHeaderMixin``.
    """

    def get_rate(self):
        """Read throttle rates from api_settings at call time so that
        override_settings() in tests is always respected."""
        if not getattr(self, 'scope', None):
            return None
        rates = api_settings.DEFAULT_THROTTLE_RATES
        rate = rates.get(self.scope)
        if rate is None:
            from django.core.exceptions import ImproperlyConfigured
            raise ImproperlyConfigured(
                f"No default throttle rate set for '{self.scope}' scope"
            )
        return rate

    def allow_request(self, request, view):
        # Determine scope dynamically for ViewSets
        if hasattr(view, 'action') and hasattr(view, 'action_throttle_scopes'):
            self.scope = view.action_throttle_scopes.get(view.action)

        # Fallback to static throttle_scope attribute on the view
        if getattr(self, 'scope', None) is None:
            self.scope = getattr(view, self.scope_attr, None)

        if not self.scope:
            return True

        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)

        # Call SimpleRateThrottle.allow_request directly to skip
        # ScopedRateThrottle.allow_request, which would overwrite self.scope.
        return SimpleRateThrottle.allow_request(self, request, view)


class UnauthenticatedIPRateThrottle(SimpleRateThrottle):
    """
    IP-based rate limiter for unauthenticated REST endpoints.

    Only applies to requests that have NOT been authenticated (anonymous users).
    Authenticated requests bypass this throttle entirely, allowing the
    per-user or per-API-key throttles to govern their rate.

    The throttle scope defaults to ``unauthenticated_ip`` and can be
    overridden per-view via ``throttle_scope``.

    Configuration (in settings.py ``REST_FRAMEWORK.DEFAULT_THROTTLE_RATES``)::

        "unauthenticated_ip": "30/minute",   # default for unauthenticated endpoints

    Or per-endpoint via ``ENDPOINT_RATE_LIMIT_UNAUTHENTICATED_IP`` env var.
    """

    scope = "unauthenticated_ip"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            return None  # skip — let per-user / per-key throttles govern
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}

    def allow_request(self, request, view):
        # Authenticated users are never throttled by this class
        if request.user and request.user.is_authenticated:
            return True
        return super().allow_request(request, view)
