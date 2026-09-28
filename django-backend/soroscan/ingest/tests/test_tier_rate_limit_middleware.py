import asyncio
import time

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.http import JsonResponse
from django.test import RequestFactory

from soroscan.ingest.models import APIKey, Organization, Team, TeamMembership
from soroscan.tier_rate_limit_middleware import TieredAPIKeyRateLimitMiddleware


User = get_user_model()


@pytest.fixture(autouse=True)
def clear_rate_limit_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def request_factory():
    return RequestFactory()


async def _ok_response(_request):
    # The middleware is async (c27dd70b); get_response must be awaitable.
    return JsonResponse({"ok": True})


def _call(middleware, request):
    """Run the async middleware from a synchronous test."""
    return asyncio.run(middleware(request))


@pytest.mark.django_db
def test_organization_and_api_key_have_subscription_tiers():
    user = User.objects.create_user(username="tier-user")
    organization = Organization.objects.create(
        name="Tier Org",
        owner=user,
        tier=Organization.Tier.PRO,
    )
    api_key = APIKey.objects.create(
        user=user,
        name="Tier Key",
        tier=APIKey.Tier.ENTERPRISE,
        quota_per_hour=APIKey.UNLIMITED_QUOTA,
    )

    assert organization.tier == Organization.Tier.PRO
    assert api_key.tier == APIKey.Tier.ENTERPRISE


@pytest.mark.django_db(transaction=True)
def test_x_api_key_sliding_window_returns_429_and_reset_header(
    request_factory,
    monkeypatch,
):
    user = User.objects.create_user(username="free-user")
    api_key = APIKey.objects.create(
        user=user,
        name="Free Key",
        tier=APIKey.Tier.FREE,
        quota_per_hour=2,
    )
    monkeypatch.setitem(APIKey.TIER_QUOTAS, APIKey.Tier.FREE, 2)

    middleware = TieredAPIKeyRateLimitMiddleware(_ok_response)

    first = _call(middleware, request_factory.get("/", HTTP_X_API_KEY=api_key.key))
    second = _call(middleware, request_factory.get("/", HTTP_X_API_KEY=api_key.key))
    blocked = _call(middleware, request_factory.get("/", HTTP_X_API_KEY=api_key.key))

    assert first.status_code == 200
    assert second.status_code == 200
    assert blocked.status_code == 429
    assert blocked["X-RateLimit-Remaining"] == "0"
    assert int(blocked["X-RateLimit-Reset"]) > int(time.time())


@pytest.mark.django_db(transaction=True)
def test_organization_tier_controls_team_api_key_limit(
    request_factory,
    monkeypatch,
):
    user = User.objects.create_user(username="org-user")
    organization = Organization.objects.create(
        name="Pro Org",
        owner=user,
        tier=Organization.Tier.PRO,
    )
    team = Team.objects.create(
        name="Pro Team",
        organization=organization,
        created_by=user,
    )
    TeamMembership.objects.create(
        team=team,
        user=user,
        role=TeamMembership.Role.OWNER,
    )
    api_key = APIKey.objects.create(
        user=user,
        team=team,
        name="Team Key",
        tier=APIKey.Tier.FREE,
        quota_per_hour=1,
    )

    monkeypatch.setitem(APIKey.TIER_QUOTAS, APIKey.Tier.FREE, 1)
    monkeypatch.setitem(APIKey.TIER_QUOTAS, APIKey.Tier.PRO, 2)

    middleware = TieredAPIKeyRateLimitMiddleware(_ok_response)

    first = _call(middleware, request_factory.get("/", HTTP_X_API_KEY=api_key.key))
    second = _call(middleware, request_factory.get("/", HTTP_X_API_KEY=api_key.key))
    blocked = _call(middleware, request_factory.get("/", HTTP_X_API_KEY=api_key.key))

    assert first.status_code == 200
    assert second.status_code == 200
    assert second["X-RateLimit-Limit"] == "2"
    assert blocked.status_code == 429


@pytest.mark.django_db(transaction=True)
def test_enterprise_organization_is_unlimited(request_factory):
    user = User.objects.create_user(username="enterprise-user")
    organization = Organization.objects.create(
        name="Enterprise Org",
        owner=user,
        tier=Organization.Tier.ENTERPRISE,
    )
    team = Team.objects.create(
        name="Enterprise Team",
        organization=organization,
        created_by=user,
    )
    TeamMembership.objects.create(
        team=team,
        user=user,
        role=TeamMembership.Role.OWNER,
    )
    api_key = APIKey.objects.create(
        user=user,
        team=team,
        name="Enterprise Key",
        tier=APIKey.Tier.FREE,
        quota_per_hour=1,
    )

    middleware = TieredAPIKeyRateLimitMiddleware(_ok_response)

    for _ in range(5):
        response = _call(
            middleware,
            request_factory.get("/", HTTP_X_API_KEY=api_key.key),
        )
        assert response.status_code == 200


@pytest.mark.django_db
def test_requests_without_x_api_key_are_not_rate_limited(request_factory):
    middleware = TieredAPIKeyRateLimitMiddleware(_ok_response)

    response = _call(middleware, request_factory.get("/"))

    assert response.status_code == 200
    assert "X-RateLimit-Reset" not in response
