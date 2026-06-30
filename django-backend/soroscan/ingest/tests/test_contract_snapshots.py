"""
Tests for contract snapshot capture, diff tracking, API, GraphQL, admin, and tasks.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from soroscan.ingest.models import ContractSnapshot, StateChange
from soroscan.ingest.services.contract_state import (
    compute_state_diff,
    create_contract_snapshot,
    decode_state_payload,
    normalize_state_payload,
    should_snapshot_contract,
)
from soroscan.ingest.tasks import snapshot_contract_state
from soroscan.ingest.tests.factories import TrackedContractFactory, UserFactory

User = get_user_model()


@pytest.mark.django_db
class TestStateDiff:
    def test_detects_nested_update(self):
        old = {"config": {"paused": False, "limit": 10}}
        new = {"config": {"paused": True, "limit": 10}}
        changes = compute_state_diff(old, new)
        assert len(changes) == 1
        assert changes[0]["field_name"] == "config.paused"
        assert changes[0]["change_type"] == StateChange.ChangeType.UPDATE

    def test_detects_array_insert(self):
        old = {"items": ["a"]}
        new = {"items": ["a", "b"]}
        changes = compute_state_diff(old, new)
        assert any(
            c["field_name"] == "items[1]" and c["change_type"] == "insert"
            for c in changes
        )

    def test_detects_top_level_insert(self):
        changes = compute_state_diff({}, {"supply": 100})
        assert changes[0]["change_type"] == StateChange.ChangeType.INSERT
        assert changes[0]["field_name"] == "supply"


@pytest.mark.django_db
class TestSnapshotService:
    def test_create_snapshot_records_changes(self):
        contract = TrackedContractFactory(last_indexed_ledger=1000)
        create_contract_snapshot(contract, 1000, {"supply": 100})
        create_contract_snapshot(contract, 2000, {"supply": 150, "paused": True})

        snapshots = ContractSnapshot.objects.filter(contract=contract).order_by(
            "ledger_sequence"
        )
        assert snapshots.count() == 2
        latest = snapshots.last()
        field_names = {c.field_name for c in latest.changes.all()}
        assert "supply" in field_names
        assert "paused" in field_names

    def test_should_snapshot_at_interval(self):
        contract = TrackedContractFactory(last_indexed_ledger=2000)
        assert should_snapshot_contract(contract, interval=1000) is True
        contract.last_indexed_ledger = 1500
        assert should_snapshot_contract(contract, interval=1000) is False

    def test_normalize_compresses_large_payload(self, settings):
        settings.CONTRACT_SNAPSHOT_MAX_BYTES = 200
        large = {"entries": {"k": "x" * 500}}
        prepared = normalize_state_payload(large)
        assert prepared.get("_compressed") or prepared.get("_truncated")
        decoded = decode_state_payload(prepared)
        if prepared.get("_compressed"):
            assert decoded["entries"]["k"].startswith("x")


@pytest.mark.django_db
class TestSnapshotAPI:
    def test_list_snapshots_with_ledger_filters(self):
        user = UserFactory()
        contract = TrackedContractFactory(owner=user, last_indexed_ledger=3000)
        create_contract_snapshot(contract, 1000, {"v": 1})
        create_contract_snapshot(contract, 2000, {"v": 2})
        create_contract_snapshot(contract, 3000, {"v": 3})

        client = APIClient()
        client.force_authenticate(user=user)
        url = reverse("contract-snapshots", kwargs={"pk": contract.pk})
        response = client.get(url, {"ledger_min": 1500, "ledger_max": 2500})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["ledger_sequence"] == 2000
        assert len(response.data[0]["changes"]) >= 0


@pytest.mark.django_db
class TestSnapshotGraphQL:
    def test_contract_state_query(self):
        from soroscan.ingest.schema import schema

        contract = TrackedContractFactory(last_indexed_ledger=1000)
        create_contract_snapshot(contract, 1000, {"supply": 42})

        query = """
        query($contractId: String!, $ledger: Int!) {
          contractState(contractId: $contractId, ledger: $ledger) {
            contractId
            ledger
            stateData
          }
        }
        """
        result = schema.execute_sync(
            query,
            variable_values={
                "contractId": contract.contract_id,
                "ledger": 1000,
            },
        )
        assert result.errors is None
        assert result.data["contractState"]["ledger"] == 1000
        assert result.data["contractState"]["stateData"]["supply"] == 42


@pytest.mark.django_db
class TestSnapshotTask:
    @patch("soroscan.ingest.tasks.SorobanClient")
    def test_snapshot_task_captures_eligible_contracts(self, mock_client_cls):
        contract = TrackedContractFactory(is_active=True, last_indexed_ledger=1000)
        TrackedContractFactory(is_active=True, last_indexed_ledger=1001)

        mock_client = MagicMock()
        mock_client.get_contract_state.return_value = {"entries": {}}
        mock_client_cls.return_value = mock_client

        result = snapshot_contract_state()
        assert result["captured"] == 1
        assert ContractSnapshot.objects.filter(contract=contract).count() == 1


@pytest.mark.django_db
class TestSnapshotAdmin:
    def test_state_timeline_view(self):
        admin_user = UserFactory(is_staff=True, is_superuser=True)
        contract = TrackedContractFactory()
        create_contract_snapshot(contract, 1000, {"supply": 1})
        create_contract_snapshot(contract, 2000, {"supply": 2})

        client = Client()
        client.force_login(admin_user)
        url = reverse("admin:ingest_trackedcontract_state_timeline", args=[contract.pk])
        response = client.get(url)

        assert response.status_code == 200
        assert b"State timeline" in response.content
        assert b"1000" in response.content
        assert b"2000" in response.content
