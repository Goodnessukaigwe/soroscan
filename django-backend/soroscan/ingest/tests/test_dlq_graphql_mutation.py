"""Tests for the replayDeadLetterWebhooks GraphQL mutation (issue #1409)."""

from datetime import datetime, timezone
import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from strawberry.django.views import GraphQLView

from soroscan.ingest.models import WebhookDeliveryLog, WebhookSubscription

from .factories import (
    ContractEventFactory,
    TrackedContractFactory,
    WebhookDeliveryLogFactory,
    WebhookSubscriptionFactory,
)

User = get_user_model()

# `ContractEventFactory` otherwise uses `Faker("date_time")`, which yields
# random (often pre-2026) dates, and `ContractEvent` is range-partitioned on
# timestamp with hard-coded 2026-08/2026-09 partitions. A fixed recent date
# keeps these fixtures deterministic and independent of that partitioning.
EVENT_TIMESTAMP = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)

REPLAY_MUTATION = """
    mutation Replay($ids: [ID!]!) {
        replayDeadLetterWebhooks(deliveryIds: $ids)
    }
"""


@pytest.fixture
def staff_user():
    return User.objects.create_superuser(
        username="dlq-staff", password="test", email="dlq-staff@example.com"
    )


@pytest.fixture
def regular_user():
    return User.objects.create_user(
        username="dlq-user", password="test", email="dlq-user@example.com"
    )


@pytest.fixture
def contract():
    return TrackedContractFactory()


@pytest.fixture
def other_contract():
    return TrackedContractFactory()


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


def forwarded(mock_call):
    """Return the ``(args, kwargs)`` Celery forwards from ``delay`` to ``apply_async``."""
    call_args, call_kwargs = mock_call
    args = call_args[0] if call_args else call_kwargs.get("args", ())
    kwargs = call_args[1] if len(call_args) > 1 else call_kwargs.get("kwargs", {})
    return tuple(args), dict(kwargs)


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


def execute_mutation(user, delivery_ids):
    """Execute the mutation as `user` and return the Strawberry result.

    `StrawberryDjangoContext` is what the view builds in production, and the
    repo's permission decorators read `info.context.request` while the rate
    limit and logging extensions read `context.get("request")`, so the context
    has to be that type rather than a plain dict.
    """
    from soroscan.ingest.schema import schema
    from strawberry.django.context import StrawberryDjangoContext

    request = RequestFactory().post(
        "/graphql/",
        data=json.dumps({"query": REPLAY_MUTATION}),
        content_type="application/json",
        REMOTE_ADDR="127.0.0.1",
    )
    request.user = user

    return schema.execute_sync(
        REPLAY_MUTATION,
        variable_values={"ids": [str(i) for i in delivery_ids]},
        context_value=StrawberryDjangoContext(request=request, response=None),
    )


@pytest.mark.django_db
class TestReplayDeadLetterWebhooksMutation:
    def test_requeues_and_returns_count(self, staff_user, webhook):
        event = ContractEventFactory(
            contract=webhook.contract, timestamp=EVENT_TIMESTAMP
        )
        delivery = make_delivery(webhook, event)

        with patch("soroscan.ingest.tasks.dispatch_webhook.apply_async") as mock_apply:
            result = execute_mutation(staff_user, [delivery.id])

        assert result.errors is None
        assert result.data == {"replayDeadLetterWebhooks": 1}
        delivery.refresh_from_db()
        assert delivery.status == WebhookDeliveryLog.STATUS_PENDING
        assert mock_apply.call_count == 1

    def test_replays_bypass_deduplication(self, staff_user, webhook):
        event = ContractEventFactory(
            contract=webhook.contract, timestamp=EVENT_TIMESTAMP
        )
        delivery = make_delivery(webhook, event)

        with patch("soroscan.ingest.tasks.dispatch_webhook.apply_async") as mock_apply:
            execute_mutation(staff_user, [delivery.id])

        # `Task.delay(*args, **kwargs)` forwards to `apply_async(args, kwargs)`.
        args, kwargs = forwarded(mock_apply.call_args)
        assert args == (webhook.id, event.id)
        assert kwargs == {"replay": True}, "replays must bypass delivery dedup"

    def test_requeues_multiple_deliveries(self, staff_user, webhook, other_webhook):
        first_event = ContractEventFactory(
            contract=webhook.contract, timestamp=EVENT_TIMESTAMP
        )
        second_event = ContractEventFactory(
            contract=other_webhook.contract, timestamp=EVENT_TIMESTAMP
        )
        first = make_delivery(webhook, first_event)
        second = make_delivery(other_webhook, second_event)

        with patch("soroscan.ingest.tasks.dispatch_webhook.apply_async"):
            result = execute_mutation(staff_user, [first.id, second.id])

        assert result.data == {"replayDeadLetterWebhooks": 2}
        first.refresh_from_db()
        second.refresh_from_db()
        assert first.status == WebhookDeliveryLog.STATUS_PENDING
        assert second.status == WebhookDeliveryLog.STATUS_PENDING

    def test_ignores_non_dead_lettered_deliveries(self, staff_user, webhook):
        event = ContractEventFactory(
            contract=webhook.contract, timestamp=EVENT_TIMESTAMP
        )
        delivery = make_delivery(
            webhook, event, status_value=WebhookDeliveryLog.STATUS_FAILED
        )

        with patch("soroscan.ingest.tasks.dispatch_webhook.apply_async") as mock_apply:
            result = execute_mutation(staff_user, [delivery.id])

        assert result.data == {"replayDeadLetterWebhooks": 0}
        delivery.refresh_from_db()
        assert delivery.status == WebhookDeliveryLog.STATUS_FAILED
        mock_apply.assert_not_called()

    def test_skips_deliveries_without_an_event(self, staff_user, webhook):
        delivery = make_delivery(webhook, None)

        with patch("soroscan.ingest.tasks.dispatch_webhook.apply_async") as mock_apply:
            result = execute_mutation(staff_user, [delivery.id])

        assert result.data == {"replayDeadLetterWebhooks": 0}
        mock_apply.assert_not_called()

    def test_reactivates_suspended_subscription(self, staff_user, webhook):
        webhook.status = WebhookSubscription.STATUS_SUSPENDED
        webhook.is_active = False
        webhook.save(update_fields=["status", "is_active"])
        event = ContractEventFactory(
            contract=webhook.contract, timestamp=EVENT_TIMESTAMP
        )
        delivery = make_delivery(webhook, event)

        with patch("soroscan.ingest.tasks.dispatch_webhook.apply_async"):
            result = execute_mutation(staff_user, [delivery.id])

        assert result.data == {"replayDeadLetterWebhooks": 1}
        webhook.refresh_from_db()
        assert webhook.is_active is True
        assert webhook.status == WebhookSubscription.STATUS_ACTIVE

    def test_empty_list_returns_zero(self, staff_user):
        with patch("soroscan.ingest.tasks.dispatch_webhook.apply_async") as mock_apply:
            result = execute_mutation(staff_user, [])

        assert result.data == {"replayDeadLetterWebhooks": 0}
        mock_apply.assert_not_called()

    def test_unknown_ids_return_zero(self, staff_user):
        result = execute_mutation(staff_user, [987654])
        assert result.data == {"replayDeadLetterWebhooks": 0}

    def test_non_staff_is_denied(self, regular_user, webhook):
        event = ContractEventFactory(
            contract=webhook.contract, timestamp=EVENT_TIMESTAMP
        )
        delivery = make_delivery(webhook, event)

        with patch("soroscan.ingest.tasks.dispatch_webhook.apply_async") as mock_apply:
            result = execute_mutation(regular_user, [delivery.id])

        assert result.errors, "non-staff callers must be rejected"
        delivery.refresh_from_db()
        assert delivery.status == WebhookDeliveryLog.STATUS_DEAD_LETTER
        mock_apply.assert_not_called()

    def test_anonymous_is_denied(self, webhook):
        from django.contrib.auth.models import AnonymousUser

        with patch("soroscan.ingest.tasks.dispatch_webhook.apply_async"):
            result = execute_mutation(AnonymousUser(), [1])

        assert result.errors, "anonymous callers must be rejected"

    def test_non_integer_id_is_rejected(self, staff_user):
        result = execute_mutation(staff_user, ["not-a-number"])
        assert result.errors, "a non-integer delivery id must be rejected"


@pytest.mark.django_db
def test_mutation_is_present_in_the_schema():
    from soroscan.ingest.schema import schema

    assert "replayDeadLetterWebhooks(deliveryIds: [ID!]!): Int!" in schema.as_str()


def test_graphql_view_is_importable():
    """The mutation must not break the GraphQL view import used by routing."""
    assert GraphQLView is not None
