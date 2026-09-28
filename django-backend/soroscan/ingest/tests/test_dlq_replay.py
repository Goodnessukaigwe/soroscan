"""Tests for Dead Letter Queue replay functionality (issue #1311)."""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from soroscan.ingest.models import (
    WebhookSubscription,
)
from soroscan.ingest.tasks import replay_dead_letter

from .factories import (
    ContractEventFactory,
    TrackedContractFactory,
    WebhookDeadLetterFactory,
    WebhookSubscriptionFactory,
)

User = get_user_model()


@pytest.fixture
def admin_user():
    return User.objects.create_superuser(username="admin", password="test", email="a@b.com")


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def regular_user():
    return User.objects.create_user(username="regular", password="test", email="r@b.com")


@pytest.fixture
def regular_client(regular_user):
    client = APIClient()
    client.force_authenticate(user=regular_user)
    return client


@pytest.fixture
def contract(admin_user):
    return TrackedContractFactory(owner=admin_user)


@pytest.fixture
def webhook(contract):
    return WebhookSubscriptionFactory(
        contract=contract,
        target_url="https://example.com/webhook",
        is_active=True,
        status=WebhookSubscription.STATUS_ACTIVE,
    )


@pytest.fixture
def event(contract):
    return ContractEventFactory(contract=contract)


@pytest.fixture
def dlq_entry(webhook, event):
    return WebhookDeadLetterFactory(
        subscription=webhook,
        event=event,
        payload={"test": "data"},
        status_code=500,
        error="Internal Server Error",
        retries_exhausted=6,
        resolved=False,
    )


@pytest.mark.django_db
class TestDLQReplayTask:
    def test_replay_dispatches_webhook(self, dlq_entry):
        with patch("soroscan.ingest.tasks.dispatch_webhook.apply_async") as mock_apply:
            result = replay_dead_letter(dlq_entry.id)

        assert result["status"] == "replayed"
        mock_apply.assert_called_once()

    def test_replay_marks_entry_resolved(self, dlq_entry):
        with patch("soroscan.ingest.tasks.dispatch_webhook.apply_async"):
            replay_dead_letter(dlq_entry.id)

        dlq_entry.refresh_from_db()
        assert dlq_entry.resolved is True
        assert "Replayed" in dlq_entry.resolution_note

    def test_replay_skips_already_resolved(self, dlq_entry):
        dlq_entry.resolved = True
        dlq_entry.save(update_fields=["resolved"])

        result = replay_dead_letter(dlq_entry.id)
        assert result["status"] == "skipped"
        assert result["reason"] == "already_resolved"

    def test_replay_skips_missing_event(self, dlq_entry):
        dlq_entry.event = None
        dlq_entry.save(update_fields=["event"])

        result = replay_dead_letter(dlq_entry.id)
        assert result["status"] == "skipped"
        assert result["reason"] == "event_missing"

    def test_replay_skips_nonexistent_entry(self):
        result = replay_dead_letter(99999)
        assert result["status"] == "skipped"
        assert result["reason"] == "not_found"

    def test_replay_reactivates_suspended_subscription(self, dlq_entry):
        dlq_entry.subscription.status = WebhookSubscription.STATUS_SUSPENDED
        dlq_entry.subscription.is_active = False
        dlq_entry.subscription.save(update_fields=["status", "is_active"])

        with patch("soroscan.ingest.tasks.dispatch_webhook.apply_async"):
            replay_dead_letter(dlq_entry.id)

        dlq_entry.subscription.refresh_from_db()
        assert dlq_entry.subscription.is_active is True
        assert dlq_entry.subscription.status == WebhookSubscription.STATUS_ACTIVE


@pytest.mark.django_db
class TestDLQListAPI:
    def test_list_dlq_entries(self, admin_client, dlq_entry):
        response = admin_client.get("/api/ingest/dead-letter-queue/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["id"] == dlq_entry.id

    def test_filter_by_resolved(self, admin_client, dlq_entry):
        response = admin_client.get("/api/ingest/dead-letter-queue/", {"resolved": "false"})
        assert len(response.data) == 1

        dlq_entry.resolved = True
        dlq_entry.save(update_fields=["resolved"])

        response = admin_client.get("/api/ingest/dead-letter-queue/", {"resolved": "false"})
        assert len(response.data) == 0

    def test_non_admin_forbidden(self, regular_client):
        response = regular_client.get("/api/ingest/dead-letter-queue/")
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestDLQReplayAPI:
    @patch("soroscan.ingest.tasks.dispatch_webhook.apply_async")
    def test_replay_entries(self, mock_apply, admin_client, dlq_entry):
        response = admin_client.post(
            "/api/ingest/dead-letter-queue/replay/",
            {"entry_ids": [dlq_entry.id]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["queued"] == 1
        assert response.data["skipped"] == 0
        mock_apply.assert_called_once()

    def test_replay_skips_resolved(self, admin_client, dlq_entry):
        dlq_entry.resolved = True
        dlq_entry.save(update_fields=["resolved"])

        response = admin_client.post(
            "/api/ingest/dead-letter-queue/replay/",
            {"entry_ids": [dlq_entry.id]},
            format="json",
        )
        assert response.data["queued"] == 0

    def test_replay_requires_entry_ids(self, admin_client):
        response = admin_client.post(
            "/api/ingest/dead-letter-queue/replay/",
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_admin_forbidden(self, regular_client, dlq_entry):
        response = regular_client.post(
            "/api/ingest/dead-letter-queue/replay/",
            {"entry_ids": [dlq_entry.id]},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
