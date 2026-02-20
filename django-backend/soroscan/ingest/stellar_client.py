"""
Stellar/Soroban client for interacting with the SoroScan contract.
"""
import logging
from dataclasses import dataclass
from typing import Any, Optional

from django.conf import settings
from stellar_sdk import Keypair, Network, TransactionBuilder
from stellar_sdk.soroban_server import SorobanServer
from stellar_sdk.xdr import (
    SCVal,
    SCValType,
    SCSymbol,
    SCBytes,
    SCAddress,
    SCAddressType,
    Hash,
)

logger = logging.getLogger(__name__)


@dataclass
class TransactionResult:
    """Result of a Soroban transaction."""

    success: bool
    tx_hash: str
    status: str
    error: Optional[str] = None
    result_xdr: Optional[str] = None


class SorobanClient:
    """
    Client for interacting with Soroban smart contracts.
    """

    def __init__(
        self,
        rpc_url: Optional[str] = None,
        network_passphrase: Optional[str] = None,
        contract_id: Optional[str] = None,
        secret_key: Optional[str] = None,
    ):
        self.rpc_url = rpc_url or settings.SOROBAN_RPC_URL
        self.network_passphrase = network_passphrase or settings.STELLAR_NETWORK_PASSPHRASE
        self.contract_id = contract_id or settings.SOROSCAN_CONTRACT_ID
        self.secret_key = secret_key or settings.INDEXER_SECRET_KEY

        self.server = SorobanServer(self.rpc_url)
        self.keypair = Keypair.from_secret(self.secret_key) if self.secret_key else None

    def _address_to_sc_val(self, address: str) -> SCVal:
        """Convert a Stellar address string to SCVal."""
        if address.startswith("G"):
            # Account address
            keypair = Keypair.from_public_key(address)
            sc_address = SCAddress(
                type=SCAddressType.SC_ADDRESS_TYPE_ACCOUNT,
                account_id=keypair.xdr_account_id(),
            )
        elif address.startswith("C"):
            # Contract address
            contract_hash = Hash(bytes.fromhex(address[1:]))  # Strip 'C' prefix
            sc_address = SCAddress(
                type=SCAddressType.SC_ADDRESS_TYPE_CONTRACT,
                contract_id=contract_hash,
            )
        else:
            raise ValueError(f"Invalid address format: {address}")

        return SCVal(type=SCValType.SCV_ADDRESS, address=sc_address)

    def _symbol_to_sc_val(self, symbol: str) -> SCVal:
        """Convert a string to SCVal symbol."""
        return SCVal(
            type=SCValType.SCV_SYMBOL,
            sym=SCSymbol(symbol.encode("utf-8")),
        )

    def _bytes_to_sc_val(self, data: bytes) -> SCVal:
        """Convert bytes to SCVal."""
        return SCVal(
            type=SCValType.SCV_BYTES,
            bytes=SCBytes(data),
        )

    def record_event(
        self,
        target_contract_id: str,
        event_type: str,
        payload_hash_hex: str,
    ) -> TransactionResult:
        """
        Submit a record_event transaction to the SoroScan contract.

        Args:
            target_contract_id: The contract that emitted the original event
            event_type: The type/category of the event
            payload_hash_hex: SHA-256 hash of the payload (hex string)

        Returns:
            TransactionResult with status and hash
        """
        if not self.keypair:
            return TransactionResult(
                success=False,
                tx_hash="",
                status="error",
                error="No keypair configured",
            )

        try:
            # Get account info
            account = self.server.load_account(self.keypair.public_key)

            # Build parameters
            payload_hash_bytes = bytes.fromhex(payload_hash_hex)
            if len(payload_hash_bytes) != 32:
                raise ValueError("Payload hash must be 32 bytes")

            # Build the transaction
            tx_builder = TransactionBuilder(
                source_account=account,
                network_passphrase=self.network_passphrase,
                base_fee=100000,  # 0.01 XLM
            )

            tx_builder.append_invoke_contract_function_op(
                contract_id=self.contract_id,
                function_name="record_event",
                parameters=[
                    self._address_to_sc_val(self.keypair.public_key),  # indexer
                    self._address_to_sc_val(target_contract_id),  # contract_id
                    self._symbol_to_sc_val(event_type),  # event_type
                    self._bytes_to_sc_val(payload_hash_bytes),  # payload_hash
                ],
            )

            tx = tx_builder.set_timeout(30).build()

            # Simulate and prepare
            simulate_response = self.server.simulate_transaction(tx)

            if simulate_response.error:
                return TransactionResult(
                    success=False,
                    tx_hash="",
                    status="simulation_failed",
                    error=simulate_response.error,
                )

            # Prepare transaction with resource fees
            prepared_tx = self.server.prepare_transaction(tx, simulate_response)
            prepared_tx.sign(self.keypair)

            # Submit
            send_response = self.server.send_transaction(prepared_tx)

            logger.info(
                "Transaction submitted: %s",
                send_response.hash,
                extra={"contract_id": target_contract_id},
            )

            return TransactionResult(
                success=send_response.status == "PENDING",
                tx_hash=send_response.hash,
                status=send_response.status,
                result_xdr=getattr(send_response, "result_xdr", None),
            )

        except Exception as e:
            logger.exception(
                "Failed to record event",
                extra={"contract_id": target_contract_id},
            )
            return TransactionResult(
                success=False,
                tx_hash="",
                status="error",
                error=str(e),
            )

    def get_total_events(self) -> Optional[int]:
        """
        Query the total_events function on the contract.

        Returns:
            Total event count or None on error
        """
        try:
            # This is a read-only call, so we simulate without submitting
            account = self.server.load_account(self.keypair.public_key)

            tx_builder = TransactionBuilder(
                source_account=account,
                network_passphrase=self.network_passphrase,
                base_fee=100,
            )

            tx_builder.append_invoke_contract_function_op(
                contract_id=self.contract_id,
                function_name="total_events",
                parameters=[],
            )

            tx = tx_builder.set_timeout(30).build()
            simulate_response = self.server.simulate_transaction(tx)

            if simulate_response.results:
                # Parse the u64 result
                result_xdr = simulate_response.results[0].xdr
                # Decode and return the value
                # This is simplified - actual implementation needs XDR parsing
                return None  # TODO: Parse XDR result

            return None

        except Exception as e:
            logger.exception("Failed to get total events")
            return None

    def get_events_range(
        self,
        contract_id: str,
        start_ledger: int,
        end_ledger: int,
    ) -> list[Any]:
        """
        Fetch contract events in an inclusive ledger range.

        The caller is responsible for pagination strategy; this method fetches the
        requested range and returns raw SDK event objects.
        """
        if start_ledger > end_ledger:
            return []

        filters = [
            {
                "type": "contract",
                "contractIds": [contract_id],
            }
        ]
        pagination = {"limit": 200}

        try:
            response = self.server.get_events(
                start_ledger=start_ledger,
                end_ledger=end_ledger,
                filters=filters,
                pagination=pagination,
            )
        except TypeError:
            # Some SDK variants do not support end_ledger.
            response = self.server.get_events(
                start_ledger=start_ledger,
                filters=filters,
                pagination=pagination,
            )

        events = list(getattr(response, "events", []) or [])
        return [
            event
            for event in events
            if start_ledger <= int(getattr(event, "ledger", start_ledger)) <= end_ledger
        ]
