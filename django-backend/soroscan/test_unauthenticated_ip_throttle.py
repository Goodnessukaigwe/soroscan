"""
Tests for UnauthenticatedIPRateThrottle (issue #1008).
"""
import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APIRequestFactory
from unittest.mock import MagicMock

from soroscan.throttles import UnauthenticatedIPRateThrottle


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="ip_throttle_user", password="password")


def _make_view():
    view = MagicMock()
    view.throttle_scope = "unauthenticated_ip"
    view.scope_attr = "throttle_scope"
    return view


def _make_throttle(rate="1/minute"):
    throttle = UnauthenticatedIPRateThrottle()
    throttle.rate = rate
    throttle.num_requests, throttle.duration = throttle.parse_rate(rate)
    return throttle


@pytest.mark.django_db
def test_unauthenticated_request_throttled(user):
    """Unauthenticated requests should be throttled by IP."""
    factory = APIRequestFactory()
    view = _make_view()
    throttle = _make_throttle("1/minute")

    req1 = factory.get("/api/ingest/health/")
    req1.user = None
    assert throttle.allow_request(req1, view) is True

    req2 = factory.get("/api/ingest/health/")
    req2.user = None
    assert throttle.allow_request(req2, view) is False


@pytest.mark.django_db
def test_authenticated_request_bypassed(user):
    """Authenticated requests should bypass this throttle."""
    factory = APIRequestFactory()
    view = _make_view()
    throttle = _make_throttle("1/minute")

    for _ in range(5):
        req = factory.get("/api/ingest/health/")
        req.user = user
        assert throttle.allow_request(req, view) is True


@pytest.mark.django_db
def test_get_cache_key_returns_none_for_authenticated(user):
    """get_cache_key should return None for authenticated users."""
    factory = APIRequestFactory()
    req = factory.get("/api/ingest/health/")
    req.user = user
    view = _make_view()

    throttle = UnauthenticatedIPRateThrottle()
    assert throttle.get_cache_key(req, view) is None


@pytest.mark.django_db
def test_get_cache_key_returns_key_for_anonymous():
    """get_cache_key should return a cache key for anonymous users."""
    factory = APIRequestFactory()
    req = factory.get("/api/ingest/health/")
    req.user = None
    view = _make_view()

    throttle = UnauthenticatedIPRateThrottle()
    key = throttle.get_cache_key(req, view)
    assert key is not None
    assert "unauthenticated_ip" in key
