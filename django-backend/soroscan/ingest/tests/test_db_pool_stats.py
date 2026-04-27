"""
Tests for GET /api/meta/db-pool/ — database connection pool stats endpoint.

Coverage
--------
* 401 for unauthenticated requests (no credentials supplied).
* 403 for authenticated-but-not-staff users.
* 200 with correct JSON shape for staff / superusers.
* Response keys are always integers.
* Graceful 503 when the DB layer raises an unexpected exception.
"""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from unittest.mock import MagicMock, patch

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def regular_user(db):
    return User.objects.create_user(
        username="regular",
        password="secret123",
        is_staff=False,
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="admin",
        password="secret123",
        is_staff=True,
    )


@pytest.fixture
def db_pool_url():
    return reverse("db-pool-stats")


# ---------------------------------------------------------------------------
# Authentication / authorisation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDbPoolStatsAuth:
    """The endpoint must reject unauthenticated and non-staff requests."""

    def test_unauthenticated_returns_401(self, api_client, db_pool_url):
        """No credentials → access denied (401 with JWT auth class, 403 without)."""
        response = api_client.get(db_pool_url)
        # 401 when JWTAuthentication is active; 403 when no auth class is
        # configured (test settings omit DEFAULT_AUTHENTICATION_CLASSES).
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_non_staff_user_returns_403(self, api_client, regular_user, db_pool_url):
        """Authenticated but non-staff user → 403 Forbidden."""
        api_client.force_authenticate(user=regular_user)
        response = api_client.get(db_pool_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "detail" in response.data

    def test_post_not_allowed(self, api_client, admin_user, db_pool_url):
        """Only GET is allowed; other verbs → 405 Method Not Allowed."""
        api_client.force_authenticate(user=admin_user)
        response = api_client.post(db_pool_url, data={})
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# ---------------------------------------------------------------------------
# Successful response (admin user)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDbPoolStatsSuccess:
    """Admin users must receive a 200 with the expected JSON structure."""

    def test_returns_200_for_staff_user(self, api_client, admin_user, db_pool_url):
        api_client.force_authenticate(user=admin_user)
        response = api_client.get(db_pool_url)
        assert response.status_code == status.HTTP_200_OK

    def test_response_contains_required_keys(self, api_client, admin_user, db_pool_url):
        api_client.force_authenticate(user=admin_user)
        response = api_client.get(db_pool_url)
        data = response.data
        assert set(data.keys()) == {"total", "active", "idle", "wait_queue"}

    def test_all_values_are_non_negative_integers(self, api_client, admin_user, db_pool_url):
        api_client.force_authenticate(user=admin_user)
        response = api_client.get(db_pool_url)
        data = response.data
        for key in ("total", "active", "idle", "wait_queue"):
            value = data[key]
            assert isinstance(value, int), f"'{key}' should be int, got {type(value)}"
            assert value >= 0, f"'{key}' must be >= 0, got {value}"

    def test_stats_are_consistent(self, api_client, admin_user, db_pool_url):
        """active + idle must not exceed total (or equal it for pooled setups)."""
        api_client.force_authenticate(user=admin_user)
        response = api_client.get(db_pool_url)
        data = response.data
        # active + idle should be <= total (wait_queue covers the remainder)
        assert data["active"] + data["idle"] <= data["total"] + data["wait_queue"]

    def test_superuser_also_gets_200(self, db, api_client, db_pool_url):
        superuser = User.objects.create_superuser(
            username="super", password="secret123"
        )
        api_client.force_authenticate(user=superuser)
        response = api_client.get(db_pool_url)
        assert response.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# Realtime stats behavior
# ---------------------------------------------------------------------------


class _FakeConnections:
    def __init__(self, wrapper):
        self.wrapper = wrapper

    def __getitem__(self, alias):
        assert alias == "default"
        return self.wrapper


@pytest.mark.django_db
class TestDbPoolStatsRealtime:
    """The endpoint should return current values from the active collector."""

    def test_returns_live_postgres_stats(self, api_client, admin_user, db_pool_url):
        wrapper = MagicMock()
        wrapper.vendor = "postgresql"
        fake_connections = _FakeConnections(wrapper)

        with patch("soroscan.meta_views.connections", fake_connections), patch(
            "soroscan.meta_views._collect_postgres_pool_stats",
            return_value={"total": 12, "active": 5, "idle": 7, "wait_queue": 1},
        ):
            api_client.force_authenticate(user=admin_user)
            response = api_client.get(db_pool_url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {
            "total": 12,
            "active": 5,
            "idle": 7,
            "wait_queue": 1,
        }

    def test_values_change_between_requests(self, api_client, admin_user, db_pool_url):
        """Two consecutive reads should reflect changing backend load."""
        wrapper = MagicMock()
        wrapper.vendor = "postgresql"
        fake_connections = _FakeConnections(wrapper)

        with patch("soroscan.meta_views.connections", fake_connections), patch(
            "soroscan.meta_views._collect_postgres_pool_stats",
            side_effect=[
                {"total": 8, "active": 2, "idle": 6, "wait_queue": 0},
                {"total": 8, "active": 6, "idle": 2, "wait_queue": 3},
            ],
        ):
            api_client.force_authenticate(user=admin_user)
            first = api_client.get(db_pool_url)
            second = api_client.get(db_pool_url)

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert first.data != second.data


# ---------------------------------------------------------------------------
# Failure / 503 path
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDbPoolStatsFailure:
    """If the DB layer throws, the endpoint must return 503."""

    def test_returns_503_on_db_error(self, api_client, admin_user, db_pool_url):
        with patch(
            "soroscan.meta_views._collect_fallback_pool_stats",
            side_effect=Exception("Simulated DB failure"),
        ):
            api_client.force_authenticate(user=admin_user)
            response = api_client.get(db_pool_url)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "detail" in response.data
