"""Tests for batch dead-letter webhook replay (issue #1406)."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from soroscan.ingest.models import (
    WebhookDeliveryLog,
    WebhookSubscription,
)
from soroscan.ingest.tasks import replay_dead_letter_webhooks

from .factories import (
    ContractEventFactory,
    TrackedContractFactory,
    WebhookDeliveryLogFactory,
    WebhookSubscriptionFactory,
)

User = get_user_model()

# `soroscan/urls.py` mounts the v1 app at `v1/`, so this is the reachable
# path for the endpoint added in `soroscan/v1/urls.py`.
REPLAY_URL = "/v1/webhooks/dlq/replay/"

# Deterministic event timestamp. `ContractEventFactory` otherwise uses
# `Faker("date_time")`, which yields random (often pre-2026) dates, and
# `ContractEvent` is range-partitioned on timestamp with hard-coded
# 2026-08/2026-09 partitions. A fixed recent date keeps these fixtures
# deterministic and independent of that partitioning.
EVENT_TIMESTAMP = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def admin_user():
    return User.objects.create_superuser(
        username="dlq-admin", password="test", email="dlq-admin@example.com"
    )


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def regular_user():
    return User.objects.create_user(
        username="dlq-regular", password="test", email="dlq-regular@example.com"
    )


@pytest.fixture
def regular_client(regular_user):
    client = APIClient()
    client.force_authenticate(user=regular_user)
    return client


@pytest.fixture
def contract(admin_user):
    return TrackedContractFactory(owner=admin_user)


@pytest.fixture
def other_contract(admin_user):
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
def other_webhook(other_contract):
    return WebhookSubscriptionFactory(
        contract=other_contract,
        target_url="https://example.com/other",
        is_active=True,
        status=WebhookSubscription.STATUS_ACTIVE,
    )


def make_delivery(
    subscription, event, status_value=WebhookDeliveryLog.STATUS_DEAD_LETTER
):
    return WebhookDeliveryLogFactory(
        subscription=subscription,
        event=event,
        status=status_value,
        success=False,
        error="Internal Server Error",
    )


def forwarded(mock_call):
    """Return the ``(args, kwargs)`` Celery forwards from ``delay`` to ``apply_async``."""
    call_args, call_kwargs = mock_call
    args = call_args[0] if call_args else call_kwargs.get("args", ())
    kwargs = call_args[1] if len(call_args) > 1 else call_kwargs.get("kwargs", {})
    return tuple(args), dict(kwargs)


@pytest.mark.django_db
class TestReplayDeadLetterWebhooksTask:
    def test_resets_status_and_redispatches(self, webhook):
        event = ContractEventFactory(
            contract=webhook.contract, timestamp=EVENT_TIMESTAMP
        )
        delivery = make_delivery(webhook, event)

        with patch("soroscan.ingest.tasks.dispatch_webhook.apply_async") as mock_apply:
            result = replay_dead_letter_webhooks(delivery_ids=[delivery.id])

        assert result["status"] == "ok"
        assert result["requeued"] == 1
        assert result["skipped"] == 0

        delivery.refresh_from_db()
        assert delivery.status == WebhookDeliveryLog.STATUS_PENDING
        mock_apply.assert_called_once()

    def test_replays_as_replay_to_bypass_deduplication(self, webhook):
        event = ContractEventFactory(
            contract=webhook.contract, timestamp=EVENT_TIMESTAMP
        )
        delivery = make_delivery(webhook, event)

        with patch("soroscan.ingest.tasks.dispatch_webhook.apply_async") as mock_apply:
            replay_dead_letter_webhooks(delivery_ids=[delivery.id])

        args, kwargs = forwarded(mock_apply.call_args)
        assert args == (webhook.id, event.id)
        assert kwargs == {"replay": True}, "replays must bypass delivery dedup"

    def test_selects_by_contract_id(self, webhook, other_webhook):
        event = ContractEventFactory(
            contract=webhook.contract, timestamp=EVENT_TIMESTAMP
        )
        other_event = ContractEventFactory(
            contract=other_webhook.contract, timestamp=EVENT_TIMESTAMP
        )
        wanted = make_delivery(webhook, event)
        other = make_delivery(other_webhook, other_event)

        with patch("soroscan.ingest.tasks.dispatch_webhook.apply_async") as mock_apply:
            result = replay_dead_letter_webhooks(
                contract_id=webhook.contract.contract_id
            )

        assert result["requeued"] == 1
        wanted.refresh_from_db()
        other.refresh_from_db()
        assert wanted.status == WebhookDeliveryLog.STATUS_PENDING
        assert other.status == WebhookDeliveryLog.STATUS_DEAD_LETTER
        assert mock_apply.call_count == 1

    def test_ignores_non_dead_lettered_deliveries(self, webhook):
        event = ContractEventFactory(
            contract=webhook.contract, timestamp=EVENT_TIMESTAMP
        )
        delivery = make_delivery(
            webhook, event, status_value=WebhookDeliveryLog.STATUS_FAILED
        )

        with patch("soroscan.ingest.tasks.dispatch_webhook.apply_async") as mock_apply:
            result = replay_dead_letter_webhooks(delivery_ids=[delivery.id])

        assert result["requeued"] == 0
        delivery.refresh_from_db()
        assert delivery.status == WebhookDeliveryLog.STATUS_FAILED
        mock_apply.assert_not_called()

    def test_skips_deliveries_without_an_event(self, webhook):
        delivery = make_delivery(webhook, None)

        with patch("soroscan.ingest.tasks.dispatch_webhook.apply_async") as mock_apply:
            result = replay_dead_letter_webhooks(delivery_ids=[delivery.id])

        assert result["requeued"] == 0
        assert result["skipped"] == 1
        mock_apply.assert_not_called()

    def test_reactivates_suspended_subscription(self, webhook):
        webhook.status = WebhookSubscription.STATUS_SUSPENDED
        webhook.is_active = False
        webhook.save(update_fields=["status", "is_active"])
        event = ContractEventFactory(
            contract=webhook.contract, timestamp=EVENT_TIMESTAMP
        )
        delivery = make_delivery(webhook, event)

        with patch("soroscan.ingest.tasks.dispatch_webhook.apply_async"):
            replay_dead_letter_webhooks(delivery_ids=[delivery.id])

        webhook.refresh_from_db()
        assert webhook.is_active is True
        assert webhook.status == WebhookSubscription.STATUS_ACTIVE

    def test_requires_a_selection(self):
        result = replay_dead_letter_webhooks()
        assert result["status"] == "skipped"
        assert result["reason"] == "no_selection"

    def test_handles_unknown_delivery_ids(self):
        result = replay_dead_letter_webhooks(delivery_ids=[987654])
        assert result["status"] == "ok"
        assert result["requeued"] == 0
        assert result["skipped"] == 0


@pytest.mark.django_db
class TestReplayDlqWebhooksAPI:
    @patch("soroscan.ingest.tasks.replay_dead_letter_webhooks.apply_async")
    def test_endpoint_queues_task_for_delivery_ids(
        self, mock_apply, admin_client, webhook
    ):
        event = ContractEventFactory(
            contract=webhook.contract, timestamp=EVENT_TIMESTAMP
        )
        delivery = make_delivery(webhook, event)

        response = admin_client.post(
            REPLAY_URL,
            {"delivery_ids": [delivery.id]},
            format="json",
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.data["contract_id"] is None
        mock_apply.assert_called_once()
        args, kwargs = forwarded(mock_apply.call_args)
        assert args == ()
        assert kwargs == {
            "delivery_ids": [delivery.id],
            "contract_id": None,
        }

    @patch("soroscan.ingest.tasks.replay_dead_letter_webhooks.apply_async")
    def test_endpoint_queues_task_for_contract_id(
        self, mock_apply, admin_client, webhook
    ):
        response = admin_client.post(
            REPLAY_URL,
            {"contract_id": webhook.contract.contract_id},
            format="json",
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        args, kwargs = forwarded(mock_apply.call_args)
        assert args == ()
        assert kwargs == {
            "delivery_ids": None,
            "contract_id": webhook.contract.contract_id,
        }

    @patch("soroscan.ingest.tasks.dispatch_webhook.apply_async")
    def test_endpoint_work_runs_through_the_task(
        self, mock_dispatch, admin_client, webhook
    ):
        """With eager Celery the queued task performs the replay inline."""
        event = ContractEventFactory(
            contract=webhook.contract, timestamp=EVENT_TIMESTAMP
        )
        delivery = make_delivery(webhook, event)

        response = admin_client.post(
            REPLAY_URL,
            {"delivery_ids": [delivery.id]},
            format="json",
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        delivery.refresh_from_db()
        assert delivery.status == WebhookDeliveryLog.STATUS_PENDING
        mock_dispatch.assert_called_once()

    def test_endpoint_rejects_missing_selection(self, admin_client):
        response = admin_client.post(REPLAY_URL, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_endpoint_rejects_non_list_delivery_ids(self, admin_client):
        response = admin_client.post(REPLAY_URL, {"delivery_ids": "1,2"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_endpoint_rejects_non_string_contract_id(self, admin_client):
        response = admin_client.post(REPLAY_URL, {"contract_id": 7}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_endpoint_requires_staff(self, regular_client, webhook):
        response = regular_client.post(
            REPLAY_URL,
            {"contract_id": webhook.contract.contract_id},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_endpoint_requires_authentication(self):
        response = APIClient().post(REPLAY_URL, {"contract_id": "C"}, format="json")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_endpoint_accepts_path_without_trailing_slash(self, admin_client, webhook):
        with patch("soroscan.ingest.tasks.replay_dead_letter_webhooks.apply_async"):
            response = admin_client.post(
                "/v1/webhooks/dlq/replay",
                {"contract_id": webhook.contract.contract_id},
                format="json",
            )
        assert response.status_code == status.HTTP_202_ACCEPTED

    def test_endpoint_only_accepts_post(self, admin_client, webhook):
        with patch("soroscan.ingest.tasks.replay_dead_letter_webhooks.apply_async"):
            response = admin_client.get(REPLAY_URL)
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
