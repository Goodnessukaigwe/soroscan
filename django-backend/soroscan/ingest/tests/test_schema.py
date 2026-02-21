import pytest
from django.utils import timezone

from soroscan.ingest.schema import schema
from .factories import ContractEventFactory, TrackedContractFactory, UserFactory


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def contract(user):
    return TrackedContractFactory(owner=user)


@pytest.mark.django_db
class TestGraphQLQueries:
    def test_query_contracts(self, contract):
        query = """
            query {
                contracts {
                    id
                    contractId
                    name
                }
            }
        """
        result = schema.execute_sync(query)
        assert result.errors is None
        assert len(result.data["contracts"]) == 1
        assert result.data["contracts"][0]["contractId"] == contract.contract_id

    def test_query_contracts_filter_active(self, contract):
        TrackedContractFactory(owner=contract.owner, is_active=False)
        
        query = """
            query {
                contracts(isActive: true) {
                    id
                    isActive
                }
            }
        """
        result = schema.execute_sync(query)
        assert result.errors is None
        assert len(result.data["contracts"]) == 1
        assert result.data["contracts"][0]["isActive"] is True

    def test_query_contract_by_id(self, contract):
        query = f"""
            query {{
                contract(contractId: "{contract.contract_id}") {{
                    id
                    contractId
                    name
                }}
            }}
        """
        result = schema.execute_sync(query)
        assert result.errors is None
        assert result.data["contract"]["contractId"] == contract.contract_id

    def test_query_contract_not_found(self):
        query = """
            query {
                contract(contractId: "NONEXISTENT") {
                    id
                }
            }
        """
        result = schema.execute_sync(query)
        assert result.errors is None
        assert result.data["contract"] is None

    def test_query_events(self, contract):
        ContractEventFactory(contract=contract)
        ContractEventFactory(contract=contract)
        
        query = """
            query {
                events(limit: 10) {
                    id
                    eventType
                }
            }
        """
        result = schema.execute_sync(query)
        assert result.errors is None
        assert len(result.data["events"]) == 2

    def test_query_events_filter_by_contract(self, contract):
        other_contract = TrackedContractFactory(owner=contract.owner)
        ContractEventFactory(contract=contract)
        ContractEventFactory(contract=other_contract)
        
        query = f"""
            query {{
                events(contractId: "{contract.contract_id}") {{
                    id
                    contractId
                }}
            }}
        """
        result = schema.execute_sync(query)
        assert result.errors is None
        assert len(result.data["events"]) == 1
        assert result.data["events"][0]["contractId"] == contract.contract_id

    def test_query_events_filter_by_type(self, contract):
        ContractEventFactory(contract=contract, event_type="transfer")
        ContractEventFactory(contract=contract, event_type="mint")
        
        query = """
            query {
                events(eventType: "transfer") {
                    id
                    eventType
                }
            }
        """
        result = schema.execute_sync(query)
        assert result.errors is None
        assert len(result.data["events"]) == 1
        assert result.data["events"][0]["eventType"] == "transfer"

    def test_query_events_pagination(self, contract):
        for _ in range(5):
            ContractEventFactory(contract=contract)
        
        query = """
            query {
                events(limit: 2, offset: 2) {
                    id
                }
            }
        """
        result = schema.execute_sync(query)
        assert result.errors is None
        assert len(result.data["events"]) == 2

    def test_query_events_limit_enforced(self, contract):
        for _ in range(10):
            ContractEventFactory(contract=contract)
        
        query = """
            query {
                events(limit: 5000) {
                    id
                }
            }
        """
        result = schema.execute_sync(query)
        assert result.errors is None
        # Should be capped at 1000 per the schema
        assert len(result.data["events"]) <= 1000

    def test_query_events_time_range(self, contract):
        old_event = ContractEventFactory(
            contract=contract,
            timestamp=timezone.now() - timezone.timedelta(days=2)
        )
        new_event = ContractEventFactory(
            contract=contract,
            timestamp=timezone.now()
        )
        
        since = (timezone.now() - timezone.timedelta(days=1)).isoformat()
        query = f"""
            query {{
                events(since: "{since}") {{
                    id
                }}
            }}
        """
        result = schema.execute_sync(query)
        assert result.errors is None
        assert len(result.data["events"]) == 1

    def test_query_event_by_id(self, contract):
        event = ContractEventFactory(contract=contract)
        
        query = f"""
            query {{
                event(id: {event.id}) {{
                    id
                    eventType
                }}
            }}
        """
        result = schema.execute_sync(query)
        assert result.errors is None
        assert result.data["event"]["id"] == str(event.id)

    def test_query_contract_stats(self, contract):
        ContractEventFactory(contract=contract, event_type="transfer")
        ContractEventFactory(contract=contract, event_type="mint")
        ContractEventFactory(contract=contract, event_type="transfer")
        
        query = f"""
            query {{
                contractStats(contractId: "{contract.contract_id}") {{
                    totalEvents
                    uniqueEventTypes
                }}
            }}
        """
        result = schema.execute_sync(query)
        assert result.errors is None
        assert result.data["contractStats"]["totalEvents"] == 3
        assert result.data["contractStats"]["uniqueEventTypes"] == 2

    def test_query_event_types(self, contract):
        ContractEventFactory(contract=contract, event_type="transfer")
        ContractEventFactory(contract=contract, event_type="mint")
        ContractEventFactory(contract=contract, event_type="transfer")
        
        query = f"""
            query {{
                eventTypes(contractId: "{contract.contract_id}")
            }}
        """
        result = schema.execute_sync(query)
        assert result.errors is None
        assert set(result.data["eventTypes"]) == {"transfer", "mint"}


@pytest.mark.django_db
class TestGraphQLMutations:
    def test_register_contract(self, user):
        mutation = """
            mutation {
                registerContract(
                    contractId: "CTEST123",
                    name: "Test Contract",
                    description: "A test"
                ) {
                    contractId
                    name
                }
            }
        """
        result = schema.execute_sync(mutation)
        assert result.errors is None
        assert result.data["registerContract"]["contractId"] == "CTEST123"

    def test_update_contract(self, contract):
        mutation = f"""
            mutation {{
                updateContract(
                    contractId: "{contract.contract_id}",
                    name: "Updated Name",
                    isActive: false
                ) {{
                    contractId
                    name
                    isActive
                }}
            }}
        """
        result = schema.execute_sync(mutation)
        assert result.errors is None
        assert result.data["updateContract"]["name"] == "Updated Name"
        assert result.data["updateContract"]["isActive"] is False

    def test_update_nonexistent_contract(self):
        mutation = """
            mutation {
                updateContract(
                    contractId: "NONEXISTENT",
                    name: "Updated"
                ) {
                    contractId
                }
            }
        """
        result = schema.execute_sync(mutation)
        assert result.errors is None
        assert result.data["updateContract"] is None
