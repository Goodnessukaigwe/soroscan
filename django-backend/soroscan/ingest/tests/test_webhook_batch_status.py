import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status

from .factories import UserFactory, WebhookDeliveryLogFactory


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def authenticated_client(api_client):
    user = UserFactory()
    api_client.force_authenticate(user=user)
    return api_client


@pytest.mark.django_db
class TestWebhookBatchDeliveryStatus:
    def test_requires_authentication(self, api_client):
        url = reverse("webhook-batch-delivery-status")
        response = api_client.post(url, {"delivery_ids": [1]}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_returns_status_for_multiple_deliveries_in_one_query(self, authenticated_client):
        success_log = WebhookDeliveryLogFactory(success=True, status_code=200)
        failed_log = WebhookDeliveryLogFactory(success=False, status_code=500, error="timeout")

        url = reverse("webhook-batch-delivery-status")
        delivery_ids = [success_log.id, failed_log.id, 999999]

        with CaptureQueriesContext(connection) as context:
            response = authenticated_client.post(
                url,
                {"delivery_ids": delivery_ids},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert len(context) == 1

        deliveries = response.data["deliveries"]
        assert len(deliveries) == 3
        assert deliveries[0]["status"] == "success"
        assert deliveries[0]["http_status_code"] == 200
        assert deliveries[1]["status"] == "failed"
        assert deliveries[1]["http_status_code"] == 500
        assert deliveries[2]["status"] == "not_found"

    def test_preserves_request_order(self, authenticated_client):
        first = WebhookDeliveryLogFactory(success=True, status_code=201)
        second = WebhookDeliveryLogFactory(success=False, status_code=503)

        url = reverse("webhook-batch-delivery-status")
        response = authenticated_client.post(
            url,
            {"delivery_ids": [second.id, first.id]},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in response.data["deliveries"]]
        assert ids == [second.id, first.id]

    def test_rejects_empty_delivery_ids(self, authenticated_client):
        url = reverse("webhook-batch-delivery-status")
        response = authenticated_client.post(url, {"delivery_ids": []}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_non_integer_ids(self, authenticated_client):
        url = reverse("webhook-batch-delivery-status")
        response = authenticated_client.post(
            url,
            {"delivery_ids": ["abc"]},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_more_than_200_ids(self, authenticated_client):
        url = reverse("webhook-batch-delivery-status")
        response = authenticated_client.post(
            url,
            {"delivery_ids": list(range(1, 202))},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
