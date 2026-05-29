import pytest
from django.urls import reverse
from rest_framework import status

from soroscan.ingest.models import WebhookDeliveryLog

from .factories import (
    UserFactory,
    WebhookDeliveryLogFactory,
    WebhookSubscriptionFactory,
)


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
class TestWebhookFailuresEndpoint:
    def test_requires_authentication(self, api_client):
        url = reverse("webhook-failures")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_returns_last_50_failed_deliveries(self, authenticated_client):
        sub = WebhookSubscriptionFactory(target_url="https://example.com/hook")

        for i in range(55):
            WebhookDeliveryLogFactory(
                subscription=sub,
                success=False,
                status_code=500,
                error=f"failure {i}",
            )
        WebhookDeliveryLogFactory(subscription=sub, success=True, status_code=200, error="")

        url = reverse("webhook-failures")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert len(results) == 50
        assert all(item["http_status_code"] == 500 for item in results)
        assert all(item["url"] == "https://example.com/hook" for item in results)
        assert "failure" in results[0]["error_message"]

    def test_filters_by_subscription_id(self, authenticated_client):
        sub_a = WebhookSubscriptionFactory(target_url="https://a.example/hook")
        sub_b = WebhookSubscriptionFactory(target_url="https://b.example/hook")

        WebhookDeliveryLogFactory(
            subscription=sub_a,
            success=False,
            status_code=502,
            error="a failed",
        )
        WebhookDeliveryLogFactory(
            subscription=sub_b,
            success=False,
            status_code=503,
            error="b failed",
        )

        url = reverse("webhook-failures")
        response = authenticated_client.get(url, {"subscription_id": sub_a.id})

        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert len(results) == 1
        assert results[0]["subscription_id"] == sub_a.id
        assert results[0]["url"] == "https://a.example/hook"
        assert results[0]["error_message"] == "a failed"
        assert results[0]["http_status_code"] == 502

    def test_invalid_subscription_id_returns_400(self, authenticated_client):
        url = reverse("webhook-failures")
        response = authenticated_client.get(url, {"subscription_id": "abc"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_excludes_successful_deliveries(self, authenticated_client):
        sub = WebhookSubscriptionFactory()
        WebhookDeliveryLogFactory(subscription=sub, success=True, status_code=200)

        url = reverse("webhook-failures")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []
        assert WebhookDeliveryLog.objects.filter(success=False).count() == 0
