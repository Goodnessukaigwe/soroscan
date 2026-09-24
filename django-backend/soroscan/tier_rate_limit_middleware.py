"""Tier-based sliding-window rate limiting for ``X-API-Key`` requests."""

import math
import time

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from soroscan.ingest.models import APIKey


WINDOW_SECONDS = 3600
CACHE_PREFIX = "soroscan_tier_sliding_window"


class TieredAPIKeyRateLimitMiddleware(MiddlewareMixin):
    """Enforce Free/Pro/Enterprise quotas using a one-hour sliding window."""

    async def __call__(self, request):
        raw_key = request.headers.get("X-API-Key")
        if not raw_key:
            return await self.get_response(request)

        api_key = await sync_to_async(self._get_api_key)(raw_key)
        if api_key is None:
            return await self.get_response(request)

        tier = await sync_to_async(self._effective_tier)(api_key)
        limit = APIKey.TIER_QUOTAS.get(
            tier,
            APIKey.TIER_QUOTAS[APIKey.Tier.FREE],
        )

        if limit is None:
            return await self.get_response(request)

        now = time.time()
        cache_key = f"{CACHE_PREFIX}:{api_key.pk}"
        cutoff = now - WINDOW_SECONDS
        history = [
            float(timestamp)
            for timestamp in cache.get(cache_key, [])
            if float(timestamp) > cutoff
        ]

        if len(history) >= limit:
            reset_at = math.ceil(min(history) + WINDOW_SECONDS)
            response = JsonResponse(
                {
                    "detail": "API key rate limit exceeded.",
                    "tier": tier,
                    "limit": limit,
                },
                status=429,
            )
            self._set_headers(
                response,
                limit=limit,
                remaining=0,
                reset_at=reset_at,
            )
            return response

        history.append(now)
        reset_at = math.ceil(min(history) + WINDOW_SECONDS)
        ttl = max(1, reset_at - math.floor(now))
        cache.set(cache_key, history, timeout=ttl)

        response = await self.get_response(request)
        self._set_headers(
            response,
            limit=limit,
            remaining=max(0, limit - len(history)),
            reset_at=reset_at,
        )
        return response

    @staticmethod
    def _get_api_key(raw_key: str):
        try:
            return (
                APIKey.objects.select_related("team__organization")
                .get(key=raw_key, is_active=True)
            )
        except APIKey.DoesNotExist:
            return None

    @staticmethod
    def _effective_tier(api_key: APIKey) -> str:
        if api_key.team_id and api_key.team and api_key.team.organization_id:
            return api_key.team.organization.tier
        return api_key.tier

    @staticmethod
    def _set_headers(
        response,
        *,
        limit: int,
        remaining: int,
        reset_at: int,
    ) -> None:
        response["X-RateLimit-Limit"] = str(limit)
        response["X-RateLimit-Remaining"] = str(remaining)
        response["X-RateLimit-Reset"] = str(reset_at)
