"""
Stellar/Soroban client for interacting with the SoroScan contract.
"""
import logging
import time
import requests  # noqa: F401
from dataclasses import dataclass
from threading import Lock
from typing import Any, Optional

from django.conf import settings
from stellar_sdk import Keypair, TransactionBuilder, scval
from stellar_sdk.soroban_server import SorobanServer

from soroscan.circuit_breaker import execute_with_circuit_breaker
from soroscan.ingest.telemetry import tracer
from stellar_sdk.xdr import (
    SCVal,
    SCValType,
    SCSymbol,
    SCBytes,
    SCAddress,
    SCAddressType,
    Hash,
    ContractExecutableType,
)
import stellar_sdk.xdr as stellar_xdr

from .cache_utils import get_cached_simulation_result

logger = logging.getLogger(__name__)


class _SimulationError(Exception):
    """Soroban RPC simulation failed; used to keep failures out of the cache."""


def _decode_primitive_scval(sc_val: SCVal) -> Any:
    """
    Decode a primitive SCVal to a native Python type.

    Supports: U64, I64, U32, I32, SYMBOL, BOOL, STRING, BYTES, ADDRESS, VOID

    Args:
        sc_val: The SCVal to decode

    Returns:
        Native Python value (int, str, bool, bytes, etc.)
    """
    sc_type = sc_val.type

    if sc_type == SCValType.SCV_VOID:
        return None

    if sc_type == SCValType.SCV_U64:
        return int(sc_val.u64.uint64)

    if sc_type == SCValType.SCV_I64:
        return int(sc_val.i64.int64)

    if sc_type == SCValType.SCV_U32:
        return int(sc_val.u32.uint32)

    if sc_type == SCValType.SCV_I32:
        return int(sc_val.i32.int32)

    if sc_type == SCValType.SCV_SYMBOL:
        # SCSymbol contains bytes
        return sc_val.sym.sc_symbol.decode("utf-8")

    if sc_type == SCValType.SCV_BOOL:
        return bool(sc_val.b)

    if sc_type == SCValType.SCV_STRING:
        # SCString contains bytes
        return sc_val.str.sc_string.decode("utf-8")

    if sc_type == SCValType.SCV_BYTES:
        # SCBytes contains bytes
        return bytes(sc_val.bytes.sc_bytes)

    if sc_type == SCValType.SCV_ADDRESS:
        address = sc_val.address
        if address.type == SCAddressType.SC_ADDRESS_TYPE_ACCOUNT:
            # Convert account ID to Stellar address (G...)
            from stellar_sdk import StrKey
            public_key = address.account_id
            if hasattr(public_key, "account_id"):
                # AccountID wraps the public key in ``account_id``
                public_key = public_key.account_id
            return StrKey.encode_ed25519_public_key(bytes(public_key.ed25519.uint256))
        elif address.type == SCAddressType.SC_ADDRESS_TYPE_CONTRACT:
            # Convert contract ID to Stellar address (C...)
            from stellar_sdk import StrKey
            contract_ref = address.contract_id
            if not hasattr(contract_ref, "hash"):
                # ContractID wraps its 32-byte hash in ``contract_id``
                contract_ref = contract_ref.contract_id
            return StrKey.encode_contract(bytes(contract_ref.hash))
        return str(address)

    # For complex types, fall back to the SDK's to_native
    # (though it may not handle all complex types perfectly)
    try:
        return scval.to_native(sc_val)
    except Exception:
        logger.warning("Failed to decode SCVal type %s, returning raw XDR", sc_type)
        return {"xdr": sc_val.to_xdr(), "type": str(sc_type)}


def _decode_child(value: Any) -> Any:
    """Decode a nested ``SCVal`` child, passing native values through.

    XDR-decoded entries always carry ``SCVal`` children, but values built via
    ``stellar_sdk.scval.to_map`` may already be plain Python strings.
    """
    if isinstance(value, SCVal):
        return _decode_complex_scval(value)
    return value


def _decode_complex_scval(sc_val: SCVal) -> Any:
    """
    Recursively decode complex SCVal types (maps, vectors, contract instances).

    Supports: MAP, VEC, ADDRESS, CONTRACT_INSTANCE, and nested combinations.

    Args:
        sc_val: The SCVal to decode

    Returns:
        Native Python value (dict, list, str, etc.)
    """
    sc_type = sc_val.type

    # Handle primitive types first
    if sc_type in (
        SCValType.SCV_VOID,
        SCValType.SCV_U64,
        SCValType.SCV_I64,
        SCValType.SCV_U32,
        SCValType.SCV_I32,
        SCValType.SCV_SYMBOL,
        SCValType.SCV_BOOL,
        SCValType.SCV_STRING,
        SCValType.SCV_BYTES,
    ):
        return _decode_primitive_scval(sc_val)

    # Handle ADDRESS
    if sc_type == SCValType.SCV_ADDRESS:
        return _decode_primitive_scval(sc_val)

    # Handle VEC (array/list)
    if sc_type == SCValType.SCV_VEC:
        if sc_val.vec is None:
            return []
        vec = sc_val.vec
        items = vec.sc_vec if hasattr(vec, 'sc_vec') else vec
        return [_decode_child(item) for item in items]

    # Handle MAP (dictionary)
    if sc_type == SCValType.SCV_MAP:
        if sc_val.map is None:
            return {}
        map_obj = sc_val.map
        entries = map_obj.sc_map if hasattr(map_obj, 'sc_map') else map_obj
        result = {}
        for entry in entries:
            key = _decode_child(entry.key)
            val = _decode_child(entry.val)
            # Keys must be hashable for dict; convert to string if needed
            if not isinstance(key, (str, int, float, bool, tuple)):
                key = str(key)
            result[key] = val
        return result

    # Handle CONTRACT_INSTANCE
    if sc_type == SCValType.SCV_CONTRACT_INSTANCE:
        if sc_val.instance is None:
            return {"type": "contract_instance", "data": None}
        instance = sc_val.instance
        executable = instance.executable
        executable_info = {}
        if executable.type == ContractExecutableType.CONTRACT_EXECUTABLE_WASM:
            executable_info = {
                "type": "wasm",
                "wasm_hash": bytes(executable.wasm_hash.hash).hex() if executable.wasm_hash else None,
            }
        elif executable.type == ContractExecutableType.CONTRACT_EXECUTABLE_STELLAR_ASSET:
            executable_info = {
                "type": "stellar_asset",
            }

        # Decode storage entries
        storage = instance.storage
        storage_entries = {}
        if storage:
            storage_map = storage.sc_map if hasattr(storage, 'sc_map') else storage
            for entry in storage_map:
                key = _decode_child(entry.key)
                val = _decode_child(entry.val)
                if not isinstance(key, (str, int, float, bool, tuple)):
                    key = str(key)
                storage_entries[key] = val

        return {
            "type": "contract_instance",
            "executable": executable_info,
            "storage": storage_entries,
        }

    # For any other types, try the SDK's to_native
    try:
        return scval.to_native(sc_val)
    except Exception:
        logger.warning("Failed to decode SCVal type %s, returning raw XDR", sc_type)
        return {"xdr": sc_val.to_xdr(), "type": str(sc_type)}


@dataclass
class TransactionResult:
    """Result of a Soroban transaction."""

    success: bool
    tx_hash: str
    status: str
    error: Optional[str] = None
    result_xdr: Optional[str] = None


@dataclass
class InvocationData:
    """Parsed invocation metadata from transaction response."""

    caller: str
    contract: str
    function_name: str
    parameters: dict
    result: Optional[dict]
    ledger_sequence: int
    success: bool
    error: Optional[str] = None


class XDRDecoder:
    """Decode Soroban event SCVal XDR into JSON-safe Python values."""

    @classmethod
    def decode(cls, value: SCVal | bytes | str) -> Any:
        """Decode an SCVal object, raw XDR bytes, or base64 XDR string."""
        return cls._json_safe(scval.to_native(value))

    @classmethod
    def decode_event(
        cls,
        topics: list[SCVal | bytes | str],
        payload: SCVal | bytes | str,
    ) -> dict[str, Any]:
        """Decode event topics and payload into a clean JSON-compatible dict."""
        return {
            "topics": [cls.decode(topic) for topic in topics],
            "payload": cls.decode(payload),
        }

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value

        if isinstance(value, (bytes, bytearray)):
            return f"0x{bytes(value).hex()}"

        if isinstance(value, dict):
            return {
                cls._json_key(key): cls._json_safe(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple)):
            return [cls._json_safe(item) for item in value]

        address = getattr(value, "address", None)
        if isinstance(address, str):
            return address

        if isinstance(value, SCVal):
            raise TypeError(f"Unsupported Soroban SCVal type: {value.type}")

        return str(value)

    @classmethod
    def _json_key(cls, value: Any) -> str:
        decoded = cls._json_safe(value)
        if isinstance(decoded, str):
            return decoded
        if decoded is None:
            return "null"
        if isinstance(decoded, bool):
            return "true" if decoded else "false"
        return str(decoded)


class RateLimiter:
    """Token bucket rate limiter for RPC requests."""

    def __init__(self, rate: int = 10):
        """
        Initialize rate limiter.

        Args:
            rate: Maximum requests per second (default: 10)
        """
        self.rate = rate  # requests per second
        self.tokens = float(rate)
        self.last_update = time.time()
        self.lock = Lock()

    def acquire(self):
        """Block until a token is available."""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens < 1:
                sleep_time = (1 - self.tokens) / self.rate
                time.sleep(sleep_time)
                self.tokens = 0
            else:
                self.tokens -= 1


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

        # Invocation tracking infrastructure
        self._rate_limiter = RateLimiter(rate=10)
        self._invocation_cache = {}  # tx_hash -> (InvocationData, timestamp)
        self._cache_ttl = 300  # 5 minutes
        self._cache_max_size = 1000

    def _address_to_sc_val(self, address: str) -> SCVal:
        """Convert a Stellar address string to an ``SCV_ADDRESS`` SCVal.

        Args:
            address: A Stellar account address (starts with ``G``) or contract
                address (starts with ``C``).

        Returns:
            An ``SCVal`` of type ``SCV_ADDRESS`` wrapping the decoded address.

        Raises:
            ValueError: If *address* does not start with ``G`` or ``C``.
        """
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
        """Convert a plain string to an ``SCV_SYMBOL`` SCVal.

        Args:
            symbol: The symbol string to encode (UTF-8).

        Returns:
            An ``SCVal`` of type ``SCV_SYMBOL``.
        """
        return SCVal(
            type=SCValType.SCV_SYMBOL,
            sym=SCSymbol(symbol.encode("utf-8")),
        )

    def _bytes_to_sc_val(self, data: bytes) -> SCVal:
        """Convert a raw bytes value to an ``SCV_BYTES`` SCVal.

        Args:
            data: Raw bytes to wrap.

        Returns:
            An ``SCVal`` of type ``SCV_BYTES``.
        """
        return SCVal(
            type=SCValType.SCV_BYTES,
            bytes=SCBytes(data),
        )

    def _get_admin_keypair(self) -> Optional[Keypair]:
        """Return the admin ``Keypair`` derived from settings.

        Prefers ``ADMIN_SECRET_KEY``; falls back to the instance's
        ``secret_key``.  Returns ``None`` when neither is configured.

        Returns:
            A ``Keypair`` object, or ``None`` if no secret key is available.
        """
        admin_secret = getattr(settings, "ADMIN_SECRET_KEY", "") or self.secret_key
        if not admin_secret:
            return None
        return Keypair.from_secret(admin_secret)

    def _submit_contract_transaction(
        self,
        function_name: str,
        parameters: list[SCVal],
        signer: Keypair,
    ) -> TransactionResult:
        """Simulate, prepare, sign, and submit a Soroban contract write transaction.

        The method performs the full round-trip:
        1. Load the source account sequence number from RPC.
        2. Build a ``InvokeContractFunction`` transaction.
        3. Simulate the transaction to obtain resource fees.
        4. Prepare the transaction with the simulation footprint.
        5. Sign and submit to the network.

        Args:
            function_name: Name of the Soroban contract function to invoke.
            parameters: Ordered list of ``SCVal`` arguments for the function.
            signer: The ``Keypair`` that will sign the transaction.

        Returns:
            A :class:`TransactionResult` with ``success=True`` when the
            network accepted the transaction (status ``PENDING``), or
            ``success=False`` with an ``error`` description on any failure.
        """
        try:
            account = self.server.load_account(signer.public_key)
            tx_builder = TransactionBuilder(
                source_account=account,
                network_passphrase=self.network_passphrase,
                base_fee=100000,
            )
            tx_builder.append_invoke_contract_function_op(
                contract_id=self.contract_id,
                function_name=function_name,
                parameters=parameters,
            )
            tx = tx_builder.set_timeout(30).build()
            simulate_response = self.server.simulate_transaction(tx)

            if simulate_response.error:
                return TransactionResult(
                    success=False,
                    tx_hash="",
                    status="simulation_failed",
                    error=simulate_response.error,
                )

            prepared_tx = self.server.prepare_transaction(tx, simulate_response)
            prepared_tx.sign(signer)
            send_response = self.server.send_transaction(prepared_tx)

            logger.info(
                "Contract transaction submitted: %s (%s)",
                send_response.hash,
                function_name,
            )

            return TransactionResult(
                success=send_response.status == "PENDING",
                tx_hash=send_response.hash,
                status=send_response.status,
                result_xdr=getattr(send_response, "result_xdr", None),
            )
        except Exception as exc:
            logger.exception("Failed to submit contract transaction: %s", function_name)
            return TransactionResult(
                success=False,
                tx_hash="",
                status="error",
                error=str(exc),
            )

    def _run_simulation(self, function_name: str, parameters: list[SCVal]) -> Any:
        """Execute a Soroban RPC simulation and decode the return value.

        Raises:
            _SimulationError: when the RPC returns an error or no result.
                Failures are deliberately raised (rather than returned) so the
                simulation cache never stores them.
        """
        account = self.server.load_account(self.keypair.public_key)
        tx_builder = TransactionBuilder(
            source_account=account,
            network_passphrase=self.network_passphrase,
            base_fee=100,
        )
        tx_builder.append_invoke_contract_function_op(
            contract_id=self.contract_id,
            function_name=function_name,
            parameters=parameters,
        )
        tx = tx_builder.set_timeout(30).build()
        simulate_response = self.server.simulate_transaction(tx)

        if simulate_response.error:
            raise _SimulationError(str(simulate_response.error))

        results = getattr(simulate_response, "results", None) or []
        if not results:
            raise _SimulationError("No simulation result returned")

        result_xdr = getattr(results[0], "xdr", None)
        if not result_xdr:
            raise _SimulationError("Missing result XDR")

        sc_val_obj = stellar_xdr.SCVal.from_xdr(result_xdr)
        return _decode_complex_scval(sc_val_obj)

    def _simulate_contract_read(
        self,
        function_name: str,
        parameters: list[SCVal],
    ) -> tuple[bool, Any]:
        """Simulate a read-only contract call and decode the return value.

        Successful results are cached in Redis for 60 seconds (issue #1402);
        identical calls for the same contract/function/args skip the RPC
        entirely inside that window.
        """
        if not self.keypair:
            return False, "No keypair configured for simulation"

        try:
            args_xdr = [param.to_xdr() for param in parameters]
            value = get_cached_simulation_result(
                self.contract_id,
                function_name,
                args_xdr,
                lambda: self._run_simulation(function_name, parameters),
            )
            return True, value
        except _SimulationError as exc:
            return False, str(exc)
        except Exception as exc:
            logger.exception("Failed to simulate contract read: %s", function_name)
            return False, str(exc)

    def add_indexer(self, indexer_address: str) -> TransactionResult:
        """Submit an ``add_indexer`` transaction to the SoroScan contract (SC-9).

        The configured admin keypair signs the transaction.  The contract
        grants the provided address indexer privileges, allowing it to call
        ``record_event`` on behalf of the platform.

        Args:
            indexer_address: Stellar address (``G...``) of the indexer to
                authorise.

        Returns:
            A :class:`TransactionResult` describing the outcome.  ``success``
            is ``False`` when no admin keypair is configured or when the RPC
            call fails.
        """
        admin_keypair = self._get_admin_keypair()
        if not admin_keypair:
            return TransactionResult(
                success=False,
                tx_hash="",
                status="error",
                error="No admin keypair configured",
            )

        return self._submit_contract_transaction(
            function_name="add_indexer",
            parameters=[
                self._address_to_sc_val(admin_keypair.public_key),
                self._address_to_sc_val(indexer_address),
            ],
            signer=admin_keypair,
        )

    def is_indexer(self, indexer_address: str) -> tuple[bool, Any]:
        """Query whether an address holds indexer privileges on the contract (SC-15).

        Executes a read-only simulation of the ``is_indexer`` contract function.
        The result is cached in Redis for 60 seconds.

        Args:
            indexer_address: Stellar address (``G...``) to check.

        Returns:
            A ``(success, value)`` tuple.  When *success* is ``True``, *value*
            is a ``bool`` indicating authorisation.  When *success* is
            ``False``, *value* is an error description string.
        """
        return self._simulate_contract_read(
            function_name="is_indexer",
            parameters=[self._address_to_sc_val(indexer_address)],
        )

    def get_admin(self) -> tuple[bool, Any]:
        """Query the current admin address stored on the contract (SC-15).

        Executes a read-only simulation of the ``get_admin`` contract function.
        The result is cached in Redis for 60 seconds.

        Returns:
            A ``(success, value)`` tuple.  When *success* is ``True``, *value*
            is the admin's Stellar address string.  When *success* is
            ``False``, *value* is an error description string.
        """
        return self._simulate_contract_read(
            function_name="get_admin",
            parameters=[],
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

    def record_structured_event(
        self,
        target_contract_id: str,
        event_type: str,
        payload_hash_hex: str,
        schema_version: int,
        correlation_id_hex: str,
    ) -> TransactionResult:
        """Submit a versioned, correlation-safe event record (SC-38).

        Extends :meth:`record_event` with a ``schema_version`` field and a
        ``correlation_id`` that lets consumers deduplicate or trace related
        events across the ledger.

        Args:
            target_contract_id: Stellar contract address (``C...``) of the
                contract that emitted the original event.
            event_type: The type/category of the event (e.g. ``"transfer"``).
            payload_hash_hex: Hex-encoded SHA-256 hash (32 bytes) of the event
                payload.
            schema_version: Integer schema version used when encoding the
                payload, stored as ``SCV_U32`` on-chain.
            correlation_id_hex: Hex-encoded 32-byte identifier used to
                correlate this event with related ones.

        Returns:
            A :class:`TransactionResult` with ``success=True`` when the
            network accepted the transaction (status ``PENDING``), or
            ``success=False`` with an ``error`` description on any failure.

        Raises:
            ValueError: If either *payload_hash_hex* or *correlation_id_hex*
                does not decode to exactly 32 bytes.
        """
        if not self.keypair:
            return TransactionResult(False, "", "error", error="No keypair configured")

        try:
            payload_hash = bytes.fromhex(payload_hash_hex)
            correlation_id = bytes.fromhex(correlation_id_hex)
            if len(payload_hash) != 32 or len(correlation_id) != 32:
                raise ValueError("Payload hash and correlation ID must be 32 bytes")
            account = self.server.load_account(self.keypair.public_key)
            tx = (
                TransactionBuilder(
                    source_account=account,
                    network_passphrase=self.network_passphrase,
                    base_fee=100000,
                )
                .append_invoke_contract_function_op(
                    contract_id=self.contract_id,
                    function_name="record_structured_event",
                    parameters=[
                        self._address_to_sc_val(self.keypair.public_key),
                        self._address_to_sc_val(target_contract_id),
                        self._symbol_to_sc_val(event_type),
                        self._bytes_to_sc_val(payload_hash),
                        SCVal(type=SCValType.SCV_U32, u32=schema_version),
                        self._bytes_to_sc_val(correlation_id),
                    ],
                )
                .set_timeout(30)
                .build()
            )
            simulation = self.server.simulate_transaction(tx)
            if simulation.error:
                return TransactionResult(False, "", "simulation_failed", error=simulation.error)
            prepared = self.server.prepare_transaction(tx, simulation)
            prepared.sign(self.keypair)
            response = self.server.send_transaction(prepared)
            return TransactionResult(
                success=response.status == "PENDING",
                tx_hash=response.hash,
                status=response.status,
                result_xdr=getattr(response, "result_xdr", None),
            )
        except Exception as e:
            logger.exception("Failed to record SC-38 structured event")
            return TransactionResult(False, "", "error", error=str(e))

    def get_total_events(self) -> Optional[int]:
        """
        Query the total_events function on the contract.

        The decoded result is cached in Redis for 60 seconds (issue #1402).

        Returns:
            Total event count or None on error
        """
        try:
            if not self.keypair:
                return None

            # This is a read-only call, so we simulate without submitting
            total = get_cached_simulation_result(
                self.contract_id,
                "total_events",
                [],
                lambda: self._run_simulation("total_events", []),
            )

            if isinstance(total, bool) or not isinstance(total, int):
                logger.warning(
                    "Expected integer from total_events, got %s", type(total).__name__
                )
                return None
            return total

        except Exception:
            logger.exception("Failed to get total events")
            return None

    def get_events_range(
        self,
        contract_id: str,
        start_ledger: int,
        end_ledger: int,
    ) -> list[Any]:
        """Fetch raw contract events within an inclusive ledger range.

        Issues a ``getEvents`` RPC call filtered to *contract_id*.  When the
        SDK variant in use does not support the ``end_ledger`` parameter, the
        call is retried without it and results are filtered client-side.

        The caller is responsible for pagination when the range spans many
        ledgers; this method fetches at most 200 events per call.

        Args:
            contract_id: Stellar contract address (``C...``) to filter by.
            start_ledger: First ledger sequence to include (inclusive).
            end_ledger: Last ledger sequence to include (inclusive).

        Returns:
            A list of raw SDK event objects whose ``ledger`` attribute falls
            within ``[start_ledger, end_ledger]``.  Returns an empty list when
            *start_ledger* > *end_ledger* or the RPC returns no results.
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
            response = execute_with_circuit_breaker(
                "soroban_rpc",
                self.server.get_events,
                start_ledger=start_ledger,
                end_ledger=end_ledger,
                filters=filters,
                pagination=pagination,
            )
        except TypeError:
            # Some SDK variants do not support end_ledger.
            response = execute_with_circuit_breaker(
                "soroban_rpc",
                self.server.get_events,
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

    def _get_from_cache(self, tx_hash: str) -> Optional[InvocationData]:
        """Return a cached :class:`InvocationData` entry, or ``None`` if absent or expired.

        Args:
            tx_hash: Transaction hash used as the cache key.

        Returns:
            The cached :class:`InvocationData` when a non-expired entry exists,
            otherwise ``None``.
        """
        if tx_hash in self._invocation_cache:
            data, timestamp = self._invocation_cache[tx_hash]
            if time.time() - timestamp < self._cache_ttl:
                return data
            else:
                del self._invocation_cache[tx_hash]
        return None

    def _add_to_cache(self, tx_hash: str, data: InvocationData) -> None:
        """Store an :class:`InvocationData` entry with LRU eviction.

        When the cache has reached ``_cache_max_size`` entries the oldest
        entry (by insertion timestamp) is evicted before the new one is added.

        Args:
            tx_hash: Transaction hash used as the cache key.
            data: Parsed invocation data to cache.
        """
        if len(self._invocation_cache) >= self._cache_max_size:
            # Evict oldest entry
            oldest_key = min(
                self._invocation_cache.keys(),
                key=lambda k: self._invocation_cache[k][1],
            )
            del self._invocation_cache[oldest_key]

        self._invocation_cache[tx_hash] = (data, time.time())

    def _parse_transaction_response(self, tx_response) -> InvocationData:
        """
        Extract invocation metadata from Soroban RPC transaction response.

        Parses:
        - Source account (caller)
        - Contract address from operation
        - Function name from invoke_contract operation
        - Parameters from operation arguments (XDR-encoded)
        - Result from transaction result XDR
        """
        try:
            # Extract source account
            caller = getattr(tx_response, "source_account", "")
            if not caller:
                raise ValueError("No source account in transaction")

            # Extract ledger sequence
            ledger_sequence = getattr(tx_response, "ledger", 0)

            # Extract contract and function from transaction envelope
            # The transaction response contains the envelope with operations
            envelope = getattr(tx_response, "envelope_xdr", None)
            if not envelope:
                raise ValueError("No envelope in transaction response")

            # For now, we'll extract basic info from the response
            # In a real implementation, we'd parse the XDR envelope
            # This is a simplified version that assumes the response has these fields
            contract = ""
            function_name = ""
            parameters = {}

            # Try to extract from result_xdr if available
            result_xdr = getattr(tx_response, "result_xdr", None)

            # Store result as XDR-encoded dict
            result = None
            if result_xdr:
                result = {"xdr": result_xdr}

            # For a minimal implementation, we'll return what we have
            # A full implementation would parse the XDR to extract contract/function
            if not contract or not function_name:
                # Try to get from other fields if available
                # This is a placeholder - real implementation needs XDR parsing
                raise ValueError("Could not extract contract and function from transaction")

            return InvocationData(
                caller=caller,
                contract=contract,
                function_name=function_name,
                parameters=parameters,
                result=result,
                ledger_sequence=ledger_sequence,
                success=True,
            )

        except Exception as e:
            logger.warning("Failed to parse transaction response: %s", e)
            return InvocationData(
                caller="",
                contract="",
                function_name="",
                parameters={},
                result=None,
                ledger_sequence=0,
                success=False,
                error=f"Parse error: {str(e)}",
            )

    def get_invocation(self, tx_hash: str) -> InvocationData:
        """
        Fetch invocation details for a transaction.

        Implements:
        - LRU caching with 5-minute TTL
        - Rate limiting at 10 req/s
        - XDR parsing for caller, contract, function, params, result

        Args:
            tx_hash: Transaction hash to fetch

        Returns:
            InvocationData with parsed metadata or error indicator
        """
        # Check cache
        cached = self._get_from_cache(tx_hash)
        if cached:
            return cached

        # Rate limit
        self._rate_limiter.acquire()

        try:
            # Fetch transaction from RPC
            tx_response = execute_with_circuit_breaker(
                "soroban_rpc",
                self.server.get_transaction,
                tx_hash,
            )

            if not tx_response or getattr(tx_response, "status", None) == "NOT_FOUND":
                return InvocationData(
                    caller="",
                    contract="",
                    function_name="",
                    parameters={},
                    result=None,
                    ledger_sequence=0,
                    success=False,
                    error="Transaction not found",
                )

            # Parse invocation data
            invocation = self._parse_transaction_response(tx_response)

            # Cache result
            self._add_to_cache(tx_hash, invocation)

            return invocation

        except Exception as e:
            logger.exception("Failed to fetch invocation for tx_hash=%s", tx_hash)
            return InvocationData(
                caller="",
                contract="",
                function_name="",
                parameters={},
                result=None,
                ledger_sequence=0,
                success=False,
                error=str(e),
            )

    def get_contract_state(
        self,
        contract_id: str,
        ledger: Optional[int] = None,
    ) -> dict[str, Any]:
        """Fetch persistent storage entries for a contract from Soroban RPC.

        Calls ``getLedgerEntries`` on the configured ``SorobanServer``.  When
        the RPC method is unavailable or fails the method returns a minimal
        marker payload so callers can still persist a snapshot record.

        Args:
            contract_id: Stellar contract address (``C...``) whose state to
                retrieve.
            ledger: Optional ledger sequence to scope the snapshot.  When
                ``None`` the RPC returns the latest known state and the actual
                ledger number is included in the response payload.

        Returns:
            A JSON-serialisable ``dict`` with keys:

            - ``contract_id`` (*str*): echoes the input.
            - ``ledger`` (*int | None*): ledger sequence of the snapshot, or
              ``None`` if unavailable.
            - ``entries`` (*dict*): mapping of entry identifiers to their
              decoded values.  Empty when the RPC call fails or returns no
              entries.
        """
        payload: dict[str, Any] = {
            "contract_id": contract_id,
            "ledger": ledger,
            "entries": {},
        }

        get_entries = getattr(self.server, "get_ledger_entries", None)
        if get_entries is None:
            logger.warning("SorobanServer.get_ledger_entries is unavailable")
            return payload

        try:
            attributes = {"contract_id": contract_id}
            if ledger is not None:
                attributes["ledger"] = ledger
            with tracer.start_as_current_span(
                "soroban.rpc.get_contract_state", attributes=attributes
            ):
                self._rate_limiter.acquire()
                response = execute_with_circuit_breaker(
                    "soroban_rpc",
                    get_entries,
                    keys=[{"contractData": {"contract": contract_id, "key": "AAAA"}}],
                )
        except Exception:
            logger.exception("Failed to fetch contract state for %s", contract_id)
            return payload

        entries = getattr(response, "entries", None) or getattr(response, "result", None) or []
        serialized: dict[str, Any] = {}
        for index, entry in enumerate(entries):
            key = getattr(entry, "key", None) or getattr(entry, "contractData", None)
            val = getattr(entry, "val", None) or getattr(entry, "value", None)
            serialized[str(key or index)] = self._serialize_ledger_entry_value(val)

        payload["entries"] = serialized
        latest_ledger = getattr(response, "latestLedger", None)
        if latest_ledger is not None:
            payload["ledger"] = latest_ledger
        return payload

    @staticmethod
    def _serialize_ledger_entry_value(value: Any) -> Any:
        """Serialize a raw ledger entry value to a JSON-safe Python type.

        Tries, in order: pass-through for already-serialisable types, the
        object's ``to_dict()`` method, its ``xdr`` attribute, and finally
        ``str(value)`` as a last resort.

        Args:
            value: Raw ledger entry value returned by the RPC SDK.

        Returns:
            A JSON-serialisable representation: ``None``, a primitive, a
            ``dict``, a ``list``, or a plain string.
        """
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool, list, dict)):
            return value
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if hasattr(value, "xdr"):
            return {"xdr": value.xdr}
        return str(value)

    # ------------------------------------------------------------------
    # Fee / resource extraction
    # ------------------------------------------------------------------

    @staticmethod
    def extract_fee_data(tx_response: Any) -> dict[str, int]:
        """
        Extract Soroban fee and resource usage from a ``get_transaction`` response.

        The Stellar RPC returns ``fee_charged`` (total fee in stroops) on the
        top-level response object.  Detailed resource breakdown (CPU instructions,
        memory, read/write bytes) lives inside the ``result_meta_xdr`` (or
        ``resultMetaXdr``) SorobanTransactionMeta v3 structure.

        This helper is intentionally defensive: it tries several attribute and
        dict key variants produced by different stellar-sdk versions and falls
        back gracefully to zeros.  The values it returns are always non-negative
        integers measured in stroops (fees) or raw units (resources).

        Returns a dict with keys:
          total_fee_stroops, inclusion_fee_stroops, resource_fee_stroops,
          cpu_instructions_used, memory_bytes_used,
          read_bytes_used, write_bytes_used
        """
        result: dict[str, int] = {
            "total_fee_stroops": 0,
            "inclusion_fee_stroops": 0,
            "resource_fee_stroops": 0,
            "cpu_instructions_used": 0,
            "memory_bytes_used": 0,
            "read_bytes_used": 0,
            "write_bytes_used": 0,
        }

        if tx_response is None:
            return result

        # ── Total fee ──────────────────────────────────────────────────
        for attr in ("fee_charged", "feeCharged", "fee"):
            val = _get_attr_or_key(tx_response, attr)
            if val is not None:
                try:
                    result["total_fee_stroops"] = int(val)
                except (TypeError, ValueError):
                    pass
                break

        # ── Try to parse Soroban resource stats from result_meta_xdr ──
        # stellar_sdk >= 8 exposes a typed `result_meta` with `.soroban_meta`
        # Older versions expose raw XDR strings.
        # We attempt the typed path first, then fall back.
        try:
            result_meta = (
                _get_attr_or_key(tx_response, "result_meta")
                or _get_attr_or_key(tx_response, "resultMeta")
            )
            if result_meta is not None:
                soroban_meta = (
                    _get_attr_or_key(result_meta, "soroban_meta")
                    or _get_attr_or_key(result_meta, "sorobanMeta")
                )
                if soroban_meta is not None:
                    resources = (
                        _get_attr_or_key(soroban_meta, "resources")
                        or _get_attr_or_key(soroban_meta, "v3")
                    )
                    if resources is not None:
                        _set_int(result, "cpu_instructions_used", resources,
                                 ("cpu_insns", "cpuInsns", "instructions", "cpuInstructions"))
                        _set_int(result, "memory_bytes_used", resources,
                                 ("mem_bytes", "memBytes", "memory", "memoryBytes"))
                        _set_int(result, "read_bytes_used", resources,
                                 ("read_bytes", "readBytes", "netReadBytes", "net_read_bytes"))
                        _set_int(result, "write_bytes_used", resources,
                                 ("write_bytes", "writeBytes", "netWriteBytes", "net_write_bytes"))

                    # Resource fee is sometimes a sibling field on soroban_meta
                    _set_int(result, "resource_fee_stroops", soroban_meta,
                             ("resource_fee_refund", "resourceFeeRefund",
                              "resource_fee", "resourceFee"))

        except Exception:
            # Any parse error → keep zeros; don't crash the ingest loop
            pass

        # Derive inclusion fee as the difference
        result["inclusion_fee_stroops"] = max(
            0, result["total_fee_stroops"] - result["resource_fee_stroops"]
        )

        return result


# ---------------------------------------------------------------------------
# Module-level helpers used by SorobanClient.extract_fee_data
# ---------------------------------------------------------------------------

def _get_attr_or_key(obj: Any, name: str) -> Any:
    """Try attribute access then dict-key access; return ``None`` if neither works.

    Args:
        obj: The object or mapping to inspect.
        name: Attribute or key name to look up.

    Returns:
        The resolved value, or ``None`` when *name* is not present on *obj*.
    """
    val = getattr(obj, name, None)
    if val is None and isinstance(obj, dict):
        val = obj.get(name)
    return val


def _set_int(
    result: dict[str, int],
    key: str,
    source: Any,
    attr_names: tuple[str, ...],
) -> None:
    """Write the first non-``None`` integer found in *source* to ``result[key]``.

    Iterates over *attr_names* and calls :func:`_get_attr_or_key` for each.
    The first value that can be cast to ``int`` is stored and the function
    returns immediately.  No-ops when none of the names resolve to a usable
    integer.

    Args:
        result: The output dict to update in place.
        key: The key in *result* to set.
        source: Object or mapping to search for the value.
        attr_names: Ordered tuple of attribute/key names to try on *source*.
    """
    for name in attr_names:
        val = _get_attr_or_key(source, name)
        if val is not None:
            try:
                result[key] = int(val)
                return
            except (TypeError, ValueError):
                pass
