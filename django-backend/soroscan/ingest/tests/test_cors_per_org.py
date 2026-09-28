"""
Tests for per-organization CORS configuration.

Coverage:
- Organization.cors_origins field (model-level)
- OrgCorsMiddleware header injection
- GET /api/ingest/organizations/<pk>/cors/ (read)
- PATCH /api/ingest/organizations/<pk>/cors/ (update)
- OrganizationAdmin.save_model validation
- Cache-invalidation signal
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from unittest.mock import patch

from soroscan.cors_middleware import (
    OrgCorsMiddleware,
    _get_org_origins,
    invalidate_org_cors_cache,
)
from soroscan.ingest.models import Organization, OrganizationMembership

User = get_user_model()

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(username, password="pass", is_staff=False):
    user = User.objects.create_user(username=username, password=password, is_staff=is_staff)
    return user


def _make_org(owner, name="Test Org", cors_origins=None):
    org = Organization.objects.create(
        name=name,
        owner=owner,
        cors_origins=cors_origins or [],
    )
    OrganizationMembership.objects.create(
        organization=org,
        user=owner,
        role=OrganizationMembership.Role.OWNER,
    )
    return org


def _api_client(user=None):
    client = APIClient()
    if user:
        client.force_authenticate(user=user)
    return client


# ---------------------------------------------------------------------------
# 1. Model field
# ---------------------------------------------------------------------------

class TestOrganizationCorsOriginsField:
    def test_default_is_empty_list(self):
        owner = _make_user("owner1")
        org = Organization.objects.create(name="Org A", owner=owner)
        assert org.cors_origins == []

    def test_stores_and_retrieves_origins(self):
        owner = _make_user("owner2")
        origins = ["https://app.example.com", "https://staging.example.com"]
        org = Organization.objects.create(name="Org B", owner=owner, cors_origins=origins)
        org.refresh_from_db()
        assert org.cors_origins == origins

    def test_updates_origins(self):
        owner = _make_user("owner3")
        org = Organization.objects.create(name="Org C", owner=owner, cors_origins=[])
        org.cors_origins = ["https://updated.example.com"]
        org.save()
        org.refresh_from_db()
        assert org.cors_origins == ["https://updated.example.com"]

    def test_multiple_orgs_independent_cors(self):
        owner = _make_user("owner4")
        org1 = Organization.objects.create(name="Org D", owner=owner, cors_origins=["https://one.com"])
        org2 = Organization.objects.create(name="Org E", owner=owner, cors_origins=["https://two.com"])
        org1.refresh_from_db()
        org2.refresh_from_db()
        assert "https://one.com" in org1.cors_origins
        assert "https://two.com" in org2.cors_origins
        assert "https://two.com" not in org1.cors_origins


# ---------------------------------------------------------------------------
# 2. OrgCorsMiddleware
# ---------------------------------------------------------------------------

def _simple_response(status=200):
    from django.http import HttpResponse
    return HttpResponse("ok", status=status)


class TestOrgCorsMiddleware:
    """Unit-test the middleware in isolation using a mock get_response."""

    def _make_request(self, origin=None, method="GET"):
        factory = RequestFactory()
        req = factory.generic(method, "/api/ingest/events/")
        if origin:
            req.META["HTTP_ORIGIN"] = origin
        return req

    @override_settings(CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOWED_ORIGINS=[], CORS_ALLOW_CREDENTIALS=True)
    def test_no_origin_header_passes_through(self):
        """Requests without an Origin header are untouched."""
        req = self._make_request(origin=None)
        middleware = OrgCorsMiddleware(lambda r: _simple_response())
        resp = middleware(req)
        assert resp.status_code == 200
        assert "Access-Control-Allow-Origin" not in resp

    @override_settings(CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOWED_ORIGINS=[], CORS_ALLOW_CREDENTIALS=True)
    def test_unknown_origin_not_in_any_org_passes_through_without_acao(self):
        """Origins not in any org list are not injected."""
        invalidate_org_cors_cache()
        req = self._make_request(origin="https://unknown.example.com")

        with patch("soroscan.cors_middleware._get_org_origins", return_value={}):
            invalidate_org_cors_cache()
            middleware = OrgCorsMiddleware(lambda r: _simple_response())
            resp = middleware(req)

        assert "Access-Control-Allow-Origin" not in resp

    @override_settings(CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOWED_ORIGINS=[], CORS_ALLOW_CREDENTIALS=True)
    def test_org_origin_gets_acao_header(self):
        """An origin present in an org's cors_origins list receives the ACAO header."""
        owner = _make_user("mw_owner1")
        _make_org(owner, cors_origins=["https://client.example.com"])

        invalidate_org_cors_cache()
        req = self._make_request(origin="https://client.example.com")
        middleware = OrgCorsMiddleware(lambda r: _simple_response())
        resp = middleware(req)

        assert resp["Access-Control-Allow-Origin"] == "https://client.example.com"
        assert resp["Access-Control-Allow-Credentials"] == "true"
        assert "Origin" in resp.get("Vary", "")

    @override_settings(CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOWED_ORIGINS=[], CORS_ALLOW_CREDENTIALS=True)
    def test_preflight_returns_200_with_cors_headers(self):
        """OPTIONS preflight for an org origin is handled immediately."""
        owner = _make_user("mw_owner2")
        _make_org(owner, cors_origins=["https://preflight.example.com"])

        invalidate_org_cors_cache()
        req = self._make_request(origin="https://preflight.example.com", method="OPTIONS")
        middleware = OrgCorsMiddleware(lambda r: _simple_response())
        resp = middleware(req)

        assert resp.status_code == 200
        assert resp["Access-Control-Allow-Origin"] == "https://preflight.example.com"

    @override_settings(CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOWED_ORIGINS=["https://global.example.com"], CORS_ALLOW_CREDENTIALS=True)
    def test_global_allowed_origin_skips_org_lookup(self):
        """Origins already in CORS_ALLOWED_ORIGINS are handled by CorsHeaders; we skip them."""
        req = self._make_request(origin="https://global.example.com")

        # If the middleware reached _get_org_origins it would hit the DB.
        # We assert it does NOT by verifying the response has no ACAO from us
        # (CorsHeaders isn't in this test chain, so the header is simply absent).
        called = []

        def _fake_load():
            called.append(True)
            return {}

        with patch("soroscan.cors_middleware._get_org_origins", side_effect=_fake_load):
            invalidate_org_cors_cache()
            middleware = OrgCorsMiddleware(lambda r: _simple_response())
            middleware(req)

        assert not called, "OrgCorsMiddleware should not query DB for globally allowed origins"

    @override_settings(CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOWED_ORIGINS=[], CORS_ALLOW_CREDENTIALS=True)
    def test_trailing_slash_stripped(self):
        """Origins stored with a trailing slash still match the browser-sent value."""
        owner = _make_user("mw_owner3")
        _make_org(owner, cors_origins=["https://slash.example.com/"])

        invalidate_org_cors_cache()
        req = self._make_request(origin="https://slash.example.com")
        middleware = OrgCorsMiddleware(lambda r: _simple_response())
        resp = middleware(req)

        assert resp["Access-Control-Allow-Origin"] == "https://slash.example.com"

    @override_settings(CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOWED_ORIGINS=[], CORS_ALLOW_CREDENTIALS=False)
    def test_credentials_header_absent_when_not_configured(self):
        """Access-Control-Allow-Credentials is only set when CORS_ALLOW_CREDENTIALS=True."""
        owner = _make_user("mw_owner4")
        _make_org(owner, cors_origins=["https://nocreds.example.com"])

        invalidate_org_cors_cache()
        req = self._make_request(origin="https://nocreds.example.com")
        middleware = OrgCorsMiddleware(lambda r: _simple_response())
        resp = middleware(req)

        assert resp["Access-Control-Allow-Origin"] == "https://nocreds.example.com"
        assert "Access-Control-Allow-Credentials" not in resp


# ---------------------------------------------------------------------------
# 3. REST API – GET /api/ingest/organizations/<pk>/cors/
# ---------------------------------------------------------------------------

class TestOrganizationCorsGetEndpoint:
    def test_owner_can_read_cors(self):
        owner = _make_user("api_owner1")
        org = _make_org(owner, cors_origins=["https://read.example.com"])
        client = _api_client(owner)

        url = reverse("organization-cors", kwargs={"pk": org.pk})
        resp = client.get(url)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["cors_origins"] == ["https://read.example.com"]
        assert resp.data["id"] == org.pk

    def test_staff_can_read_any_org_cors(self):
        owner = _make_user("api_owner2")
        staff = _make_user("staff1", is_staff=True)
        org = _make_org(owner, cors_origins=["https://staffread.example.com"])
        client = _api_client(staff)

        url = reverse("organization-cors", kwargs={"pk": org.pk})
        resp = client.get(url)

        assert resp.status_code == status.HTTP_200_OK

    def test_unrelated_user_cannot_read_cors(self):
        owner = _make_user("api_owner3")
        other = _make_user("other1")
        org = _make_org(owner)
        client = _api_client(other)

        url = reverse("organization-cors", kwargs={"pk": org.pk})
        resp = client.get(url)

        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_read_cors(self):
        owner = _make_user("api_owner4")
        org = _make_org(owner)
        client = _api_client()  # no auth

        url = reverse("organization-cors", kwargs={"pk": org.pk})
        resp = client.get(url)

        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_nonexistent_org_returns_404(self):
        staff = _make_user("staff2", is_staff=True)
        client = _api_client(staff)

        url = reverse("organization-cors", kwargs={"pk": 999999})
        resp = client.get(url)

        assert resp.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# 4. REST API – PATCH /api/ingest/organizations/<pk>/cors/
# ---------------------------------------------------------------------------

class TestOrganizationCorsPatchEndpoint:
    def test_owner_can_update_cors_origins(self):
        owner = _make_user("patch_owner1")
        org = _make_org(owner)
        client = _api_client(owner)

        url = reverse("organization-cors", kwargs={"pk": org.pk})
        resp = client.patch(url, {"cors_origins": ["https://new.example.com"]}, format="json")

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["cors_origins"] == ["https://new.example.com"]
        org.refresh_from_db()
        assert org.cors_origins == ["https://new.example.com"]

    def test_admin_member_can_update_cors_origins(self):
        owner = _make_user("patch_owner2")
        admin_user = _make_user("patch_admin1")
        org = _make_org(owner)
        OrganizationMembership.objects.create(
            organization=org, user=admin_user, role=OrganizationMembership.Role.ADMIN
        )
        client = _api_client(admin_user)

        url = reverse("organization-cors", kwargs={"pk": org.pk})
        resp = client.patch(url, {"cors_origins": ["https://admin-set.example.com"]}, format="json")

        assert resp.status_code == status.HTTP_200_OK

    def test_regular_member_cannot_update_cors_origins(self):
        owner = _make_user("patch_owner3")
        member = _make_user("patch_member1")
        org = _make_org(owner)
        OrganizationMembership.objects.create(
            organization=org, user=member, role=OrganizationMembership.Role.MEMBER
        )
        client = _api_client(member)

        url = reverse("organization-cors", kwargs={"pk": org.pk})
        resp = client.patch(url, {"cors_origins": ["https://sneaky.example.com"]}, format="json")

        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_staff_can_update_any_org_cors(self):
        owner = _make_user("patch_owner4")
        staff = _make_user("patch_staff1", is_staff=True)
        org = _make_org(owner)
        client = _api_client(staff)

        url = reverse("organization-cors", kwargs={"pk": org.pk})
        resp = client.patch(url, {"cors_origins": ["https://staff-set.example.com"]}, format="json")

        assert resp.status_code == status.HTTP_200_OK

    def test_can_clear_cors_origins(self):
        owner = _make_user("patch_owner5")
        org = _make_org(owner, cors_origins=["https://old.example.com"])
        client = _api_client(owner)

        url = reverse("organization-cors", kwargs={"pk": org.pk})
        resp = client.patch(url, {"cors_origins": []}, format="json")

        assert resp.status_code == status.HTTP_200_OK
        org.refresh_from_db()
        assert org.cors_origins == []

    def test_multiple_origins_accepted(self):
        owner = _make_user("patch_owner6")
        org = _make_org(owner)
        client = _api_client(owner)
        origins = [
            "https://app.example.com",
            "https://staging.example.com",
            "http://localhost:3000",
        ]

        url = reverse("organization-cors", kwargs={"pk": org.pk})
        resp = client.patch(url, {"cors_origins": origins}, format="json")

        assert resp.status_code == status.HTTP_200_OK
        org.refresh_from_db()
        assert set(org.cors_origins) == set(origins)

    def test_invalid_origin_missing_scheme_rejected(self):
        owner = _make_user("patch_owner7")
        org = _make_org(owner)
        client = _api_client(owner)

        url = reverse("organization-cors", kwargs={"pk": org.pk})
        resp = client.patch(url, {"cors_origins": ["example.com"]}, format="json")

        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_origin_ftp_scheme_rejected(self):
        owner = _make_user("patch_owner8")
        org = _make_org(owner)
        client = _api_client(owner)

        url = reverse("organization-cors", kwargs={"pk": org.pk})
        resp = client.patch(url, {"cors_origins": ["ftp://example.com"]}, format="json")

        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_trailing_slash_stripped_on_save(self):
        owner = _make_user("patch_owner9")
        org = _make_org(owner)
        client = _api_client(owner)

        url = reverse("organization-cors", kwargs={"pk": org.pk})
        resp = client.patch(url, {"cors_origins": ["https://trailing.example.com/"]}, format="json")

        assert resp.status_code == status.HTTP_200_OK
        org.refresh_from_db()
        assert org.cors_origins == ["https://trailing.example.com"]


# ---------------------------------------------------------------------------
# 5. Cache invalidation signal
# ---------------------------------------------------------------------------

class TestOrgCorsCacheInvalidation:
    @override_settings(CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOWED_ORIGINS=[])
    def test_cache_invalidated_on_org_save(self):
        """After saving an Organization, the next _get_org_origins call reloads from DB."""
        owner = _make_user("sig_owner1")
        org = _make_org(owner, cors_origins=["https://before.example.com"])

        # Prime the cache.
        invalidate_org_cors_cache()
        origins_before = _get_org_origins()
        assert "https://before.example.com" in origins_before

        # Update and save — signal should bust the cache.
        org.cors_origins = ["https://after.example.com"]
        org.save()

        origins_after = _get_org_origins()
        assert "https://after.example.com" in origins_after
        assert "https://before.example.com" not in origins_after

    @override_settings(CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOWED_ORIGINS=[])
    def test_cache_invalidated_on_org_delete(self):
        """Deleting an Organization removes its origins from the cache."""
        owner = _make_user("sig_owner2")
        org = _make_org(owner, cors_origins=["https://delete-me.example.com"])

        invalidate_org_cors_cache()
        assert "https://delete-me.example.com" in _get_org_origins()

        org.delete()

        assert "https://delete-me.example.com" not in _get_org_origins()


# ---------------------------------------------------------------------------
# 6. Integration – middleware + DB in a single request cycle
# ---------------------------------------------------------------------------

class TestOrgCorsIntegration:
    @override_settings(CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOWED_ORIGINS=[], CORS_ALLOW_CREDENTIALS=True)
    def test_request_with_org_origin_gets_cors_headers(self, client):
        """
        An HTTP request whose Origin matches an org's cors_origins list
        should have Access-Control-Allow-Origin set in the response.
        """
        owner = _make_user("int_owner1")
        _make_org(owner, cors_origins=["https://integration.example.com"])

        invalidate_org_cors_cache()

        response = client.get(
            "/api/ingest/health/",
            HTTP_ORIGIN="https://integration.example.com",
        )

        assert response.get("Access-Control-Allow-Origin") == "https://integration.example.com"

    @override_settings(CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOWED_ORIGINS=[], CORS_ALLOW_CREDENTIALS=True)
    def test_request_with_unknown_origin_has_no_acao_header(self, client):
        """
        Origins not in any org list must not receive the ACAO header.
        """
        invalidate_org_cors_cache()

        response = client.get(
            "/api/ingest/health/",
            HTTP_ORIGIN="https://notallowed.example.com",
        )

        assert response.get("Access-Control-Allow-Origin") is None
