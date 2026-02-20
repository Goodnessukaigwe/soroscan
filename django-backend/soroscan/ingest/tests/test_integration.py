from dataclasses import dataclass

import pytest
from django.contrib.auth import get_user_model

from soroscan.ingest.models import ContractEvent, TrackedContract
from soroscan.ingest.tasks import BATCH_LEDGER_SIZE, backfill_contract_events

User = get_user_model()


@dataclass
class MockEvent:
    contract_id: str
    ledger: int
    event_index: int
    tx_hash: str
    type: str
    value: dict
    xdr: str = ""


@pytest.mark.django_db
def test_backfill_contract_events_1000_ledger_range(mocker):
    user = User.objects.create_user(username="integration-user", password="secret")
    contract = TrackedContract.objects.create(
        contract_id="C" + ("a" * 55),
        name="Backfill Contract",
        owner=user,
        is_active=True,
    )

    def build_events_for_window(start_ledger: int, end_ledger: int) -> list[MockEvent]:
        return [
            MockEvent(
                contract_id=contract.contract_id,
                ledger=ledger,
                event_index=0,
                tx_hash=f"tx-{ledger}",
                type="transfer",
                value={"amount": ledger},
            )
            for ledger in range(start_ledger, end_ledger + 1)
        ]

    client_mock = mocker.Mock()
    client_mock.get_events_range.side_effect = [
        build_events_for_window(1, 200),
        build_events_for_window(201, 400),
        build_events_for_window(401, 600),
        build_events_for_window(601, 800),
        build_events_for_window(801, 1000),
    ]
    mocker.patch("soroscan.ingest.tasks.SorobanClient", return_value=client_mock)

    result = backfill_contract_events(contract.contract_id, 1, 1000)

    assert result["from_ledger"] == 1
    assert result["to_ledger"] == 1000
    assert result["created_events"] == 1000
    assert result["updated_events"] == 0
    assert result["processed_events"] == 1000
    assert ContractEvent.objects.filter(contract=contract).count() == 1000

    contract.refresh_from_db()
    assert contract.last_indexed_ledger == 1000

    # 1000 ledgers with a 200-ledger window must request exactly 5 batches.
    assert client_mock.get_events_range.call_count == 1000 // BATCH_LEDGER_SIZE

    # Re-run for the same range to verify idempotency and resume checkpoint behavior.
    client_mock.get_events_range.reset_mock()
    second_run = backfill_contract_events(contract.contract_id, 1, 1000)

    assert second_run["created_events"] == 0
    assert second_run["updated_events"] == 0
    assert second_run["processed_events"] == 0
    assert ContractEvent.objects.filter(contract=contract).count() == 1000
    assert client_mock.get_events_range.call_count == 0
