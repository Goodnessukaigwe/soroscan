"""
Tests for per-contract event whitelist/blacklist filtering.

Covers:
  - TrackedContract.should_ingest_event() logic
  - Ingest pipeline (_upsert_contract_event) respects filter
  - Prometheus metric incremented on filtered events
  - Serializer exposes new fields
  - GraphQL updateContract mutation sets filter fields
  - Admin list_filter includes event_filter_type
"""
import pytest
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model

from soroscan.ingest.models import ContractEvent
from soroscan.ingest.schema import schema
from soroscan.ingest.serializers import TrackedContractSerializer
from soroscan.ingest.tasks import _network_label, _upsert_contract_event

from .factories import TrackedContractFactory, UserFactory

User = get_user_model()


# ---------------------------------------------------------------------------
# Model: should_ingest_event
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestShouldIngestEvent:
    def test_none_filter_always_true(self):
        contract = TrackedContractFactory(event_filter_type="none", event_filter_list=[])
        assert contract.should_ingest_event("transfer") is True
        assert contract.should_ingest_event("approval") is True

    def test_whitelist_allows_listed_type(self):
        contract = TrackedContractFactory(
            event_filter_type="whitelist",
            event_filter_list=["transfer", "swap"],
        )
        assert contract.should_ingest_event("transfer") is True
        assert contract.should_ingest_event("swap") is True

    def test_whitelist_drops_unlisted_type(self):
        contract = TrackedContractFactory(
            event_filter_type="whitelist",
            event_filter_list=["transfer"],
        )
        assert contract.should_ingest_event("approval") is False
        assert contract.should_ingest_event("mint") is False

    def test_blacklist_drops_listed_type(self):
        contract = TrackedContractFactory(
            event_filter_type="blacklist",
            event_filter_list=["approval", "mint"],
        )
        assert contract.should_ingest_event("approval") is False
        assert contract.should_ingest_event("mint") is False

    def test_blacklist_allows_unlisted_type(self):
        contract = TrackedContractFactory(
            event_filter_type="blacklist",
            event_filter_list=["approval"],
        )
        assert contract.should_ingest_event("transfer") is True
        assert contract.should_ingest_event("swap") is True

    def test_whitelist_empty_list_drops_all(self):
        contract = TrackedContractFactory(
            event_filter_type="whitelist",
            event_filter_list=[],
        )
        assert contract.should_ingest_event("transfer") is False

    def test_blacklist_empty_list_allows_all(self):
        contract = TrackedContractFactory(
            event_filter_type="blacklist",
            event_filter_list=[],
        )
        assert contract.should_ingest_event("transfer") is True

    def test_default_filter_type_is_none(self):
        contract = TrackedContractFactory()
        assert contract.event_filter_type == "none"

    def test_default_filter_list_is_empty(self):
        contract = TrackedContractFactory()
        assert contract.event_filter_list == []


# ---------------------------------------------------------------------------
# Ingest pipeline: _upsert_contract_event respects filter
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUpsertContractEventFilter:
    def _make_event(self, event_type: str, ledger: int = 1000, event_index: int = 0):
        event = MagicMock()
        event.type = event_type
        event.event_type = event_type
        event.ledger = ledger
        event.ledger_sequence = ledger
        event.event_index = event_index
        event.tx_hash = "a" * 64
        event.transaction_hash = "a" * 64
        event.value = {"amount": 100}
        event.payload = {"amount": 100}
        event.xdr = ""
        event.raw_xdr = ""
        event.timestamp = None
        event.signature = None
        return event

    def test_whitelist_persists_allowed_event(self):
        contract = TrackedContractFactory(
            event_filter_type="whitelist",
            event_filter_list=["transfer"],
        )
        event = self._make_event("transfer")
        result, created = _upsert_contract_event(contract, event)
        assert result is not None
        assert created is True
        assert ContractEvent.objects.filter(contract=contract, event_type="transfer").exists()

    def test_whitelist_drops_unlisted_event(self):
        contract = TrackedContractFactory(
            event_filter_type="whitelist",
            event_filter_list=["transfer"],
        )
        event = self._make_event("approval")
        result, created = _upsert_contract_event(contract, event)
        assert result is None
        assert created is False
        assert not ContractEvent.objects.filter(contract=contract, event_type="approval").exists()

    def test_blacklist_drops_listed_event(self):
        contract = TrackedContractFactory(
            event_filter_type="blacklist",
            event_filter_list=["approval"],
        )
        event = self._make_event("approval")
        result, created = _upsert_contract_event(contract, event)
        assert result is None
        assert created is False
        assert not ContractEvent.objects.filter(contract=contract, event_type="approval").exists()

    def test_blacklist_persists_unlisted_event(self):
        contract = TrackedContractFactory(
            event_filter_type="blacklist",
            event_filter_list=["approval"],
        )
        event = self._make_event("transfer")
        result, created = _upsert_contract_event(contract, event)
        assert result is not None
        assert created is True
        assert ContractEvent.objects.filter(contract=contract, event_type="transfer").exists()

    def test_no_filter_persists_all_events(self):
        contract = TrackedContractFactory(event_filter_type="none")
        for i, etype in enumerate(["transfer", "approval", "mint"]):
            event = self._make_event(etype, ledger=1000 + i, event_index=i)
            result, created = _upsert_contract_event(contract, event)
            assert result is not None

        assert ContractEvent.objects.filter(contract=contract).count() == 3


# ---------------------------------------------------------------------------
# Prometheus metric incremented on filtered events
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestFilteredMetric:
    def _make_event(self, event_type: str):
        event = MagicMock()
        event.type = event_type
        event.event_type = event_type
        event.ledger = 2000
        event.ledger_sequence = 2000
        event.event_index = 0
        event.tx_hash = "b" * 64
        event.transaction_hash = "b" * 64
        event.value = {}
        event.payload = {}
        event.xdr = ""
        event.raw_xdr = ""
        event.timestamp = None
        event.signature = None
        return event

    def test_metric_incremented_on_whitelist_drop(self):
        from soroscan.ingest import metrics

        contract = TrackedContractFactory(
            event_filter_type="whitelist",
            event_filter_list=["transfer"],
        )
        event = self._make_event("approval")

        before = metrics.events_filtered_total.labels(
            contract_id=contract.contract_id[:8],
            network=_network_label(),
            filter_type="whitelist",
            event_type="approval",
        )._value.get()

        _upsert_contract_event(contract, event)

        after = metrics.events_filtered_total.labels(
            contract_id=contract.contract_id[:8],
            network=_network_label(),
            filter_type="whitelist",
            event_type="approval",
        )._value.get()

        assert after == before + 1

    def test_metric_not_incremented_when_event_passes(self):
        from soroscan.ingest import metrics

        contract = TrackedContractFactory(
            event_filter_type="whitelist",
            event_filter_list=["transfer"],
        )
        event = self._make_event("transfer")

        before = metrics.events_filtered_total.labels(
            contract_id=contract.contract_id[:8],
            network=_network_label(),
            filter_type="whitelist",
            event_type="transfer",
        )._value.get()

        _upsert_contract_event(contract, event)

        after = metrics.events_filtered_total.labels(
            contract_id=contract.contract_id[:8],
            network=_network_label(),
            filter_type="whitelist",
            event_type="transfer",
        )._value.get()

        assert after == before  # no increment


# ---------------------------------------------------------------------------
# Serializer exposes new fields
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTrackedContractSerializerFilterFields:
    def test_serializer_includes_event_filter_type(self):
        contract = TrackedContractFactory(event_filter_type="whitelist", event_filter_list=["transfer"])
        data = TrackedContractSerializer(contract).data
        assert "event_filter_type" in data
        assert data["event_filter_type"] == "whitelist"

    def test_serializer_includes_event_filter_list(self):
        contract = TrackedContractFactory(event_filter_type="blacklist", event_filter_list=["approval"])
        data = TrackedContractSerializer(contract).data
        assert "event_filter_list" in data
        assert data["event_filter_list"] == ["approval"]

    def test_serializer_defaults(self):
        contract = TrackedContractFactory()
        data = TrackedContractSerializer(contract).data
        assert data["event_filter_type"] == "none"
        assert data["event_filter_list"] == []

    def test_serializer_can_write_filter_fields(self):
        user = UserFactory()
        contract = TrackedContractFactory(owner=user)
        request = MagicMock()
        request.user = user
        serializer = TrackedContractSerializer(
            contract,
            data={
                "event_filter_type": "blacklist",
                "event_filter_list": ["approval", "mint"],
                "name": contract.name,
                "contract_id": contract.contract_id,
            },
            context={"request": request},
            partial=True,
        )
        assert serializer.is_valid(), serializer.errors
        updated = serializer.save()
        assert updated.event_filter_type == "blacklist"
        assert updated.event_filter_list == ["approval", "mint"]


# ---------------------------------------------------------------------------
# GraphQL: updateContract mutation sets filter fields
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGraphQLEventFilter:
    def _ctx(self, user):
        ctx = MagicMock()
        req = MagicMock()
        req.user = user
        ctx.request = req
        return ctx

    def test_update_contract_sets_whitelist(self):
        user = UserFactory()
        contract = TrackedContractFactory(owner=user)
        mutation = f"""
            mutation {{
                updateContract(
                    contractId: "{contract.contract_id}",
                    eventFilterType: "whitelist",
                    eventFilterList: ["transfer", "swap"]
                ) {{
                    eventFilterType
                    eventFilterList
                }}
            }}
        """
        result = schema.execute_sync(mutation, context_value=self._ctx(user))
        assert result.errors is None
        assert result.data["updateContract"]["eventFilterType"] == "whitelist"
        assert result.data["updateContract"]["eventFilterList"] == ["transfer", "swap"]

        contract.refresh_from_db()
        assert contract.event_filter_type == "whitelist"
        assert contract.event_filter_list == ["transfer", "swap"]

    def test_update_contract_sets_blacklist(self):
        user = UserFactory()
        contract = TrackedContractFactory(owner=user)
        mutation = f"""
            mutation {{
                updateContract(
                    contractId: "{contract.contract_id}",
                    eventFilterType: "blacklist",
                    eventFilterList: ["approval"]
                ) {{
                    eventFilterType
                    eventFilterList
                }}
            }}
        """
        result = schema.execute_sync(mutation, context_value=self._ctx(user))
        assert result.errors is None
        assert result.data["updateContract"]["eventFilterType"] == "blacklist"

    def test_update_contract_clears_filter(self):
        user = UserFactory()
        contract = TrackedContractFactory(
            owner=user,
            event_filter_type="whitelist",
            event_filter_list=["transfer"],
        )
        mutation = f"""
            mutation {{
                updateContract(
                    contractId: "{contract.contract_id}",
                    eventFilterType: "none",
                    eventFilterList: []
                ) {{
                    eventFilterType
                    eventFilterList
                }}
            }}
        """
        result = schema.execute_sync(mutation, context_value=self._ctx(user))
        assert result.errors is None
        assert result.data["updateContract"]["eventFilterType"] == "none"
        assert result.data["updateContract"]["eventFilterList"] == []

    def test_update_contract_invalid_filter_type_raises(self):
        user = UserFactory()
        contract = TrackedContractFactory(owner=user)
        mutation = f"""
            mutation {{
                updateContract(
                    contractId: "{contract.contract_id}",
                    eventFilterType: "invalid_type"
                ) {{
                    eventFilterType
                }}
            }}
        """
        result = schema.execute_sync(mutation, context_value=self._ctx(user))
        assert result.errors is not None

    def test_contracts_query_returns_filter_fields(self):
        TrackedContractFactory(event_filter_type="whitelist", event_filter_list=["transfer"])
        query = """
            query {
                contracts {
                    contractId
                    eventFilterType
                    eventFilterList
                }
            }
        """
        result = schema.execute_sync(query)
        assert result.errors is None
        contract_data = result.data["contracts"][0]
        assert "eventFilterType" in contract_data
        assert "eventFilterList" in contract_data
