"""Tests for contract event schema validation (issue #1310)."""
import pytest

from soroscan.ingest.event_schemas import (
    CONTRACT_EVENT_SCHEMAS,
    SC20_TRANSFER_SCHEMA,
    get_schema_for_event,
    validate_against_standard_schema,
)
from soroscan.ingest.tasks import validate_event_payload, validate_contract_payload_schema
from .factories import EventSchemaFactory, TrackedContractFactory, ContractEventFactory


@pytest.fixture
def contract():
    return TrackedContractFactory()


# ---------------------------------------------------------------------------
# Pre-defined schema registry
# ---------------------------------------------------------------------------


class TestContractEventSchemas:
    def test_all_schemas_are_valid_json_schema(self):
        """Every registered schema must be a valid JSON Schema object."""

        for key, schema in CONTRACT_EVENT_SCHEMAS.items():
            assert schema["type"] == "object", f"Schema {key} must be type: object"
            assert "properties" in schema, f"Schema {key} missing properties"
            assert "required" in schema, f"Schema {key} missing required"

    def test_transfer_schema_requires_fields(self):
        payload = {"from": "GABC", "to": "GDEF", "amount": "1000"}
        valid, err = validate_against_standard_schema(payload, "sc_20", "transfer")
        assert valid is True
        assert err is None

    def test_transfer_schema_rejects_missing_fields(self):
        payload = {"from": "GABC"}
        valid, err = validate_against_standard_schema(payload, "sc_20", "transfer")
        assert valid is False
        assert "to" in err

    def test_transfer_schema_rejects_extra_fields(self):
        payload = {
            "from": "GABC",
            "to": "GDEF",
            "amount": "1000",
            "extra_field": "bad",
        }
        valid, err = validate_against_standard_schema(payload, "sc_20", "transfer")
        assert valid is False
        assert "Additional properties" in err or "additional" in err.lower()

    def test_nft_transfer_schema(self):
        payload = {"from": "GABC", "to": "GDEF", "token_id": "42"}
        valid, _ = validate_against_standard_schema(payload, "sc_21", "transfer")
        assert valid is True

    def test_swap_schema(self):
        payload = {
            "from": "GABC",
            "token_in": "CAAA",
            "token_out": "CBBB",
            "amount_in": "500",
            "amount_out": "480",
        }
        valid, _ = validate_against_standard_schema(payload, "sc_31", "swap")
        assert valid is True

    def test_faucet_schema(self):
        payload = {"to": "GABC", "amount": "10000", "token": "CCCC"}
        valid, _ = validate_against_standard_schema(payload, "sc_36", "mint_test_tokens")
        assert valid is True

    def test_indexer_schema(self):
        payload = {
            "indexer": "GABC",
            "contract_id": "CDEF...",
            "event_type": "transfer",
            "payload": {"amount": 100},
            "schema_version": 1,
        }
        valid, _ = validate_against_standard_schema(payload, "sc_38", "record_event")
        assert valid is True

    def test_unknown_standard_passes(self):
        payload = {"anything": "goes"}
        valid, _ = validate_against_standard_schema(payload, "unknown_standard", "any_event")
        assert valid is True

    def test_get_schema_for_event_returns_schema(self):
        schema = get_schema_for_event("sc_20", "transfer")
        assert schema is not None
        assert schema is SC20_TRANSFER_SCHEMA

    def test_get_schema_for_event_returns_none_for_unknown(self):
        schema = get_schema_for_event("sc_99", "nonexistent")
        assert schema is None


# ---------------------------------------------------------------------------
# EventSchema model-level validation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestValidateEventPayload:
    def test_passes_with_valid_payload(self, contract):
        EventSchemaFactory(
            contract=contract,
            event_type="transfer",
            json_schema=SC20_TRANSFER_SCHEMA,
        )
        payload = {"from": "GABC", "to": "GDEF", "amount": "1000"}
        passed, version = validate_event_payload(contract, "transfer", payload, ledger=100)
        assert passed is True
        assert version == 1

    def test_fails_with_invalid_payload(self, contract):
        EventSchemaFactory(
            contract=contract,
            event_type="transfer",
            json_schema=SC20_TRANSFER_SCHEMA,
        )
        payload = {"wrong_field": "value"}
        passed, version = validate_event_payload(contract, "transfer", payload, ledger=100)
        assert passed is False
        assert version == 1

    def test_passes_when_no_schema_exists(self, contract):
        passed, version = validate_event_payload(contract, "transfer", {"any": "data"})
        assert passed is True
        assert version is None

    def test_passes_with_none_payload(self, contract):
        EventSchemaFactory(contract=contract, event_type="transfer")
        passed, _ = validate_event_payload(contract, "transfer", None)
        assert passed is True

    def test_passes_with_non_dict_payload(self, contract):
        EventSchemaFactory(contract=contract, event_type="transfer")
        passed, _ = validate_event_payload(contract, "transfer", "not a dict")
        assert passed is True

    def test_uses_latest_schema_version(self, contract):
        EventSchemaFactory(
            contract=contract,
            event_type="swap",
            version=1,
            json_schema={
                "type": "object",
                "properties": {"amount": {"type": "number"}},
                "required": ["amount"],
            },
        )
        EventSchemaFactory(
            contract=contract,
            event_type="swap",
            version=2,
            json_schema={
                "type": "object",
                "properties": {"amount": {"type": "number"}, "token": {"type": "string"}},
                "required": ["amount", "token"],
            },
        )
        # Old schema would pass, new schema requires 'token'
        passed, version = validate_event_payload(
            contract, "swap", {"amount": 100}, ledger=200
        )
        assert passed is False
        assert version == 2


# ---------------------------------------------------------------------------
# Contract-level schema validation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestValidateContractPayloadSchema:
    def test_passes_when_no_schema(self, contract):
        result = validate_contract_payload_schema(contract, {"any": "data"}, "transfer")
        assert result is True

    def test_passes_valid_payload(self, contract):
        contract.json_schema = {
            "type": "object",
            "properties": {"amount": {"type": "number"}},
            "required": ["amount"],
        }
        contract.save(update_fields=["json_schema"])
        result = validate_contract_payload_schema(contract, {"amount": 100}, "transfer")
        assert result is True

    def test_fails_invalid_payload(self, contract):
        contract.json_schema = {
            "type": "object",
            "properties": {"amount": {"type": "number"}},
            "required": ["amount"],
        }
        contract.save(update_fields=["json_schema"])
        result = validate_contract_payload_schema(
            contract, {"wrong": "field"}, "transfer", ledger=500
        )
        assert result is False

    def test_passes_empty_schema(self, contract):
        contract.json_schema = {}
        contract.save(update_fields=["json_schema"])
        result = validate_contract_payload_schema(contract, {"any": "data"}, "transfer")
        assert result is True


# ---------------------------------------------------------------------------
# Ingestion flow validation integration
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestIngestionSchemaValidation:
    """Tests that the ingestion flow properly validates and logs invalid events."""

    def test_invalid_event_recorded_as_ingest_error(self, contract):
        from soroscan.ingest.models import IngestError

        contract.json_schema = {
            "type": "object",
            "properties": {"amount": {"type": "number"}},
            "required": ["amount"],
        }
        contract.save(update_fields=["json_schema"])

        result = validate_contract_payload_schema(
            contract, {"invalid": "payload"}, "transfer", ledger=999
        )

        assert result is False

        # Verify the IngestError model can track this kind of failure
        IngestError.objects.create(
            error_type=IngestError.ErrorType.VALIDATION_ERROR,
            contract_id=contract.contract_id,
            error_message="Schema validation failed for event_type=transfer ledger=999",
            ledger=999,
        )
        assert IngestError.objects.filter(
            contract_id=contract.contract_id,
            error_type=IngestError.ErrorType.VALIDATION_ERROR,
        ).exists()

    def test_valid_event_does_not_record_error(self, contract):
        from soroscan.ingest.models import IngestError

        contract.json_schema = {
            "type": "object",
            "properties": {"amount": {"type": "number"}},
            "required": ["amount"],
        }
        contract.save(update_fields=["json_schema"])

        result = validate_contract_payload_schema(
            contract, {"amount": 100}, "transfer"
        )

        assert result is True
        assert not IngestError.objects.filter(
            contract_id=contract.contract_id,
            error_type=IngestError.ErrorType.VALIDATION_ERROR,
        ).exists()

    def test_event_created_with_validation_status(self, contract):
        event = ContractEventFactory(
            contract=contract,
            validation_status="passed",
            schema_version=None,
        )
        assert event.validation_status == "passed"

    def test_event_created_with_failed_validation(self, contract):
        event = ContractEventFactory(
            contract=contract,
            validation_status="failed",
            schema_version=1,
        )
        assert event.validation_status == "failed"
        assert event.schema_version == 1
