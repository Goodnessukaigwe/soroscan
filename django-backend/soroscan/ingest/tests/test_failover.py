"""Automated failover tests for dependency health and recovery.

Simulates database, Redis, Soroban RPC, and Celery worker failures at the
same abstraction boundary used by `soroscan.health`, then verifies probes
degrade and recover when dependencies return.

Queued work recovery is asserted only where the application already
guarantees idempotency: ContractEvent uniqueness on
(contract, ledger, event_index).
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from soroscan.ingest.models import ContractEvent
from soroscan.ingest.tests.failover_helpers import (
    database_unavailable,
    redis_unavailable,
    rpc_healthy,
    rpc_timeout,
    workers_healthy,
    workers_unresponsive,
)
from soroscan.ingest.tests.factories import ContractEventFactory, TrackedContractFactory


@pytest.fixture
def api_client():
    return APIClient()


def assert_readiness_healthy(response):
    assert response.status_code == status.HTTP_200_OK, f"Expected 200 but got {response.status_code}: {response.data}"
    assert response.data["status"] == "healthy"
    assert response.data["components"]["database"] == "healthy"
    assert response.data["components"]["redis"] == "healthy"
    assert response.data["components"]["soroban_rpc"] == "healthy"


def assert_readiness_degraded(response, component: str):
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.data["status"] == "degraded"
    assert component in response.data["components"]
    assert "degraded" in response.data["components"][component]


@pytest.mark.failover
@pytest.mark.django_db
class TestDatabaseConnectionFailover:
    def test_readiness_degrades_on_database_failure(self, api_client):
        readiness_url = reverse("readiness")
        with rpc_healthy():
            assert_readiness_healthy(api_client.get(readiness_url))
            with database_unavailable():
                degraded = api_client.get(readiness_url)
            assert_readiness_degraded(degraded, "database")
            assert api_client.get(reverse("health")).status_code == status.HTTP_200_OK

    def test_readiness_recovers_after_database_restored(self, api_client):
        readiness_url = reverse("readiness")
        with rpc_healthy():
            with database_unavailable():
                assert_readiness_degraded(api_client.get(readiness_url), "database")
            assert_readiness_healthy(api_client.get(readiness_url))


@pytest.mark.failover
@pytest.mark.django_db
class TestRedisConnectionFailover:
    def test_readiness_degrades_on_redis_failure(self, api_client):
        readiness_url = reverse("readiness")
        with rpc_healthy():
            assert_readiness_healthy(api_client.get(readiness_url))
            with redis_unavailable():
                degraded = api_client.get(readiness_url)
            assert_readiness_degraded(degraded, "redis")
            assert api_client.get(reverse("health")).status_code == status.HTTP_200_OK

    def test_readiness_recovers_after_redis_restored(self, api_client):
        readiness_url = reverse("readiness")
        with rpc_healthy():
            with redis_unavailable():
                assert_readiness_degraded(api_client.get(readiness_url), "redis")
            assert_readiness_healthy(api_client.get(readiness_url))


@pytest.mark.failover
@pytest.mark.django_db
class TestRpcTimeoutFailover:
    def test_readiness_degrades_on_rpc_timeout(self, api_client):
        readiness_url = reverse("readiness")
        with rpc_healthy():
            assert_readiness_healthy(api_client.get(readiness_url))
        with rpc_timeout():
            degraded = api_client.get(readiness_url)
        assert_readiness_degraded(degraded, "soroban_rpc")
        assert api_client.get(reverse("health")).status_code == status.HTTP_200_OK

    def test_readiness_recovers_after_rpc_timeout_cleared(self, api_client):
        readiness_url = reverse("readiness")
        with rpc_timeout():
            assert_readiness_degraded(api_client.get(readiness_url), "soroban_rpc")
        with rpc_healthy():
            assert_readiness_healthy(api_client.get(readiness_url))


@pytest.mark.failover
@pytest.mark.django_db
class TestMultipleWorkerFailover:
    def test_worker_health_degrades_when_no_workers_respond(self, api_client):
        with workers_unresponsive("empty"):
            response = api_client.get(reverse("worker-health"))
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.data["status"] == "unhealthy"
        assert "no worker responded" in response.data["error"]

    def test_worker_health_degrades_on_ping_timeout(self, api_client):
        with workers_unresponsive("timeout"):
            response = api_client.get(reverse("worker-health"))
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.data["status"] == "unhealthy"
        assert "worker ping timeout" in response.data["error"]

    def test_worker_health_recovers_when_workers_respond(self, api_client):
        worker_status = {
            "worker1@host-a": {"ok": "pong"},
            "worker2@host-b": {"ok": "pong"},
        }
        with workers_unresponsive("empty"):
            degraded = api_client.get(reverse("worker-health"))
        assert degraded.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

        with workers_healthy(worker_status):
            recovered = api_client.get(reverse("worker-health"))
        assert recovered.status_code == status.HTTP_200_OK
        assert recovered.data["status"] == "healthy"
        assert recovered.data["workers"] == worker_status

    def test_partial_worker_failure_still_reports_healthy(self, api_client):
        with workers_healthy({"worker1@host-a": {"ok": "pong"}}):
            response = api_client.get(reverse("worker-health"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "healthy"

    def test_reingest_after_worker_failure_does_not_duplicate_events(self):
        """Celery tests run eager, so queue replay is modeled as a second insert.

        The application guarantee is UniqueConstraint(contract, ledger, event_index).
        """
        contract = TrackedContractFactory()
        event = ContractEventFactory(contract=contract, ledger=4242, event_index=0)
        assert ContractEvent.objects.filter(contract=contract, ledger=4242, event_index=0).count() == 1
        with workers_unresponsive("empty"):
            pass
        with transaction.atomic():
            with pytest.raises(IntegrityError):
                ContractEvent.objects.create(
                    contract=contract,
                    event_type=event.event_type,
                    payload=event.payload,
                    payload_hash=event.payload_hash,
                    ledger=event.ledger,
                    event_index=event.event_index,
                    timestamp=event.timestamp,
                    tx_hash=event.tx_hash,
                )
        assert ContractEvent.objects.filter(contract=contract, ledger=4242, event_index=0).count() == 1


@pytest.mark.failover
@pytest.mark.django_db
class TestCombinedFailoverRecovery:
    def test_readiness_recovers_after_multiple_dependency_failures(self, api_client):
        readiness_url = reverse("readiness")
        with rpc_healthy():
            with database_unavailable(), redis_unavailable():
                response = api_client.get(readiness_url)
                assert_readiness_degraded(response, "database")
                assert "degraded" in response.data["components"]["redis"]
            assert_readiness_healthy(api_client.get(readiness_url))
