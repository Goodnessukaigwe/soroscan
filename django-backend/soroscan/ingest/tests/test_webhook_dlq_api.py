"""Tests for GET /api/v1/webhooks/dlq/ (issue #1405)."""
from datetime import datetime, timezone as dt_timezone

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from soroscan.ingest.models import WebhookDeliveryLog

from .factories import (
    TrackedContractFactory,
    UserFactory,
    WebhookDeliveryLogFactory,
    WebhookSubscriptionFactory,
)

URL = reverse("webhook-dlq-list")


def _dead_letter(subscription, timestamp=None, status_code=500):
    log = WebhookDeliveryLogFactory(
        subscription=subscription,
        status=WebhookDeliveryLog.STATUS_DEAD_LETTER,
        status_code=status_code,
        success=False,
    )
    if timestamp is not None:
        WebhookDeliveryLog.objects.filter(pk=log.pk).update(timestamp=timestamp)
    return log


@pytest.fixture
def owner():
    return UserFactory()


@pytest.fixture
def client(owner):
    api_client = APIClient()
    api_client.force_authenticate(user=owner)
    return api_client


@pytest.fixture
def subscription(owner):
    return WebhookSubscriptionFactory(contract=TrackedContractFactory(owner=owner))


@pytest.mark.django_db
class TestWebhookDLQAPI:
    def test_requires_authentication(self):
        response = APIClient().get(URL)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_returns_only_dead_letter_logs_paginated(self, client, subscription):
        dead = _dead_letter(subscription)
        WebhookDeliveryLogFactory(subscription=subscription)  # success
        WebhookDeliveryLogFactory(
            subscription=subscription, status=WebhookDeliveryLog.STATUS_FAILED
        )

        response = client.get(URL)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        result = response.data["results"][0]
        assert result["id"] == dead.id
        assert result["status"] == WebhookDeliveryLog.STATUS_DEAD_LETTER
        assert result["contract_id"] == subscription.contract.contract_id

    def test_excludes_logs_for_other_users_contracts(self, client, subscription):
        _dead_letter(subscription)
        _dead_letter(WebhookSubscriptionFactory())  # someone else's contract

        response = client.get(URL)

        assert response.data["count"] == 1

    def test_staff_sees_all_logs(self, subscription):
        _dead_letter(subscription)
        _dead_letter(WebhookSubscriptionFactory())
        staff_client = APIClient()
        staff_client.force_authenticate(user=UserFactory(is_staff=True))

        response = staff_client.get(URL)

        assert response.data["count"] == 2

    def test_filter_by_contract_id(self, client, owner, subscription):
        other = WebhookSubscriptionFactory(contract=TrackedContractFactory(owner=owner))
        _dead_letter(subscription)
        target = _dead_letter(other)

        response = client.get(URL, {"contract_id": other.contract.contract_id})

        assert [r["id"] for r in response.data["results"]] == [target.id]

    def test_filter_by_date_range(self, client, subscription):
        _dead_letter(subscription, datetime(2026, 1, 1, tzinfo=dt_timezone.utc))
        middle = _dead_letter(subscription, datetime(2026, 2, 15, tzinfo=dt_timezone.utc))
        _dead_letter(subscription, datetime(2026, 4, 1, tzinfo=dt_timezone.utc))

        response = client.get(URL, {"start_date": "2026-02-01", "end_date": "2026-03-01"})

        assert [r["id"] for r in response.data["results"]] == [middle.id]

    def test_filter_by_status_code(self, client, subscription):
        _dead_letter(subscription, status_code=500)
        target = _dead_letter(subscription, status_code=404)

        response = client.get(URL, {"status": "404"})

        assert [r["id"] for r in response.data["results"]] == [target.id]

    def test_invalid_date_returns_400(self, client):
        response = client.get(URL, {"start_date": "not-a-date"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
