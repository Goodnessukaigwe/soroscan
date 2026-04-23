import pytest
from django.utils import timezone
from datetime import timedelta
from soroscan.ingest.tasks import _upsert_contract_event
from .factories import TrackedContractFactory

@pytest.mark.django_db
class TestLastEventAtTracking:
    def test_last_event_at_updates_on_new_event(self):
        contract = TrackedContractFactory()
        assert contract.last_event_at is None

        now = timezone.now()
        event_data = {
            "ledger": 1000,
            "event_index": 0,
            "tx_hash": "hash1",
            "event_type": "swap",
            "payload": {"amount": 100},
            "timestamp": now,
            "raw_xdr": "xdr1",
        }

        _upsert_contract_event(contract, event_data)
        
        contract.refresh_from_db()
        assert contract.last_event_at == pytest.approx(now, abs=timedelta(milliseconds=10))

    def test_last_event_at_only_updates_if_newer(self):
        now = timezone.now()
        past = now - timedelta(hours=1)
        future = now + timedelta(hours=1)
        
        contract = TrackedContractFactory(last_event_at=now)
        
        # Older event
        _upsert_contract_event(contract, {"timestamp": past, "ledger": 900, "event_index": 0})
        contract.refresh_from_db()
        assert contract.last_event_at == now

        # Newer event
        _upsert_contract_event(contract, {"timestamp": future, "ledger": 1100, "event_index": 0})
        contract.refresh_from_db()
        assert contract.last_event_at == future

    def test_last_event_at_handles_none(self):
        contract = TrackedContractFactory(last_event_at=None)
        now = timezone.now()
        
        _upsert_contract_event(contract, {"timestamp": now, "ledger": 1000, "event_index": 0})
        contract.refresh_from_db()
        assert contract.last_event_at == now
