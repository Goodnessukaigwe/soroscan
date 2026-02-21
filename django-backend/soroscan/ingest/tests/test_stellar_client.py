import pytest
import responses
from stellar_sdk import Keypair, StrKey
from unittest.mock import MagicMock, patch

from soroscan.ingest.stellar_client import SorobanClient, TransactionResult


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
