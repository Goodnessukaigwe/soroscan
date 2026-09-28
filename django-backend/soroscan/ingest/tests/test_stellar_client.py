import json
import os

import pytest
from django.core.cache import cache
from stellar_sdk import Keypair, StrKey, scval
from stellar_sdk.xdr import SCVal, SCValType
import stellar_sdk.xdr as stellar_xdr
from unittest.mock import MagicMock, patch

from soroscan.ingest.cache_utils import (
    SIMULATION_CACHE_TTL,
    simulation_cache_key,
)
from soroscan.ingest.stellar_client import (
    SorobanClient,
    _decode_complex_scval,
    _decode_primitive_scval,
)


def _roundtrip(sc_val: SCVal) -> SCVal:
    """Simulate what the RPC response path does: decode from XDR bytes."""
    return SCVal.from_xdr(sc_val.to_xdr())


@pytest.fixture
def valid_keypair():
    """Generate a valid Stellar keypair for testing"""
    return Keypair.random()


@pytest.fixture
def valid_contract_id():
    """Generate a valid Stellar contract address for testing"""
    import os
    return StrKey.encode_contract(os.urandom(32))


@pytest.fixture
def hex_contract_id():
    """Generate a hex-format contract ID for tests (C + 64 hex chars)"""
    import os
    return "C" + os.urandom(32).hex()


@pytest.fixture
def client(valid_keypair, valid_contract_id):
    """Create SorobanClient with valid keypair and StrKey contract address"""
    # The client's contract_id must be StrKey format for the SDK
    # Individual tests will mock SorobanServer as needed
    return SorobanClient(
        rpc_url="https://soroban-testnet.stellar.org",
        network_passphrase="Test SDF Network ; September 2015",
        contract_id=valid_contract_id,
        secret_key=valid_keypair.secret,
    )


class TestSorobanClient:
    def test_client_initialization(self, client):
        assert client.rpc_url == "https://soroban-testnet.stellar.org"
        assert client.network_passphrase == "Test SDF Network ; September 2015"
        assert client.contract_id.startswith("C")
        assert client.keypair is not None

    def test_client_initialization_no_secret(self):
        client = SorobanClient(secret_key=None)
        assert client.keypair is None

    def test_address_to_sc_val_account(self, client):
        address = "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF"
        sc_val = client._address_to_sc_val(address)
        assert sc_val is not None

    def test_address_to_sc_val_contract(self, client):
        # Use the hex format the implementation expects (not StrKey format)
        address = "C" + "a" * 64  # Valid hex contract ID
        sc_val = client._address_to_sc_val(address)
        assert sc_val is not None

    def test_address_to_sc_val_invalid(self, client):
        with pytest.raises(ValueError):
            client._address_to_sc_val("INVALID")

    def test_symbol_to_sc_val(self, client):
        sc_val = client._symbol_to_sc_val("test_symbol")
        assert sc_val is not None

    def test_bytes_to_sc_val(self, client):
        data = b"test data"
        sc_val = client._bytes_to_sc_val(data)
        assert sc_val is not None

    @patch("soroscan.ingest.stellar_client.SorobanServer")
    def test_record_event_no_keypair(self, mock_server, hex_contract_id):
        client = SorobanClient(secret_key=None)
        result = client.record_event(
            target_contract_id=hex_contract_id,
            event_type="swap",
            payload_hash_hex="a" * 64,
        )

        assert result.success is False
        assert result.error == "No keypair configured"

    def test_record_event_invalid_hash_length(self, client, hex_contract_id):
        # Mock the server to allow account loading
        mock_account = MagicMock()
        mock_account.sequence = 1
        client.server = MagicMock()
        client.server.load_account.return_value = mock_account
        
        result = client.record_event(
            target_contract_id=hex_contract_id,
            event_type="swap",
            payload_hash_hex="aa",
        )

        assert result.success is False
        assert "32 bytes" in result.error

    def test_record_event_success(self, client, hex_contract_id):
        mock_account = MagicMock()
        mock_account.sequence = 1

        mock_simulate_response = MagicMock()
        mock_simulate_response.error = None

        mock_send_response = MagicMock()
        mock_send_response.status = "PENDING"
        mock_send_response.hash = "tx123"

        # Mock the server instance on the client
        client.server = MagicMock()
        client.server.load_account.return_value = mock_account
        client.server.simulate_transaction.return_value = mock_simulate_response
        client.server.prepare_transaction.return_value = MagicMock()
        client.server.send_transaction.return_value = mock_send_response

        result = client.record_event(
            target_contract_id=hex_contract_id,
            event_type="swap",
            payload_hash_hex="a" * 64,
        )

        assert result.success is True
        assert result.tx_hash == "tx123"
        assert result.status == "PENDING"

    def test_record_event_simulation_failed(self, client, hex_contract_id):
        mock_account = MagicMock()
        mock_account.sequence = 1

        mock_simulate_response = MagicMock()
        mock_simulate_response.error = "Simulation error"

        # Mock the server instance on the client
        client.server = MagicMock()
        client.server.load_account.return_value = mock_account
        client.server.simulate_transaction.return_value = mock_simulate_response

        result = client.record_event(
            target_contract_id=hex_contract_id,
            event_type="swap",
            payload_hash_hex="a" * 64,
        )

        assert result.success is False
        assert result.status == "simulation_failed"
        assert result.error == "Simulation error"

    def test_record_event_exception(self, client, hex_contract_id):
        # Mock the server instance on the client
        client.server = MagicMock()
        client.server.load_account.side_effect = Exception("Network error")

        result = client.record_event(
            target_contract_id=hex_contract_id,
            event_type="swap",
            payload_hash_hex="a" * 64,
        )

        assert result.success is False
        assert result.status == "error"
        assert "Network error" in result.error

    def test_get_total_events(self, client):
        mock_account = MagicMock()
        mock_account.sequence = 1

        # Mock the server instance on the client
        client.server = MagicMock()
        client.server.load_account.return_value = mock_account

        result = client.get_total_events()

        assert result is None

    def test_add_indexer_no_admin_keypair(self, hex_contract_id, valid_keypair):
        client = SorobanClient(
            rpc_url="https://soroban-testnet.stellar.org",
            contract_id=hex_contract_id,
            secret_key="",
        )
        result = client.add_indexer(valid_keypair.public_key)
        assert result.success is False
        assert result.error == "No admin keypair configured"

    def test_add_indexer_success(self, client, hex_contract_id, valid_keypair):
        mock_account = MagicMock()
        mock_account.sequence = 1
        client.server = MagicMock()
        client.server.load_account.return_value = mock_account

        mock_simulate_response = MagicMock()
        mock_simulate_response.error = None
        client.server.simulate_transaction.return_value = mock_simulate_response
        client.server.prepare_transaction.return_value = MagicMock()
        client.server.send_transaction.return_value = MagicMock(
            status="PENDING", hash="addindexer123"
        )

        result = client.add_indexer(valid_keypair.public_key)
        assert result.success is True
        assert result.tx_hash == "addindexer123"


class TestPrimitiveScvalDecoding:
    """_decode_primitive_scval must cover the RPC primitive result types (issue #1400)."""

    def test_decodes_u64(self):
        assert _decode_primitive_scval(_roundtrip(scval.to_uint64(42))) == 42

    def test_decodes_i64(self):
        assert _decode_primitive_scval(_roundtrip(scval.to_int64(-7))) == -7

    def test_decodes_symbol(self):
        assert _decode_primitive_scval(_roundtrip(scval.to_symbol("swap"))) == "swap"

    def test_decodes_bool(self):
        assert _decode_primitive_scval(_roundtrip(scval.to_bool(True))) is True
        assert _decode_primitive_scval(_roundtrip(scval.to_bool(False))) is False

    def test_decodes_void_as_none(self):
        assert _decode_primitive_scval(_roundtrip(scval.to_void())) is None


class TestComplexScvalDecoding:
    """_decode_complex_scval must decode nested XDR into JSON-safe data (issue #1401)."""

    @staticmethod
    def _nested_sample() -> SCVal:
        return scval.to_map(
            {
                scval.to_symbol("inner"): scval.to_vec(
                    [
                        scval.to_map({scval.to_symbol("x"): scval.to_int64(-1)}),
                        scval.to_uint64(7),
                    ]
                ),
                scval.to_symbol("flag"): scval.to_bool(True),
            }
        )

    def test_nested_map_and_vec_roundtrip(self):
        decoded = _decode_complex_scval(_roundtrip(self._nested_sample()))
        assert decoded == {"inner": [{"x": -1}, 7], "flag": True}

    def test_nested_result_is_json_serializable(self):
        decoded = _decode_complex_scval(_roundtrip(self._nested_sample()))
        assert json.loads(json.dumps(decoded)) == decoded

    def test_account_address_formatted_as_g_strkey(self):
        keypair = Keypair.random()
        decoded = _decode_complex_scval(
            _roundtrip(scval.to_address(keypair.public_key))
        )
        assert decoded == keypair.public_key
        assert decoded.startswith("G")

    def test_contract_address_formatted_as_c_strkey(self):
        contract_id = StrKey.encode_contract(os.urandom(32))
        decoded = _decode_complex_scval(_roundtrip(scval.to_address(contract_id)))
        assert decoded == contract_id
        assert decoded.startswith("C")

    def test_contract_instance_decodes_executable_and_storage(self):
        owner = Keypair.random().public_key
        executable = stellar_xdr.ContractExecutable(
            type=stellar_xdr.ContractExecutableType.CONTRACT_EXECUTABLE_WASM,
            wasm_hash=stellar_xdr.Hash(os.urandom(32)),
        )
        instance = stellar_xdr.SCContractInstance(
            executable=executable,
            storage=stellar_xdr.SCMap(
                [
                    stellar_xdr.SCMapEntry(
                        key=scval.to_symbol("owner"),
                        val=scval.to_address(owner),
                    )
                ]
            ),
        )
        sc_val = SCVal(
            type=SCValType.SCV_CONTRACT_INSTANCE,
            instance=instance,
        )

        decoded = _decode_complex_scval(_roundtrip(sc_val))
        assert decoded["type"] == "contract_instance"
        assert decoded["executable"]["type"] == "wasm"
        assert decoded["executable"]["wasm_hash"] == bytes(
            executable.wasm_hash.hash
        ).hex()
        assert decoded["storage"]["owner"] == owner
        # Deterministic decode — same XDR always yields the same structure
        assert decoded == _decode_complex_scval(_roundtrip(sc_val))


class TestSimulationCaching:
    """Redis-cached Soroban RPC simulations with a 60s TTL (issue #1402)."""

    def _mock_rpc_result(self, client, result_sc_val: SCVal) -> MagicMock:
        mock_account = MagicMock()
        mock_account.sequence = 1
        client.server = MagicMock()
        client.server.load_account.return_value = mock_account

        response = MagicMock()
        response.error = None
        response.results = [MagicMock(xdr=result_sc_val.to_xdr())]
        client.server.simulate_transaction.return_value = response
        return response

    def test_get_total_events_returns_decoded_int(self, client):
        cache.clear()
        self._mock_rpc_result(client, scval.to_uint64(1234))

        result = client.get_total_events()

        assert result == 1234
        assert isinstance(result, int)
        cache.clear()

    def test_get_total_events_returns_none_on_simulation_error(self, client):
        cache.clear()
        client.server = MagicMock()
        client.server.load_account.return_value = MagicMock(sequence=1)
        response = MagicMock()
        response.error = "boom"
        client.server.simulate_transaction.return_value = response

        assert client.get_total_events() is None
        cache.clear()

    def test_cache_hit_avoids_second_rpc_call(self, client):
        cache.clear()
        self._mock_rpc_result(client, scval.to_bool(True))

        first = client.get_admin()
        second = client.get_admin()

        assert first == (True, True)
        assert second == (True, True)
        # Only the first call may reach Horizon/RPC
        assert client.server.simulate_transaction.call_count == 1
        assert client.server.load_account.call_count == 1
        cache.clear()

    def test_simulation_errors_are_not_cached(self, client):
        cache.clear()
        client.server = MagicMock()
        client.server.load_account.return_value = MagicMock(sequence=1)
        response = MagicMock()
        response.error = "boom"
        client.server.simulate_transaction.return_value = response

        first = client.get_admin()
        second = client.get_admin()

        assert first == (False, "boom")
        assert second == (False, "boom")
        # Failures must not be memoized for the TTL window
        assert client.server.simulate_transaction.call_count == 2
        cache.clear()

    def test_get_total_events_without_keypair_returns_none(self):
        client = SorobanClient(secret_key=None)
        assert client.get_total_events() is None

    def test_simulation_cache_key_is_deterministic(self):
        key = simulation_cache_key("CAAA", "get_admin", [])
        assert key == simulation_cache_key("CAAA", "get_admin", [])
        assert key != simulation_cache_key("CAAA", "get_admin", ["other"])
        assert key != simulation_cache_key("CBBB", "get_admin", [])
        assert key.startswith("soroscan:simulation:")
        assert SIMULATION_CACHE_TTL == 60
