"""
Tests for GraphQL query whitelist enforcement and admin registration.
"""

import json
from unittest.mock import MagicMock

import pytest
from django.test import RequestFactory, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from soroscan.graphql_views import ThrottledGraphQLView, _check_query_whitelist
from soroscan.graphql_whitelist import hash_graphql_query, normalize_graphql_query
from soroscan.ingest.models import GraphQLRejectedQueryLog, GraphQLWhitelistedQuery
from soroscan.ingest.tests.factories import UserFactory

KNOWN_QUERY = "{ contracts { id contractId } }"


@pytest.mark.django_db
class TestGraphQLQueryHashing:
    def test_normalize_collapses_whitespace(self):
        assert (
            normalize_graphql_query("  { contracts { id } }  ")
            == "{ contracts { id } }"
        )

    def test_hash_is_stable(self):
        h1 = hash_graphql_query("{ contracts { id } }")
        h2 = hash_graphql_query("{\n  contracts { id }\n}")
        assert h1 == h2


@pytest.mark.django_db
class TestGraphQLWhitelistEnforcement:
    def _make_request(self, query: str):
        factory = RequestFactory()
        body = json.dumps({"query": query}).encode()
        return factory.post("/graphql/", data=body, content_type="application/json")

    def _make_view(self):
        view = ThrottledGraphQLView(schema=MagicMock())
        view.check_throttles = lambda r: None
        return view

    @override_settings(GRAPHQL_QUERY_WHITELIST_ENABLED=True)
    def test_unknown_query_rejected(self):
        request = self._make_request("{ unknownField }")
        response = _check_query_whitelist(request.body, request)
        assert response.status_code == 403

    @override_settings(GRAPHQL_QUERY_WHITELIST_ENABLED=True)
    def test_known_query_accepted(self):
        GraphQLWhitelistedQuery.objects.create(
            query_hash=hash_graphql_query(KNOWN_QUERY),
            query_text=KNOWN_QUERY,
            name="contracts-list",
        )
        request = self._make_request(KNOWN_QUERY)
        assert _check_query_whitelist(request.body, request) is None

    @override_settings(GRAPHQL_QUERY_WHITELIST_ENABLED=True)
    def test_unknown_query_logged(self):
        request = self._make_request("{ notRegistered }")
        _check_query_whitelist(request.body, request)
        assert GraphQLRejectedQueryLog.objects.count() == 1

    @override_settings(GRAPHQL_QUERY_WHITELIST_ENABLED=False)
    def test_developer_mode_allows_unknown(self):
        request = self._make_request("{ anything }")
        assert _check_query_whitelist(request.body, request) is None


@pytest.mark.django_db
class TestGraphQLWhitelistAdminEndpoint:
    def test_staff_can_register_query(self):
        admin = UserFactory(is_staff=True, is_superuser=True)
        client = APIClient()
        client.force_authenticate(user=admin)
        url = reverse("admin-graphql-whitelist")

        response = client.post(
            url,
            {"query": KNOWN_QUERY, "name": "contracts-list"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["created"] is True
        assert GraphQLWhitelistedQuery.objects.filter(name="contracts-list").exists()

    def test_non_staff_rejected(self):
        user = UserFactory(is_staff=False)
        client = APIClient()
        client.force_authenticate(user=user)
        url = reverse("admin-graphql-whitelist")

        response = client.post(url, {"query": KNOWN_QUERY}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_register_is_idempotent(self):
        admin = UserFactory(is_staff=True, is_superuser=True)
        client = APIClient()
        client.force_authenticate(user=admin)
        url = reverse("admin-graphql-whitelist")

        first = client.post(url, {"query": KNOWN_QUERY}, format="json")
        second = client.post(url, {"query": KNOWN_QUERY}, format="json")
        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_200_OK
        assert GraphQLWhitelistedQuery.objects.count() == 1
