"""
Celery tasks for SoroScan background processing.
"""

import threading
import cProfile
import calendar
import base64
import hashlib
import hmac
import io
import json
import logging
import pstats
import re
import time
from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import jsonschema
import requests
from celery import shared_task
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from celery.signals import task_postrun, task_prerun, task_retry
from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg, Count, F, Max, Min
from django.utils import timezone

from soroscan.circuit_breaker import execute_with_circuit_breaker
from soroscan.webhook_signing import build_x_signature_header
from soroscan.log_context import log_context_var

from .cache_utils import (
    invalidate_event_count_cache,
    get_cached_decoded_payload,
    set_cached_decoded_payload,
    invalidate_decoded_payload_cache,
    get_cached_contract,
    contract_name_cache_key,
    CONTRACT_NAME_CACHE_TTL,
    _SENTINEL,
)
from .telemetry import inject_trace_headers, payload_compression_ratio, tracer
from .reorg import check_and_handle_reorg, is_event_deliverable
from .models import (
    BlacklistedContract,
    ContractABI,
    ContractEvent,
    ContractSigningKey,
    TrackedContract,
    WebhookSubscription,
    IndexerState,
    EventSchema,
    RemediationRule,
    RemediationIncident,
    AdminAction,
    ContractInvocation,
    ContractDependency,
    CallGraph,
    DependencyImpactAssessment,
    Organization,
    OrganizationBudget,
    OrganizationCostSnapshot,
    WebhookDeadLetter,
    ContractHealthCheck,
    ContractDeployment,
    ContractVerification,
    ContractSource,
    WebhookDeliveryLog,
    IngestError,
    DataRetentionPolicy,
    DataDeletionRequest,
    PIIField,
)
from stellar_sdk import SorobanServer
from .rate_limit import check_ingest_rate
from .stellar_client import SorobanClient
from .metrics import webhook_payload_bytes
from .streaming import get_producer

logger = logging.getLogger(__name__)
BATCH_LEDGER_SIZE = 200
_SLOW_TASK_THRESHOLD_S = 5.0  # log profiling stats when task exceeds this

# ---------------------------------------------------------------------------
# Celery task profiling via signals — instruments all tasks automatically
# ---------------------------------------------------------------------------
_task_profilers: dict[str, tuple] = {}


@task_prerun.connect
def _start_task_profiling(task_id: str, task, **kwargs) -> None:
    try:
        profiler = cProfile.Profile()
        profiler.enable()
        _task_profilers[task_id] = (profiler, time.monotonic())
    except ValueError:
        pass


@task_postrun.connect
def _stop_task_profiling(task_id: str, task, **kwargs) -> None:
    entry = _task_profilers.pop(task_id, None)
    if entry is None:
        return
    profiler, start = entry
    profiler.disable()
    elapsed = time.monotonic() - start
    if elapsed > _SLOW_TASK_THRESHOLD_S:
        stream = io.StringIO()
        pstats.Stats(profiler, stream=stream).sort_stats(
            pstats.SortKey.CUMULATIVE
        ).print_stats(20)
        logger.warning(
            "Slow task %s took %.2fs\n%s",
            task.name,
            elapsed,
            stream.getvalue(),
            extra={"task_name": task.name, "total_time_s": round(elapsed, 3)},
        )


# ---------------------------------------------------------------------------
# Celery task timeout monitoring via signals — warns at 80% of timeout
# ---------------------------------------------------------------------------
_task_timeout_timers: dict[str, threading.Timer] = {}


def _log_timeout_warning(task_name: str, remaining: float) -> None:
    logger.warning(
        "Task %s is approaching timeout. %.1f seconds remaining.",
        task_name,
        remaining,
        extra={"task_name": task_name, "time_remaining": remaining},
    )


@task_prerun.connect
def _start_timeout_monitor(task_id: str, task, **kwargs) -> None:
    # Check request first, then task class, then global settings for timeouts
    timeout = (
        getattr(task.request, "soft_time_limit", None)
        or getattr(task.request, "time_limit", None)
        or getattr(task, "soft_time_limit", None)
        or getattr(task, "time_limit", None)
        or getattr(settings, "CELERY_TASK_SOFT_TIME_LIMIT", None)
        or getattr(settings, "CELERY_TASK_TIME_LIMIT", None)
    )

    if timeout:
        warning_delay = float(timeout) * 0.8
        remaining = float(timeout) - warning_delay
        timer = threading.Timer(
            warning_delay, _log_timeout_warning, args=(task.name, remaining)
        )
        timer.daemon = True
        _task_timeout_timers[task_id] = timer
        timer.start()


@task_postrun.connect
def _stop_timeout_monitor(task_id: str, task, **kwargs) -> None:
    timer = _task_timeout_timers.pop(task_id, None)
    if timer:
        timer.cancel()


@task_retry.connect
def _log_task_retry_signal(sender, task_id, args, kwargs, einfo, **extra) -> None:
    """
    Log all Celery task retries with attempt number and next retry time.
    This signal fires for both manual self.retry() calls and autoretry_for.
    """
    task_name = sender.name if sender else "unknown"
    request = sender.request if sender else None
    attempt_number = request.retries + 1 if request else 1
    
    # Extract exception type from einfo
    exception_type = einfo.type.__name__ if einfo and einfo.type else "Unknown"
    
    # Try to get countdown from request
    countdown = getattr(request, "countdown", None) if request else None
    next_retry_time = None
    if countdown is not None:
        next_retry_time = timezone.now() + timedelta(seconds=countdown)
    
    logger.info(
        "Task %s retry scheduled (attempt %d) due to %s. Next retry: %s",
        task_name,
        attempt_number + 1,  # Next attempt number
        exception_type,
        next_retry_time.isoformat() if next_retry_time else "calculated with backoff",
        extra={
            "task_name": task_name,
            "task_id": task_id,
            "attempt_number": attempt_number + 1,
            "exception_type": exception_type,
            "next_retry_time": next_retry_time.isoformat() if next_retry_time else None,
            "countdown_seconds": countdown,
        },
    )


# ---------------------------------------------------------------------------
# Backoff calculation for webhook retries
# ---------------------------------------------------------------------------


def calculate_backoff(attempt: int, strategy: str, base_seconds: int) -> int:
    """
    Calculate the backoff delay for a webhook retry attempt.

    Args:
        attempt: 0-based attempt number (0 = first retry, 1 = second retry, etc.)
        strategy: One of 'exponential', 'linear', or 'fixed'
        base_seconds: Base number of seconds for the backoff calculation

    Returns:
        Backoff delay in seconds

    Note:
        For 'exponential' strategy, it is recommended to use Celery's built-in
        retry_backoff parameter instead of this function to get better jitter support.
    """
    if strategy == "exponential":
        # base_seconds * 2^attempt
        return base_seconds * (2**attempt)
    elif strategy == "linear":
        # base_seconds * attempt (add 1 because attempt is 0-based)
        return base_seconds * (attempt + 1)
    elif strategy == "fixed":
        # Always return base_seconds
        return base_seconds
    else:
        # Default to exponential if unknown strategy
        return base_seconds * (2**attempt)


def _log_task_retry(
    task_name: str,
    attempt_number: int,
    exception_type: str,
    countdown: int | None = None,
) -> None:
    """
    Log Celery task retry with attempt number and next retry time.
    
    Args:
        task_name: Name of the task being retried
        attempt_number: Current attempt number (1-based)
        exception_type: Type of exception that triggered the retry
        countdown: Seconds until next retry (None if using exponential backoff with jitter)
    """
    next_retry_time = None
    if countdown is not None:
        next_retry_time = timezone.now() + timedelta(seconds=countdown)
    
    logger.info(
        "Task %s retry scheduled (attempt %d) due to %s. Next retry: %s",
        task_name,
        attempt_number,
        exception_type,
        next_retry_time.isoformat() if next_retry_time else "calculated with jitter",
        extra={
            "task_name": task_name,
            "attempt_number": attempt_number,
            "exception_type": exception_type,
            "next_retry_time": next_retry_time.isoformat() if next_retry_time else None,
            "countdown_seconds": countdown,
        },
    )


# ---------------------------------------------------------------------------
# Prometheus metrics (imported lazily to avoid import-time side-effects
# during migrations/management commands that don't need metrics).
# ---------------------------------------------------------------------------


def _get_metrics():
    """Return the metrics module, importing it on first call."""
    from soroscan.ingest import metrics  # noqa: PLC0415

    return metrics


def _network_label() -> str:
    """Return a short label for the current Stellar network."""
    passphrase: str = getattr(settings, "STELLAR_NETWORK_PASSPHRASE", "")
    if "Public" in passphrase:
        return "mainnet"
    if "Test" in passphrase:
        return "testnet"
    return "unknown"


def _short_contract_id(contract_id: str) -> str:
    """
    Truncate contract_id to its first 8 chars to keep Prometheus label
    cardinality bounded (full 56-char IDs would create one series per contract).
    """
    return contract_id[:8] if contract_id else "unknown"


def _event_attr(event: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if hasattr(event, name):
            return getattr(event, name)
        if isinstance(event, dict) and name in event:
            return event[name]
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _calculate_completeness(contract: TrackedContract) -> dict[str, Any]:
    stats = ContractEvent.objects.filter(contract=contract).aggregate(
        min_ledger=Min("ledger"),
        max_ledger=Max("ledger"),
        observed_ledgers=Count("ledger", distinct=True),
    )
    min_ledger = stats["min_ledger"]
    max_ledger = stats["max_ledger"]
    observed_ledgers = stats["observed_ledgers"] or 0
    if min_ledger is None or max_ledger is None:
        return {
            "contract_id": contract.contract_id,
            "completeness_percentage": 100.0,
            "observed_ledgers": 0,
            "expected_ledgers": 0,
            "missing_ledgers": 0,
            "gaps": [],
        }

    expected_ledgers = (max_ledger - min_ledger + 1) if max_ledger >= min_ledger else 0
    missing_ledgers = max(expected_ledgers - observed_ledgers, 0)

    ledgers = (
        ContractEvent.objects.filter(contract=contract)
        .order_by("ledger")
        .values_list("ledger", flat=True)
        .distinct()
    )
    gaps: list[dict[str, int]] = []
    previous = None
    for ledger in ledgers:
        if previous is not None and ledger > previous + 1:
            gaps.append({"from_ledger": previous + 1, "to_ledger": ledger - 1})
        previous = ledger

    completeness_percentage = (
        100.0
        if expected_ledgers == 0
        else (observed_ledgers / expected_ledgers) * 100.0
    )
    return {
        "contract_id": contract.contract_id,
        "completeness_percentage": round(completeness_percentage, 4),
        "observed_ledgers": observed_ledgers,
        "expected_ledgers": expected_ledgers,
        "missing_ledgers": missing_ledgers,
        "gaps": gaps,
    }


def _extract_event_index(event: Any, fallback_index: int = 0) -> int:
    direct_index = _event_attr(event, "event_index", "index")
    if direct_index is not None:
        return _safe_int(direct_index, fallback_index)

    identifier = str(_event_attr(event, "id", "paging_token", default="") or "")
    if "-" in identifier:
        maybe_index = identifier.rsplit("-", maxsplit=1)[-1]
        if maybe_index.isdigit():
            return int(maybe_index)

    return fallback_index


def _decode_key_or_sig(value: Any) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value

    raw = str(value).strip()
    if not raw:
        return None
    if raw.startswith("0x"):
        raw = raw[2:]

    if len(raw) % 2 == 0 and all(c in "0123456789abcdefABCDEF" for c in raw):
        try:
            return bytes.fromhex(raw)
        except ValueError:
            pass

    try:
        return base64.b64decode(raw, validate=True)
    except Exception:
        return raw.encode("utf-8")


def _extract_signature(event: Any, payload: dict[str, Any]) -> Any:
    return (
        _event_attr(event, "signature", "event_signature")
        or payload.get("signature")
        or payload.get("event_signature")
        or payload.get("sig")
    )


def _message_for_signature(event: Any, payload: dict[str, Any]) -> bytes:
    payload_hash = _event_attr(event, "payload_hash") or payload.get("payload_hash")
    payload_hash_bytes = _decode_key_or_sig(payload_hash)
    if payload_hash_bytes:
        return payload_hash_bytes

    # Build canonical payload bytes excluding signature metadata fields.
    signing_payload = {
        k: v
        for k, v in payload.items()
        if k not in {"signature", "event_signature", "sig"}
    }
    return json.dumps(signing_payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _build_webhook_signature_header(
    webhook: WebhookSubscription, payload_bytes: bytes
) -> str:
    algorithm = (
        webhook.signature_algorithm or WebhookSubscription.SIGNATURE_SHA256
    ).lower()
    if algorithm == WebhookSubscription.SIGNATURE_SHA1:
        digestmod = hashlib.sha1
        prefix = "sha1"
    else:
        digestmod = hashlib.sha256
        prefix = "sha256"

    sig_hex = hmac.new(
        webhook.secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=digestmod,
    ).hexdigest()
    return f"{prefix}={sig_hex}"


def validate_contract_payload_schema(
    contract: TrackedContract,
    payload: dict[str, Any],
    event_type: str,
    ledger: int | None = None,
) -> bool:
    """
    Validate payload against ``TrackedContract.json_schema`` when configured.

    Returns True when no schema is configured or payload passes validation.
    """
    with tracer.start_as_current_span(
        "ingest.validate_contract_payload_schema",
        attributes={
            "contract_id": contract.contract_id,
            "event_type": event_type,
            "ledger": ledger or 0,
        },
    ):
        if contract.json_schema in (None, {}):
            return True

        try:
            jsonschema.validate(instance=payload, schema=contract.json_schema)
            return True
        except jsonschema.ValidationError as exc:
            logger.error(
                "Contract JSON schema validation failed for contract_id=%s event_type=%s ledger=%s: %s",
                contract.contract_id,
                event_type,
                ledger,
                exc.message,
                extra={
                    "contract_id": contract.contract_id,
                    "event_type": event_type,
                    "ledger": ledger,
                },
            )
            return False


def _load_signing_public_key(key: ContractSigningKey):
    value = (key.public_key or "").strip()
    if not value:
        return None

    if "-----BEGIN" in value:
        return serialization.load_pem_public_key(value.encode("utf-8"))

    key_bytes = _decode_key_or_sig(value)
    if not key_bytes:
        return None

    if key.algorithm == ContractSigningKey.Algorithm.ED25519:
        return ed25519.Ed25519PublicKey.from_public_bytes(key_bytes)

    # ECDSA flexibility: accept uncompressed points for common curves.
    for curve in (ec.SECP256R1(), ec.SECP256K1()):
        try:
            return ec.EllipticCurvePublicKey.from_encoded_point(curve, key_bytes)
        except ValueError:
            continue
    return None


def resolve_signature_status(
    contract: TrackedContract,
    event: Any,
    payload: dict[str, Any],
) -> str:
    """
    Return one of: valid, invalid, missing.

    Verification never raises and never blocks ingest.
    """
    signing_key = (
        ContractSigningKey.objects.filter(contract=contract, is_active=True)
        .only("algorithm", "public_key")
        .first()
    )
    if signing_key is None:
        return "missing"

    signature_value = _extract_signature(event, payload)
    signature = _decode_key_or_sig(signature_value)
    if not signature:
        return "missing"

    message = _message_for_signature(event, payload)

    try:
        public_key = _load_signing_public_key(signing_key)
        if public_key is None:
            logger.warning(
                "Signing key not usable for contract=%s",
                contract.contract_id,
                extra={"contract_id": contract.contract_id},
            )
            return "invalid"

        if signing_key.algorithm == ContractSigningKey.Algorithm.ED25519:
            public_key.verify(signature, message)
        else:
            public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))

        return "valid"
    except InvalidSignature:
        logger.warning(
            "Invalid event signature for contract=%s",
            contract.contract_id,
            extra={"contract_id": contract.contract_id},
        )
        return "invalid"
    except Exception:
        logger.warning(
            "Event signature verification error for contract=%s",
            contract.contract_id,
            extra={"contract_id": contract.contract_id},
            exc_info=True,
        )
        return "invalid"


def _upsert_contract_event(
    contract: TrackedContract,
    event: Any,
    fallback_event_index: int = 0,
    client: SorobanClient | None = None,
    batch_cache: dict | None = None,
) -> tuple[ContractEvent, bool]:
    with tracer.start_as_current_span(
        "ingest.upsert_contract_event",
        attributes={
            "contract_id": contract.contract_id,
            "network": _network_label(),
        },
    ):
        # Check rate limit before processing
        if not check_ingest_rate(contract):
            m = _get_metrics()
            m.events_rate_limited_total.labels(
                contract_id=_short_contract_id(contract.contract_id),
                network=_network_label(),
            ).inc()
            logger.warning(
                "Rate limit exceeded for contract %s — skipping event",
                contract.contract_id,
                extra={"contract_id": contract.contract_id},
            )
            # Return a dummy tuple to indicate the event was skipped
            return (None, False)

        ledger = _safe_int(_event_attr(event, "ledger", "ledger_sequence"), default=0)
        event_index = _extract_event_index(event, fallback_event_index)
        tx_hash = str(_event_attr(event, "tx_hash", "transaction_hash", default="") or "")
        event_type = str(
            _event_attr(event, "type", "event_type", default="unknown") or "unknown"
        )

        # Check whitelist/blacklist filter before persisting
        if not contract.should_ingest_event(event_type):
            m = _get_metrics()
            m.events_filtered_total.labels(
                contract_id=_short_contract_id(contract.contract_id),
                network=_network_label(),
                filter_type=contract.event_filter_type,
                event_type=event_type,
            ).inc()
            logger.debug(
                "Event type '%s' filtered (%s) for contract %s — skipping",
                event_type,
                contract.event_filter_type,
                contract.contract_id,
                extra={"contract_id": contract.contract_id, "event_type": event_type},
            )
            return (None, False)

        payload = _event_attr(event, "value", "payload", default={}) or {}

        if not validate_contract_payload_schema(
            contract, payload, event_type, ledger=ledger
        ):
            m = _get_metrics()
            m.events_validation_failures_total.labels(
                contract_id=_short_contract_id(contract.contract_id),
                network=_network_label(),
            ).inc()
            return (None, False)

        payload_compression_ratio(payload)

        raw_xdr = str(_event_attr(event, "xdr", "raw_xdr", default="") or "")
        signature_status = resolve_signature_status(contract, event, payload)

        timestamp = _event_attr(event, "timestamp", default=timezone.now())
        if isinstance(timestamp, datetime) and timezone.is_naive(timestamp):
            timestamp = timezone.make_aware(timestamp, dt_timezone.utc)
        if not isinstance(timestamp, datetime):
            timestamp = timezone.now()

        result = ContractEvent.objects.update_or_create(
            contract=contract,
            ledger=ledger,
            event_index=event_index,
            defaults={
                "tx_hash": tx_hash,
                "event_type": event_type,
                "payload": payload,
                "timestamp": timestamp,
                "raw_xdr": raw_xdr,
                "signature_status": signature_status,
            },
        )

        # Update contract last activity timestamp if this event is newer
        if not contract.last_event_at or timestamp > contract.last_event_at:
            contract.last_event_at = timestamp
            contract.save(update_fields=["last_event_at", "updated_at"])

        obj, created = result
        if created:
            # Invalidate event count cache
            invalidate_event_count_cache(contract.contract_id)

            m = _get_metrics()
            m.events_ingested_total.labels(
                contract_id=_short_contract_id(contract.contract_id),
                network=_network_label(),
                event_type=event_type,
            ).inc()
            # Refresh the active contracts gauge whenever a new event arrives.
            m.active_contracts_gauge.set(
                TrackedContract.objects.filter(is_active=True).count()
            )

            # --- ABI-based XDR decoding (issue #58) ---
            _try_decode_event(obj, contract, event_type, raw_xdr)
        else:
            # Event updated — invalidate decoded payload cache so next query re-decodes
            invalidate_decoded_payload_cache(obj.pk)

        return result


def _try_decode_event(
    obj: ContractEvent,
    contract: TrackedContract,
    event_type: str,
    raw_xdr: str,
) -> None:
    """Attempt ABI decoding for a newly created event.

    Checks Redis cache first (key: decoded:{event_id}, TTL 24h).
    Never raises — failures are recorded via ``decoding_status``.
    """
    from .decoder import decode_event_payload

    # Check cache first
    cached = get_cached_decoded_payload(obj.pk)
    if cached is not _SENTINEL:
        if cached is not None:
            obj.decoded_payload = cached
            obj.decoding_status = "success"
            obj.save(update_fields=["decoded_payload", "decoding_status"])
        return

    try:
        abi = ContractABI.objects.get(contract=contract)
    except ContractABI.DoesNotExist:
        # No ABI registered — leave default decoding_status="no_abi"
        return

    if not raw_xdr:
        obj.decoding_status = "no_abi"
        obj.save(update_fields=["decoding_status"])
        return

    try:
        decoded = decode_event_payload(raw_xdr, abi.abi_json, event_type)
        if decoded is not None:
            obj.decoded_payload = decoded
            obj.decoding_status = "success"
            set_cached_decoded_payload(obj.pk, decoded)
        else:
            obj.decoding_status = "failed"
        obj.save(update_fields=["decoded_payload", "decoding_status"])
    except Exception:
        logger.warning(
            "ABI decoding failed for event %s (contract=%s, type=%s)",
            obj.pk,
            contract.contract_id,
            event_type,
            exc_info=True,
        )
        obj.decoding_status = "failed"
        obj.save(update_fields=["decoding_status"])


def validate_event_payload(
    contract: TrackedContract,
    event_type: str,
    payload: dict[str, Any],
    ledger: int | None = None,
) -> tuple[bool, int | None]:
    """
    Validate event payload against the latest EventSchema for this contract+event_type.

    Returns:
        (passed, version_used): passed is True if no schema exists or validation succeeded;
        version_used is the EventSchema.version used, or None if no schema.
    """
    with tracer.start_as_current_span(
        "ingest.validate_event_payload",
        attributes={
            "contract_id": contract.contract_id,
            "event_type": event_type,
            "ledger": ledger or 0,
        },
    ):
        if payload is None or not isinstance(payload, dict):
            return (True, None)
        schema = (
            EventSchema.objects.filter(
                contract=contract,
                event_type=event_type,
            )
            .order_by("-version")
            .first()
        )
        if schema is None:
            return (True, None)
        try:
            jsonschema.validate(instance=payload, schema=schema.json_schema)
            return (True, schema.version)
        except jsonschema.ValidationError:
            logger.warning(
                "Event payload schema validation failed for contract_id=%s event_type=%s ledger=%s",
                contract.contract_id,
                event_type,
                ledger,
                extra={
                    "contract_id": contract.contract_id,
                    "event_type": event_type,
                    "ledger": ledger,
                },
            )
            return (False, schema.version)


@shared_task(
    name="ingest.tasks.dispatch_webhook",
    bind=True,
    max_retries=5,
    soft_time_limit=30,
)
def dispatch_webhook(self, subscription_id: int, event_id: int, replay: bool = False) -> bool:
    """
    Deliver a single ContractEvent to a WebhookSubscription endpoint.

    Retry Policy:
    - Maximum Retries: 5 (total 6 attempts)
    - Backoff Strategy: Exponential by default (2^attempt * base)
    - Base Delay: Configurable per subscription (default 2s)
    - Jitter: Applied to exponential retries to prevent thundering herds
    - Suspension: Subscriptions are suspended after all retries are exhausted.

    When ``replay`` is True (used by the local event replay utility) delivery
    deduplication is skipped so the same historical event can be re-sent, and
    the payload includes the event's original timestamp.
    """
    _start = time.monotonic()
    m = _get_metrics()

    with tracer.start_as_current_span(
        "webhook.dispatch",
        attributes={"webhook_id": subscription_id, "event_id": event_id},
    ):
        try:
            webhook = WebhookSubscription.objects.get(
                id=subscription_id,
                is_active=True,
                status=WebhookSubscription.STATUS_ACTIVE,
            )
        except WebhookSubscription.DoesNotExist:
            logger.warning(
                "Webhook subscription %s not found, inactive, or suspended — skipping",
                subscription_id,
                extra={"webhook_id": subscription_id},
            )
            return False

        try:
            event = ContractEvent.objects.select_related("contract").get(id=event_id)
        except ContractEvent.DoesNotExist:
            logger.warning(
                "ContractEvent %s not found — skipping dispatch for subscription %s",
                event_id,
                subscription_id,
                extra={"event_id": event_id, "webhook_id": subscription_id},
            )
            return False

        if not is_event_deliverable(event):
            logger.info(
                "Skipping webhook dispatch for orphaned event %s",
                event_id,
                extra={"event_id": event_id, "webhook_id": subscription_id},
            )
            return False

        # Deduplicate identical webhook deliveries to prevent floods.
        # Replay skips dedup so operators can retest the same historical event.
        if not replay:
            dedup_window = int(getattr(settings, "WEBHOOK_DEDUP_WINDOW_SECONDS", 300))
            dedup_material = json.dumps(
                {
                    "subscription_id": subscription_id,
                    "contract_id": event.contract.contract_id,
                    "event_type": event.event_type,
                    "ledger": event.ledger,
                    "event_index": event.event_index,
                    "payload": event.payload,
                },
                sort_keys=True,
            )
            dedup_hash = hashlib.sha256(dedup_material.encode("utf-8")).hexdigest()
            dedup_key = f"soroscan:webhooks:dedup:{subscription_id}:{dedup_hash}"
            if not cache.add(dedup_key, "1", timeout=dedup_window):
                logger.info(
                    "Deduplicated webhook delivery for subscription=%s event=%s",
                    subscription_id,
                    event_id,
                    extra={"webhook_id": subscription_id, "event_id": event_id},
                )
                m.webhook_deduplicated_total.inc()
                return True  # Consider deduplicated delivery as successful

        event_data = {
            "contract_id": event.contract.contract_id,
            "event_type": event.event_type,
            "payload": event.payload,
            "ledger": event.ledger,
            "event_index": event.event_index,
            "tx_hash": event.tx_hash,
        }
        if replay:
            original_ts = event.timestamp
            if original_ts is not None and timezone.is_naive(original_ts):
                original_ts = timezone.make_aware(original_ts, dt_timezone.utc)
            event_data["timestamp"] = original_ts.isoformat() if original_ts else None
            event_data["replay"] = True
        payload_bytes = json.dumps(event_data, sort_keys=True).encode("utf-8")
        payload_size = len(payload_bytes)

        # Log warning if payload exceeds 512 KB
        if payload_size > 512 * 1024:
            logger.warning(
                "Large webhook payload detected for contract %s: %d bytes (> 512 KB)",
                event.contract.contract_id,
                payload_size,
                extra={
                    "contract_id": event.contract.contract_id,
                    "payload_bytes": payload_size,
                },
            )

        # Record histogram metric
        webhook_payload_bytes.labels(
            contract_id=event.contract.contract_id,
        ).observe(payload_size)

        headers = {
            "Content-Type": "application/json",
            "X-SoroScan-Timestamp": timezone.now().isoformat(),
        }
        ctx = log_context_var.get()
        traceparent = ctx.get("traceparent")
        if traceparent:
            headers["traceparent"] = traceparent
        with tracer.start_as_current_span(
            "webhook.sign", attributes={"webhook_id": subscription_id}
        ):
            headers["X-SoroScan-Signature"] = _build_webhook_signature_header(
                webhook, payload_bytes
            )
        if replay:
            headers["X-SoroScan-Replay"] = "true"
            original_ts = event_data.get("timestamp")
            if original_ts:
                headers["X-SoroScan-Original-Timestamp"] = original_ts
        inject_trace_headers(headers)

        attempt_number = self.request.retries + 1
        attempt_logged = False

        try:
            headers["X-Signature"] = build_x_signature_header(payload_bytes)
        except ValueError:
            logger.warning(
                "Skipping Ed25519 webhook signature; WEBHOOK_ED25519_SIGNING_SEED not set",
                extra={"webhook_id": webhook.id},
            )

        try:
            timeout_value = int(webhook.timeout_seconds) if webhook.timeout_seconds else 10
        except (TypeError, ValueError):
            timeout_value = 10

        try:
            with tracer.start_as_current_span(
                "webhook.http_post",
                attributes={
                    "webhook_id": subscription_id,
                    "target_url": webhook.target_url,
                    "attempt": attempt_number,
                },
            ):
                response = requests.post(
                    webhook.target_url,
                    data=payload_bytes,
                    headers=headers,
                    timeout=timeout_value,
                )
            status_code = response.status_code
            elapsed_s = time.monotonic() - _start
            latency_ms = int(elapsed_s * 1000)

            if status_code == 429:
                error_msg = "Rate limited by subscriber (429)"
                _log_delivery_attempt(
                    webhook,
                    event,
                    attempt_number,
                    status_code,
                    False,
                    error_msg,
                    payload_size,
                    acknowledged=False,
                    latency_ms=latency_ms,
                    within_sla=False,
                )
                attempt_logged = True
                _on_delivery_failure(
                    webhook,
                    self,
                    event,
                    event_data,
                    status_code=status_code,
                    error=error_msg,
                )
                m.webhook_deliveries_total.labels(status="rate_limited").inc()

                countdown: int | None = None
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        countdown = int(retry_after)
                    except (ValueError, TypeError):
                        pass

                # Check if we've exhausted retries
                if self.request.retries >= self.max_retries:
                    # Final attempt — don't retry, let the HTTPError propagate
                    raise requests.HTTPError("Rate limited (429)", response=response)

                # If no Retry-After header, use webhook's backoff strategy
                if countdown is None:
                    if webhook.retry_backoff_strategy == WebhookSubscription.BACKOFF_EXPONENTIAL:
                        _log_task_retry(
                            "dispatch_webhook",
                            attempt_number + 1,
                            "RateLimitError",
                            countdown=None,
                        )
                        raise self.retry(
                            exc=requests.HTTPError("Rate limited (429)", response=response),
                            retry_backoff=webhook.retry_backoff_seconds,
                            retry_jitter=True,
                        )
                    countdown = calculate_backoff(
                        self.request.retries,
                        webhook.retry_backoff_strategy,
                        webhook.retry_backoff_seconds,
                    )

                _log_task_retry(
                    "dispatch_webhook",
                    attempt_number + 1,
                    "RateLimitError",
                    countdown=countdown,
                )
                raise self.retry(
                    exc=requests.HTTPError("Rate limited (429)", response=response),
                    countdown=countdown,
                )

            acknowledged, ack_status = _validate_webhook_ack(response, webhook)
            m.webhook_ack_total.labels(status=ack_status).inc()

            within_sla = bool(
                200 <= status_code < 300
                and acknowledged
                and elapsed_s <= webhook.delivery_sla_seconds
            )
            if 200 <= status_code < 300 and acknowledged:
                m.webhook_sla_total.labels(
                    outcome="within_sla" if within_sla else "breached"
                ).inc()

            success = 200 <= status_code < 300 and acknowledged
            if success:
                error_msg = ""
            elif 200 <= status_code < 300:
                error_msg = (
                    f"Missing or invalid acknowledgement header "
                    f"'{webhook.ack_header_name}: {webhook.ack_header_value}'"
                )
            else:
                error_msg = f"HTTP {status_code}"

            # Determine response body (truncated to 4 KB by model.save)
            try:
                _resp_body = response.text if hasattr(response, "text") else ""
            except Exception:
                _resp_body = ""
            _delivery_status = (
                "success"
                if success
                else (
                    "dead_letter"
                    if self.request.retries >= self.max_retries
                    else "failed"
                )
            )
            _log_delivery_attempt(
                webhook,
                event,
                attempt_number,
                status_code,
                success,
                error_msg,
                payload_size,
                acknowledged=acknowledged,
                latency_ms=latency_ms,
                within_sla=within_sla,
                status=_delivery_status,
                response_body=_resp_body,
                duration_ms=latency_ms,
            )
            attempt_logged = True

            if success:
                WebhookSubscription.objects.filter(pk=webhook.pk).update(
                    failure_count=0,
                    last_triggered=timezone.now(),
                )
                logger.info(
                    "Webhook %s delivered successfully (attempt %s)",
                    subscription_id,
                    attempt_number,
                    extra={"webhook_id": subscription_id},
                )
                m.webhook_deliveries_total.labels(status="success").inc()
                m.webhook_delivery_duration_seconds.observe(elapsed_s)
                m.task_duration_seconds.labels(task_name="dispatch_webhook").observe(
                    elapsed_s
                )
                return True

            _on_delivery_failure(
                webhook,
                self,
                event,
                event_data,
                status_code=status_code,
                error=error_msg,
            )
            m.webhook_deliveries_total.labels(status="failure").inc()

            if 200 <= status_code < 300 and not acknowledged:
                nack_exc = requests.HTTPError(error_msg, response=response)
                if self.request.retries >= self.max_retries:
                    raise nack_exc
                countdown = calculate_backoff(
                    self.request.retries,
                    webhook.retry_backoff_strategy,
                    webhook.retry_backoff_seconds,
                )
                raise self.retry(exc=nack_exc, countdown=countdown)

            response.raise_for_status()
        except requests.exceptions.Timeout:
            elapsed_s = time.monotonic() - _start
            latency_ms = int(elapsed_s * 1000)
            # Log timeout as 504 Gateway Timeout
            if not attempt_logged:
                _log_delivery_attempt(
                    webhook,
                    event,
                    attempt_number,
                    504,
                    False,
                    "Timeout exceeded",
                    payload_size,
                    acknowledged=False,
                    latency_ms=latency_ms,
                    within_sla=False,
                )
                attempt_logged = True
                _on_delivery_failure(
                    webhook,
                    self,
                    event,
                    event_data,
                    status_code=504,
                    error="Timeout exceeded",
                )

            logger.warning(
                "Webhook %s dispatch timed out (attempt %s/%s) after %d seconds",
                subscription_id,
                attempt_number,
                self.max_retries + 1,
                webhook.timeout_seconds,
                extra={"webhook_id": subscription_id},
            )

            # Check if we've exhausted retries
            if self.request.retries >= self.max_retries:
                # Final attempt — don't retry, let the exception propagate
                raise

            # Retry with backoff based on webhook's strategy
            if webhook.retry_backoff_strategy == WebhookSubscription.BACKOFF_EXPONENTIAL:
                _log_task_retry(
                    "dispatch_webhook",
                    attempt_number + 1,
                    "TimeoutError",
                    countdown=None,
                )
                raise self.retry(retry_backoff=webhook.retry_backoff_seconds, retry_jitter=True)

            countdown = calculate_backoff(
                self.request.retries,
                webhook.retry_backoff_strategy,
                webhook.retry_backoff_seconds,
            )
            _log_task_retry(
                "dispatch_webhook",
                attempt_number + 1,
                "TimeoutError",
                countdown=countdown,
            )
            raise self.retry(countdown=countdown)

        except requests.RequestException as exc:
            elapsed_s = time.monotonic() - _start
            latency_ms = int(elapsed_s * 1000)
            if not attempt_logged:
                _log_delivery_attempt(
                    webhook,
                    event,
                    attempt_number,
                    None,
                    False,
                    str(exc),
                    payload_size,
                    acknowledged=False,
                    latency_ms=latency_ms,
                    within_sla=False,
                )
                _on_delivery_failure(
                    webhook,
                    self,
                    event,
                    event_data,
                    status_code=None,
                    error=str(exc),
                )
            m.webhook_deliveries_total.labels(status="failure").inc()
            m.webhook_delivery_duration_seconds.observe(elapsed_s)
            m.task_duration_seconds.labels(task_name="dispatch_webhook").observe(
                elapsed_s
            )

            logger.warning(
                "Webhook %s dispatch failed (attempt %s/%s): %s",
                subscription_id,
                attempt_number,
                self.max_retries + 1,
                exc,
                extra={"webhook_id": subscription_id},
            )

            # Check if we've exhausted retries
            if self.request.retries >= self.max_retries:
                # Final attempt — don't retry, let the exception propagate
                raise

            # Retry with backoff based on webhook's strategy
            if webhook.retry_backoff_strategy == WebhookSubscription.BACKOFF_EXPONENTIAL:
                _log_task_retry(
                    "dispatch_webhook",
                    attempt_number + 1,
                    type(exc).__name__,
                    countdown=None,
                )
                raise self.retry(exc=exc, retry_backoff=webhook.retry_backoff_seconds, retry_jitter=True)

            countdown = calculate_backoff(
                self.request.retries,
                webhook.retry_backoff_strategy,
                webhook.retry_backoff_seconds,
            )
            _log_task_retry(
                "dispatch_webhook",
                attempt_number + 1,
                type(exc).__name__,
                countdown=countdown,
            )
            raise self.retry(exc=exc, countdown=countdown)

        m.webhook_delivery_duration_seconds.observe(time.monotonic() - _start)
        m.task_duration_seconds.labels(task_name="dispatch_webhook").observe(
            time.monotonic() - _start
        )
        return False


@shared_task(name="ingest.tasks.ping_webhook", bind=True)
def ping_webhook(self, subscription_id: int) -> dict:
    """
    Send a minimal ping payload to a webhook endpoint to verify it is reachable.

    Returns a dict with ``success`` (bool) and either ``status_code`` (int) on
    a network response or ``error`` (str) on a connection failure.
    """
    try:
        webhook = WebhookSubscription.objects.get(id=subscription_id)
    except WebhookSubscription.DoesNotExist:
        logger.warning(
            "Webhook subscription %s not found for ping",
            subscription_id,
            extra={"webhook_id": subscription_id},
        )
        return {"success": False, "error": "Subscription not found"}

    payload = {"type": "ping", "timestamp": timezone.now().isoformat()}
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-SoroScan-Event": "ping",
    }

    try:
        response = requests.post(
            webhook.target_url,
            data=payload_bytes,
            headers=headers,
            timeout=webhook.timeout_seconds,
        )
        success = response.status_code == 200
        logger.info(
            "Ping webhook %s -> %s (HTTP %d)",
            subscription_id,
            "success" if success else "failure",
            response.status_code,
            extra={"webhook_id": subscription_id, "status_code": response.status_code},
        )
        return {"success": success, "status_code": response.status_code}
    except requests.RequestException as exc:
        logger.warning(
            "Ping to webhook %s failed: %s",
            subscription_id,
            exc,
            extra={"webhook_id": subscription_id},
        )
        return {"success": False, "error": str(exc)}


@shared_task(name="ingest.tasks.notify_contract_pause_state", bind=True)
def notify_contract_pause_state(
    self, contract_id: str, state: str, reason: str = ""
) -> int:
    """
    Notify all active webhooks for a contract that it was paused or resumed.

    This is a lifecycle notification, not a chain event, so it is delivered
    to every active subscription regardless of the subscription's
    ``event_type``/``filter_condition`` (those filter contract *events*, not
    system-level state changes). Best-effort like ``ping_webhook`` — a failed
    delivery is logged but does not retry or affect the pause/resume itself.
    """
    payload = {
        "type": f"contract.{state}",
        "contract_id": contract_id,
        "reason": reason,
        "timestamp": timezone.now().isoformat(),
    }
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-SoroScan-Event": f"contract.{state}",
    }

    webhooks = WebhookSubscription.objects.filter(
        contract__contract_id=contract_id,
        is_active=True,
        status=WebhookSubscription.STATUS_ACTIVE,
    )
    notified = 0
    for webhook in webhooks:
        try:
            requests.post(
                webhook.target_url,
                data=payload_bytes,
                headers=headers,
                timeout=webhook.timeout_seconds,
            )
            notified += 1
        except requests.RequestException as exc:
            logger.warning(
                "Contract %s notification to webhook %s failed: %s",
                state,
                webhook.id,
                exc,
                extra={"webhook_id": webhook.id, "contract_id": contract_id},
            )
    return notified


@shared_task(name="ingest.tasks.auto_resume_paused_contracts")
def auto_resume_paused_contracts() -> int:
    """Resume any paused contract whose scheduled ``resume_at`` has passed."""
    due = TrackedContract.objects.filter(
        is_paused=True,
        resume_at__isnull=False,
        resume_at__lte=timezone.now(),
    )
    resumed = 0
    for contract in due:
        contract.resume()
        resumed += 1
    return resumed


# ---------------------------------------------------------------------------
# Private helpers for dispatch_webhook
# ---------------------------------------------------------------------------


def _log_delivery_attempt(
    webhook: WebhookSubscription,
    event: ContractEvent,
    attempt_number: int,
    status_code: int | None,
    success: bool,
    error: str,
    payload_bytes: int | None = None,
    acknowledged: bool = False,
    latency_ms: int | None = None,
    within_sla: bool = False,
    status: str = "pending",
    response_body: str = "",
    duration_ms: int | None = None,
) -> None:
    """Create a ``WebhookDeliveryLog`` record for one dispatch attempt.

    The ``status`` field maps to WebhookDeliveryLog.STATUS_* constants:
    - ``pending``:     created before the HTTP request (pre-create)
    - ``success``:     2xx + acknowledged
    - ``failed``:      non-2xx or unacknowledged
    - ``dead_letter``: final failed attempt after max retries

    ``response_body`` is truncated to ``RESPONSE_BODY_MAX_BYTES`` (4 KB)
    by the model's ``save()`` method.
    """
    from .models import WebhookDeliveryLog

    WebhookDeliveryLog.objects.create(
        subscription=webhook,
        event=event,
        attempt_number=attempt_number,
        status=status,
        status_code=status_code,
        success=success,
        error=error,
        response_body=response_body,
        duration_ms=duration_ms,
        payload_bytes=payload_bytes,
        acknowledged=acknowledged,
        latency_ms=latency_ms,
        within_sla=within_sla,
    )


def _validate_webhook_ack(
    response: requests.Response,
    webhook: WebhookSubscription,
) -> tuple[bool, str]:
    """
    Return (acknowledged, status) based on configured acknowledgement header.

    Status values: valid | missing | invalid
    """
    header_name = (webhook.ack_header_name or "X-SoroScan-Ack").strip()
    expected_value = (webhook.ack_header_value or "ok").strip()
    received = response.headers.get(header_name)
    if received is None:
        return (False, "missing")
    if received.strip().lower() != expected_value.lower():
        return (False, "invalid")
    return (True, "valid")


def _default_webhook_escalation_policy() -> list[dict[str, Any]]:
    return [
        {
            "channel": "slack",
            "target": getattr(settings, "WEBHOOK_ESCALATION_SLACK_TARGET", ""),
            "after_failures": 2,
        },
        {
            "channel": "sms",
            "target": getattr(settings, "WEBHOOK_ESCALATION_SMS_TARGET", ""),
            "after_failures": 4,
        },
        {
            "channel": "pagerduty",
            "target": getattr(settings, "WEBHOOK_ESCALATION_PAGERDUTY_TARGET", ""),
            "after_failures": 6,
        },
    ]


def _normalized_webhook_escalation_policy(
    webhook: WebhookSubscription,
) -> list[dict[str, Any]]:
    raw = webhook.escalation_policy if isinstance(webhook.escalation_policy, list) else []
    policy: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        channel = str(entry.get("channel", "")).strip().lower()
        target = str(entry.get("target", "")).strip()
        if channel not in {"slack", "sms", "pagerduty"}:
            continue
        try:
            after_failures = int(entry.get("after_failures", 1))
        except (TypeError, ValueError):
            continue
        if after_failures < 1:
            continue
        policy.append(
            {
                "channel": channel,
                "target": target,
                "after_failures": after_failures,
            }
        )

    if not policy:
        policy = _default_webhook_escalation_policy()

    return sorted(policy, key=lambda item: item["after_failures"])


def _escalation_dedup_key(
    webhook_id: int,
    event_id: int | None,
    channel: str,
    threshold: int,
) -> str:
    return (
        f"soroscan:webhook_escalation:{webhook_id}:{event_id or 'none'}:"
        f"{channel}:{threshold}"
    )


def _send_escalation_message(
    channel: str,
    target: str,
    message: str,
    payload: dict[str, Any],
) -> None:
    timeout = getattr(settings, "WEBHOOK_ESCALATION_TIMEOUT_SECONDS", 10)
    if channel == "slack":
        resp = requests.post(target, json={"text": message, "payload": payload}, timeout=timeout)
    elif channel == "sms":
        resp = requests.post(target, json={"message": message, "payload": payload}, timeout=timeout)
    elif channel == "pagerduty":
        resp = requests.post(target, json={"summary": message, "payload": payload}, timeout=timeout)
    else:
        raise ValueError(f"Unsupported escalation channel: {channel}")
    resp.raise_for_status()


def _maybe_escalate_webhook_failure(
    webhook: WebhookSubscription,
    event: ContractEvent,
    failure_count: int,
    status_code: int | None,
    error: str,
) -> None:
    from django.core.cache import cache

    policy = _normalized_webhook_escalation_policy(webhook)
    dedup_ttl = int(getattr(settings, "WEBHOOK_ESCALATION_DEDUP_SECONDS", 300))
    m = _get_metrics()

    for entry in policy:
        threshold = entry["after_failures"]
        if failure_count != threshold:
            continue

        channel = entry["channel"]
        target = entry["target"]
        if not target:
            logger.warning(
                "Escalation channel %s configured without target for webhook %s",
                channel,
                webhook.id,
                extra={"webhook_id": webhook.id},
            )
            continue

        dedup_key = _escalation_dedup_key(
            webhook.id,
            event.id if event else None,
            channel,
            threshold,
        )
        if not cache.add(dedup_key, "1", timeout=dedup_ttl):
            continue

        message = (
            f"Webhook delivery escalation ({channel.upper()}) for subscription {webhook.id} "
            f"after {failure_count} consecutive failures."
        )
        payload = {
            "webhook_id": webhook.id,
            "target_url": webhook.target_url,
            "contract_id": webhook.contract.contract_id,
            "event_id": event.id if event else None,
            "event_type": event.event_type if event else None,
            "failure_count": failure_count,
            "status_code": status_code,
            "error": error[:500],
        }
        try:
            _send_escalation_message(channel, target, message, payload)
            m.webhook_escalations_total.labels(channel=channel, status="sent").inc()
        except Exception:
            m.webhook_escalations_total.labels(channel=channel, status="failed").inc()
            logger.exception(
                "Failed to send webhook escalation via %s for webhook %s",
                channel,
                webhook.id,
            )


def _enqueue_webhook_dead_letter(
    webhook: WebhookSubscription,
    event: ContractEvent,
    payload: dict[str, Any],
    status_code: int | None,
    error: str,
    retries_exhausted: int,
) -> None:
    WebhookDeadLetter.objects.create(
        subscription=webhook,
        event=event,
        payload=payload,
        status_code=status_code,
        error=error[:2000],
        retries_exhausted=retries_exhausted,
    )
    _get_metrics().webhook_dead_letter_depth.set(
        WebhookDeadLetter.objects.filter(resolved=False).count()
    )


def _on_delivery_failure(
    webhook: WebhookSubscription,
    task_instance,
    event: ContractEvent,
    payload: dict[str, Any],
    status_code: int | None,
    error: str,
) -> None:
    """
    Atomically increment ``failure_count`` and, when all retries are exhausted,
    mark the subscription as ``suspended`` + ``is_active=False``.
    """
    WebhookSubscription.objects.filter(pk=webhook.pk).update(
        failure_count=F("failure_count") + 1,
    )
    webhook.refresh_from_db(fields=["failure_count", "status", "is_active", "escalation_policy"])

    _maybe_escalate_webhook_failure(
        webhook=webhook,
        event=event,
        failure_count=webhook.failure_count,
        status_code=status_code,
        error=error,
    )

    is_last_attempt = task_instance.request.retries >= task_instance.max_retries
    if is_last_attempt:
        WebhookSubscription.objects.filter(pk=webhook.pk).update(
            status=WebhookSubscription.STATUS_SUSPENDED,
            is_active=False,
        )
        _enqueue_webhook_dead_letter(
            webhook=webhook,
            event=event,
            payload=payload,
            status_code=status_code,
            error=error,
            retries_exhausted=task_instance.max_retries + 1,
        )
        logger.error(
            "Webhook subscription %s suspended after %d consecutive failures",
            webhook.id,
            task_instance.max_retries + 1,
            extra={"webhook_id": webhook.id},
        )
        # Push in-app notification to the contract owner
        try:
            from .services.notifications import create_and_push

            owner = webhook.contract.owner
            create_and_push(
                user=owner,
                notification_type="webhook_failure",
                title="Webhook Suspended",
                message=(
                    f"Webhook to {webhook.target_url} for contract "
                    f"'{webhook.contract.name}' has been suspended after "
                    f"{task_instance.max_retries + 1} consecutive failures."
                ),
                link=f"/webhooks/{webhook.id}",
            )
        except Exception:
            logger.exception(
                "Failed to create webhook_failure notification for webhook %s",
                webhook.id,
            )


@shared_task(name="soroscan.ingest.tasks.cleanup_webhook_delivery_logs")
def cleanup_webhook_delivery_logs() -> int:
    """
    Prune ``WebhookDeliveryLog`` entries older than ``WEBHOOK_DELIVERY_RETENTION_DAYS`` days.

    The retention period defaults to 30 days and is configurable via the
    ``WEBHOOK_DELIVERY_RETENTION_DAYS`` environment variable (Issue #765).
    """
    from .models import WebhookDeliveryLog

    _start = time.monotonic()
    retention_days = int(getattr(settings, "WEBHOOK_DELIVERY_RETENTION_DAYS", 30))
    cutoff = timezone.now() - timedelta(days=retention_days)
    deleted_count, _ = WebhookDeliveryLog.objects.filter(timestamp__lt=cutoff).delete()
    logger.info(
        "Pruned %d WebhookDeliveryLog entries older than %d days",
        deleted_count,
        retention_days,
        extra={"retention_days": retention_days, "deleted_count": deleted_count},
    )
    _get_metrics().task_duration_seconds.labels(
        task_name="cleanup_webhook_delivery_logs"
    ).observe(time.monotonic() - _start)
    return deleted_count


@shared_task(name="soroscan.ingest.tasks.warm_contract_name_cache")
def warm_contract_name_cache() -> int:
    """
    Pre-populate the contract_address -> contract_name cache in Redis.

    Loads all TrackedContract records and writes a lightweight name-only
    entry for each one under the key ``soroscan:contract:name:{contract_id}``
    with a 24-hour TTL (``CONTRACT_NAME_CACHE_TTL``).

    The task is idempotent — running it multiple times is safe; each
    invocation simply refreshes the TTL.

    Returns the number of cache entries written.
    """
    _start = time.monotonic()
    contracts = list(
        TrackedContract.objects.values("contract_id", "name")
    )
    total = len(contracts)
    logger.info(
        "warm_contract_name_cache: warming %d contract name entries (TTL=%ds)",
        total,
        CONTRACT_NAME_CACHE_TTL,
        extra={"contract_count": total, "ttl_seconds": CONTRACT_NAME_CACHE_TTL},
    )
    for entry in contracts:
        cache.set(
            contract_name_cache_key(entry["contract_id"]),
            entry["name"],
            timeout=CONTRACT_NAME_CACHE_TTL,
        )
    elapsed = time.monotonic() - _start
    logger.info(
        "warm_contract_name_cache: completed — %d entries warmed in %.3fs",
        total,
        elapsed,
        extra={
            "contract_count": total,
            "elapsed_seconds": round(elapsed, 3),
        },
    )
    return total


@shared_task
def cleanup_old_dedup_logs(dry_run: bool = False) -> int:
    """
    Prune ``EventDeduplicationLog`` entries older than the configured retention period (TTL cleanup).

    Args:
        dry_run: If True, calculate count but don't delete records.

    Returns:
        Number of records that were (or would be) deleted.
    """
    from django.conf import settings
    from .models import EventDeduplicationLog

    _start = time.monotonic()
    retention_days = getattr(settings, "DEDUP_LOG_RETENTION_DAYS", 90)
    cutoff = timezone.now() - timedelta(days=retention_days)

    # Get the count of records that would be deleted
    records_to_delete = EventDeduplicationLog.objects.filter(created_at__lt=cutoff)
    deleted_count = records_to_delete.count()

    if not dry_run:
        # Actually delete the records
        deleted_count, _ = records_to_delete.delete()

    logger.info(
        "Pruned %d EventDeduplicationLog entries older than %d days (dry_run=%s)",
        deleted_count,
        retention_days,
        dry_run,
        extra={
            "deletion_count": deleted_count,
            "retention_days": retention_days,
            "dry_run": dry_run,
        },
    )
    _get_metrics().task_duration_seconds.labels(
        task_name="cleanup_old_dedup_logs"
    ).observe(time.monotonic() - _start)
    return deleted_count


@shared_task
def process_new_event(event_data: dict[str, Any]) -> None:
    """
    Process a newly indexed event and trigger webhooks.
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    contract_id = event_data.get("contract_id")
    event_type = event_data.get("event_type")

    if not contract_id:
        logger.warning("Event missing contract_id", extra={})
        return

    channel_layer = get_channel_layer()
    if channel_layer:
        try:
            async_to_sync(channel_layer.group_send)(
                f"events_{contract_id}",
                {
                    "type": "contract_event",
                    "data": event_data,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to publish event to channel layer: %s",
                e,
                extra={"contract_id": contract_id},
            )

    webhooks = WebhookSubscription.objects.filter(
        contract__contract_id=contract_id,
        is_active=True,
        status=WebhookSubscription.STATUS_ACTIVE,
    ).filter(event_type__in=[event_type, ""])

    # CDC streaming should not depend on webhook subscriptions.
    producer = get_producer()
    if producer:
        try:
            producer.publish(contract_id, event_data)
        except Exception:
            logger.exception(
                "Failed to stream event to backend", extra={"contract_id": contract_id}
            )

    if not webhooks.exists():
        logger.info(
            "No active webhooks for contract %s event_type %s",
            contract_id,
            event_type,
            extra={"contract_id": contract_id},
        )
        return

    ledger = event_data.get("ledger")
    event_index = event_data.get("event_index", 0)
    event_obj = None
    if ledger is not None:
        try:
            event_obj = ContractEvent.objects.get(
                contract__contract_id=contract_id,
                ledger=ledger,
                event_index=event_index,
            )
        except ContractEvent.DoesNotExist:
            logger.warning(
                "ContractEvent not found for contract=%s ledger=%s index=%s — skipping webhook dispatch",
                contract_id,
                ledger,
                event_index,
                extra={"contract_id": contract_id},
            )
            return

    if event_obj is None:
        logger.warning(
            "No ledger/event_index in event_data — cannot dispatch webhooks",
            extra={"contract_id": contract_id},
        )
        return

    if not is_event_deliverable(event_obj):
        logger.info(
            "Skipping webhook dispatch for orphaned event ledger=%s index=%s",
            event_obj.ledger,
            event_obj.event_index,
            extra={"contract_id": contract_id},
        )
        return

    dispatched = 0
    for webhook in webhooks:
        if webhook.filter_condition:
            event_context = {
                "contract_id": event_obj.contract.contract_id,
                "event_type": event_obj.event_type,
                "payload": event_obj.payload,
                "decodedPayload": event_obj.decoded_payload or {},
                "ledger": event_obj.ledger,
                "event_index": event_obj.event_index,
                "tx_hash": event_obj.tx_hash,
            }
            if not evaluate_condition(webhook.filter_condition, event_context):
                continue
        dispatch_webhook.delay(webhook.id, event_obj.id)
        dispatched += 1

    # Evaluate alert rules asynchronously (separate queue, non-blocking)
    evaluate_alert_rules.apply_async(args=[event_obj.id], queue="default")

    logger.info(
        "Dispatched event to %s webhooks",
        dispatched,
        extra={"contract_id": contract_id},
    )


@shared_task(name="ingest.tasks.analyze_contract_dependencies")
def analyze_contract_dependencies() -> dict[str, int]:
    """
    Incremental analysis task: scans recent ContractInvocation records
    to identify contract-to-contract dependencies.
    """
    _start = time.monotonic()
    m = _get_metrics()

    # We only care about invocations where the caller is a contract (starts with 'C')
    # and the target contract is also tracked.
    invocations = ContractInvocation.objects.filter(
        caller__startswith="C"
    ).select_related("contract")

    dependencies_created = 0
    dependencies_updated = 0

    for invocation in invocations:
        # Check if caller is a tracked contract
        caller_contract = get_cached_contract(invocation.caller)
        if not caller_contract:
            raise TrackedContract.DoesNotExist()
            # Caller is a contract but not tracked by us — skip
            continue

        # Found a dependency: caller_contract -> invocation.contract
        dependency, created = ContractDependency.objects.get_or_create(
            caller=caller_contract,
            callee=invocation.contract,
            defaults={"call_count": 1},
        )

        if created:
            dependencies_created += 1
        else:
            dependency.call_count += 1
            dependency.save(update_fields=["call_count", "last_call"])
            dependencies_updated += 1

    duration = time.monotonic() - _start
    m.task_duration_seconds.labels(task_name="analyze_contract_dependencies").observe(
        duration
    )

    logger.info(
        "Analyzed contract dependencies: created=%d, updated=%d in %.2fs",
        dependencies_created,
        dependencies_updated,
        duration,
    )

    return {
        "created": dependencies_created,
        "updated": dependencies_updated,
        "duration_s": duration,
    }


@shared_task(name="ingest.tasks.recompute_call_graph")
def recompute_call_graph(contract_id: str | None = None) -> bool:
    """
    Periodic task: builds the interaction DAG, detects cycles, and caches it.
    Re-computes every hour (scheduled via Celery Beat).
    """
    _start = time.monotonic()

    # Get all dependencies
    deps = ContractDependency.objects.select_related("caller", "callee").all()
    if contract_id:
        # If specific contract requested, we might want to filter,
        # but the DAG usually needs full context.
        pass

    # Build adjacency list
    adj = {}
    nodes = set()
    for dep in deps:
        caller_id = dep.caller.contract_id
        callee_id = dep.callee.contract_id
        nodes.add(caller_id)
        nodes.add(callee_id)
        if caller_id not in adj:
            adj[caller_id] = []
        adj[caller_id].append(callee_id)

    # Simple DFS for cycle detection
    visited = set()
    stack = set()
    cycles = []

    def find_cycles(u):
        visited.add(u)
        stack.add(u)
        for v in adj.get(u, []):
            if v not in visited:
                if find_cycles(v):
                    return True
            elif v in stack:
                cycles.append(v)
                return True
        stack.remove(u)
        return False

    has_cycles = False
    for node in nodes:
        if node not in visited:
            if find_cycles(node):
                has_cycles = True

    # Prepare graph data for JSON storage
    max_call_count = max((d.call_count for d in deps), default=1)
    cycle_nodes = set(cycles)

    # Update edge-level dependency risk score.
    for dep in deps:
        normalized_weight = dep.call_count / max_call_count
        cycle_bonus = 0.25 if dep.caller.contract_id in cycle_nodes else 0.0
        dep.risk_score = round(min(1.0, normalized_weight + cycle_bonus) * 100.0, 2)
        dep.save(update_fields=["risk_score", "last_call"])

    graph_data = {
        "nodes": [{"id": n, "label": n[:8]} for n in nodes],
        "edges": [
            {
                "from": d.caller.contract_id,
                "to": d.callee.contract_id,
                "weight": d.call_count,
                "risk_score": d.risk_score,
            }
            for d in deps
        ],
    }

    # Update cache
    root_contract = None
    if contract_id:
        root_contract = get_cached_contract(contract_id)

    CallGraph.objects.update_or_create(
        contract=root_contract,
        defaults={
            "graph_data": graph_data,
            "has_cycles": has_cycles,
            "cycle_details": cycles if has_cycles else None,
        },
    )

    logger.info(
        "Recomputed call graph: nodes=%d, edges=%d, has_cycles=%s",
        len(nodes),
        len(deps),
        has_cycles,
    )

    return True


def _impact_level_for_score(score: float) -> str:
    if score >= 80:
        return DependencyImpactAssessment.IMPACT_CRITICAL
    if score >= 50:
        return DependencyImpactAssessment.IMPACT_HIGH
    if score >= 20:
        return DependencyImpactAssessment.IMPACT_MEDIUM
    return DependencyImpactAssessment.IMPACT_LOW


@shared_task(name="ingest.tasks.assess_vulnerability_impact")
def assess_vulnerability_impact(contract_id: str) -> dict[str, Any]:
    """
    Assess blast radius for a potentially exploited contract.

    Returns downstream impacted contracts, cycle participation, and risk score.
    """
    try:
        root_contract = get_cached_contract(contract_id)
        if not root_contract:
            raise TrackedContract.DoesNotExist()
    except TrackedContract.DoesNotExist:
        return {
            "contract_id": contract_id,
            "affected_contracts": [],
            "impacted_count": 0,
            "risk_score": 0.0,
            "impact_level": DependencyImpactAssessment.IMPACT_LOW,
            "has_cycles": False,
        }

    deps = ContractDependency.objects.select_related("caller", "callee").all()
    adj: dict[str, list[ContractDependency]] = {}
    for dep in deps:
        adj.setdefault(dep.caller.contract_id, []).append(dep)

    visited: set[str] = set()
    queue: list[str] = [contract_id]
    downstream: list[str] = []
    cumulative_weight = 0
    has_cycle = False

    while queue:
        node = queue.pop(0)
        for dep in adj.get(node, []):
            target = dep.callee.contract_id
            cumulative_weight += max(dep.call_count, 1)
            if target == contract_id:
                has_cycle = True
            if target in visited or target == contract_id:
                continue
            visited.add(target)
            downstream.append(target)
            queue.append(target)

    impacted_count = len(downstream)
    graph = CallGraph.objects.filter(contract=None).first()
    if graph and graph.has_cycles:
        cycle_details = graph.cycle_details or []
        if isinstance(cycle_details, list) and contract_id in cycle_details:
            has_cycle = True

    # Score increases with breadth (impacted contracts), call weight, and cycles.
    raw_score = min(100.0, impacted_count * 12.0 + cumulative_weight * 0.25 + (20.0 if has_cycle else 0.0))
    risk_score = round(raw_score, 2)
    impact_level = _impact_level_for_score(risk_score)

    assessment_payload = {
        "contract_id": contract_id,
        "affected_contracts": downstream,
        "impacted_count": impacted_count,
        "risk_score": risk_score,
        "impact_level": impact_level,
        "has_cycles": has_cycle,
    }

    DependencyImpactAssessment.objects.update_or_create(
        root_contract=root_contract,
        defaults={
            "affected_contracts": downstream,
            "impacted_count": impacted_count,
            "has_cycles": has_cycle,
            "risk_score": risk_score,
            "impact_level": impact_level,
            "assessment_details": {
                "cumulative_call_weight": cumulative_weight,
            },
        },
    )

    return assessment_payload


@shared_task(name="ingest.tasks.alert_downstream_contract_change")
def alert_downstream_contract_change(contract_id: str, change_type: str = "modified") -> int:
    """
    Notify dependent contract owners when an upstream dependency changes.
    """
    from .services.notifications import create_and_push

    changed_contract = get_cached_contract(contract_id)
    if not changed_contract:
        return 0

    dependents = ContractDependency.objects.select_related("caller", "callee", "caller__owner").filter(
        callee=changed_contract
    )

    notified = 0
    dedup_ttl = int(getattr(settings, "DOWNSTREAM_ALERT_DEDUP_SECONDS", 3600))
    for dep in dependents:
        cache_key = f"soroscan:dependency_change:{dep.caller_id}:{dep.callee_id}:{change_type}"
        if not cache.add(cache_key, "1", timeout=dedup_ttl):
            continue
        create_and_push(
            user=dep.caller.owner,
            notification_type="alert",
            title="Dependency Change Detected",
            message=(
                f"Dependency contract '{changed_contract.name}' ({changed_contract.contract_id}) "
                f"was {change_type}. This may impact '{dep.caller.name}'."
            ),
            link=f"/contracts/{dep.caller.contract_id}",
        )
        notified += 1

    return notified


@shared_task(name="ingest.tasks.ingest_latest_events", soft_time_limit=120)
def ingest_latest_events() -> int:
    """
    Sync events from Horizon/Soroban RPC.
    """
    _start = time.monotonic()
    m = _get_metrics()

    cursor_state, _ = IndexerState.objects.get_or_create(
        key="horizon_cursor",
        defaults={"value": "now"},
    )
    cursor = cursor_state.value
    server = SorobanServer(settings.SOROBAN_RPC_URL)
    new_events = 0

    try:
        try:
            reorg_result = check_and_handle_reorg(server)
            if reorg_result:
                logger.warning(
                    "Handled ledger re-org rollback: %s",
                    reorg_result,
                    extra={"ledger_sequence": reorg_result.get("from_ledger")},
                )
        except Exception:
            logger.exception(
                "Ledger re-org check failed — continuing with event ingestion",
                extra={},
            )

        blacklisted_ids = set(
            BlacklistedContract.objects.values_list("contract_id", flat=True)
        )
        all_active_ids = list(
            TrackedContract.objects.filter(is_active=True, is_paused=False).values_list(
                "contract_id", flat=True
            )
        )
        for cid in all_active_ids:
            if cid in blacklisted_ids:
                logger.info(
                    "Skipping blacklisted contract %s — not indexing events",
                    cid,
                    extra={"contract_id": cid, "reason": "blacklisted"},
                )
        contract_ids = [cid for cid in all_active_ids if cid not in blacklisted_ids]

        # Always update the gauge, even when there are no active contracts.
        m.active_contracts_gauge.set(len(contract_ids))

        if not contract_ids:
            logger.info("No active contracts to index", extra={})
            return 0

        events_response = execute_with_circuit_breaker(
            "horizon",
            server.get_events,
            start_ledger=int(cursor) if cursor.isdigit() else None,
            filters=[
                {
                    "type": "contract",
                    "contractIds": contract_ids,
                }
            ],
            pagination={"limit": 100},
        )

        network = _network_label()
        # Track distinct ledger sequences visited in this poll.
        scanned_ledgers: set[int] = set()
        client = None

        for fallback_event_index, event in enumerate(events_response.events):
            scanned_ledgers.add(getattr(event, "ledger", 0))
            try:
                contract = get_cached_contract(event.contract_id)
                if not contract:
                    raise TrackedContract.DoesNotExist()
            except TrackedContract.DoesNotExist:
                m.events_skipped_total.labels(
                    contract_id=_short_contract_id(
                        getattr(event, "contract_id", "") or ""
                    ),
                    network=network,
                    reason="no_contract",
                ).inc()
                continue

            # Check rate limit before processing
            if not check_ingest_rate(contract):
                m.events_rate_limited_total.labels(
                    contract_id=_short_contract_id(contract.contract_id),
                    network=network,
                ).inc()
                logger.warning(
                    "Rate limit exceeded for contract %s — skipping event",
                    contract.contract_id,
                    extra={"contract_id": contract.contract_id},
                )
                continue

            # Check whitelist/blacklist filter before persisting
            if not contract.should_ingest_event(event.type):
                m.events_filtered_total.labels(
                    contract_id=_short_contract_id(contract.contract_id),
                    network=network,
                    filter_type=contract.event_filter_type,
                    event_type=event.type,
                ).inc()
                logger.debug(
                    "Event type '%s' filtered (%s) for contract %s — skipping",
                    event.type,
                    contract.event_filter_type,
                    contract.contract_id,
                    extra={
                        "contract_id": contract.contract_id,
                        "event_type": event.type,
                    },
                )
                continue

            payload = event.value

            if not validate_contract_payload_schema(
                contract,
                payload,
                event.type,
                ledger=event.ledger,
            ):
                m.events_validation_failures_total.labels(
                    contract_id=_short_contract_id(contract.contract_id),
                    network=network,
                ).inc()
                continue

            passed, version_used = validate_event_payload(
                contract, event.type, payload, ledger=event.ledger
            )
            validation_status = "passed" if passed else "failed"
            schema_version = version_used
            # Emit validation counter immediately after the decision.
            m.events_validated_total.labels(
                status=validation_status,
                network=network,
            ).inc()
            signature_status = resolve_signature_status(
                contract,
                event,
                payload,
            )

            # --- ContractInvocation tracking (issue #X) ---
            # Fetch or create the invocation record for this transaction
            invocation_record = None
            try:
                # Use cached client if available, or create new one
                if client is None:
                    client = SorobanClient()

                invocation_data = client.get_invocation(event.tx_hash)
                if invocation_data.success:
                    invocation_record, _ = ContractInvocation.objects.get_or_create(
                        tx_hash=event.tx_hash,
                        contract=contract,
                        defaults={
                            "caller": invocation_data.caller,
                            "function_name": invocation_data.function_name,
                            "parameters": invocation_data.parameters,
                            "result": invocation_data.result,
                            "ledger_sequence": event.ledger,
                        },
                    )
            except Exception:
                logger.warning(
                    "Failed to create invocation record for tx=%s",
                    event.tx_hash,
                    exc_info=True,
                )

            event_record, created = ContractEvent.objects.get_or_create(
                tx_hash=event.tx_hash,
                ledger=event.ledger,
                event_type=event.type,
                defaults={
                    "contract": contract,
                    "payload": payload,
                    "timestamp": timezone.now(),
                    "raw_xdr": event.xdr if hasattr(event, "xdr") else "",
                    "validation_status": validation_status,
                    "schema_version": schema_version,
                    "signature_status": signature_status,
                    "invocation": invocation_record,
                },
            )

            # Update validation status if needed
            if not created:
                if (
                    event_record.validation_status != validation_status
                    or event_record.schema_version != schema_version
                    or event_record.signature_status != signature_status
                ):
                    event_record.validation_status = validation_status
                    event_record.schema_version = schema_version
                    event_record.signature_status = signature_status
                    event_record.save(
                        update_fields=[
                            "validation_status",
                            "schema_version",
                            "signature_status",
                        ]
                    )

            if created:
                new_events += 1
                m.events_ingested_total.labels(
                    contract_id=_short_contract_id(contract.contract_id),
                    network=network,
                    event_type=event_record.event_type,
                ).inc()
                process_new_event.delay(
                    {
                        "contract_id": contract.contract_id,
                        "event_type": event_record.event_type,
                        "payload": event_record.payload,
                        "ledger": event_record.ledger,
                        "event_index": event_record.event_index,
                        "tx_hash": event_record.tx_hash,
                    }
                )

            if (
                contract.last_indexed_ledger is None
                or event_record.ledger > contract.last_indexed_ledger
            ):
                if (
                    contract.last_indexed_ledger is not None
                    and event_record.ledger > contract.last_indexed_ledger + 1
                ):
                    _get_metrics().ledger_gaps_total.labels(
                        contract_id=_short_contract_id(contract.contract_id)
                    ).inc()
                    _get_metrics().missing_events_total.labels(
                        contract_id=_short_contract_id(contract.contract_id)
                    ).inc(event_record.ledger - contract.last_indexed_ledger - 1)
                contract.last_indexed_ledger = event_record.ledger
                contract.save(update_fields=["last_indexed_ledger"])

        if scanned_ledgers:
            m.ledgers_scanned_total.labels(network=network).inc(len(scanned_ledgers))

        # Trigger incremental dependency analysis if new events were processed
        if new_events > 0:
            analyze_contract_dependencies.delay()

        last_ledger = None
        if events_response.events:
            last_ledger = events_response.events[-1].ledger
            cursor_state.value = str(last_ledger)
            cursor_state.save()

        logger.info(
            "Indexed %s new events",
            new_events,
            extra={"ledger_sequence": last_ledger},
        )

    except Exception:
        logger.exception("Failed to sync events from Horizon", extra={})
        m.ingest_errors_total.labels(
            task_name="sync_events_from_horizon",
            error_type="exception",
        ).inc()

    finally:
        # Always record duration, even if an exception occurred.
        elapsed = time.monotonic() - _start
        m.task_duration_seconds.labels(task_name="ingest_latest_events").observe(
            elapsed
        )
        
        # Update event ingestion rate gauge (events/sec)
        if elapsed > 0:
            rate = new_events / elapsed
            m.event_ingestion_rate_gauge.set(rate)

    return new_events


@shared_task(name="ingest.tasks.aggregate_event_statistics", soft_time_limit=180)
def aggregate_event_statistics() -> dict[str, Any]:
    """
    Hourly task: aggregate ContractEvent rows from the last hour into
    EventAggregation pre-computed buckets and run anomaly detection.

    Strategy
    --------
    1. Determine the current 1-hour bucket (timestamp rounded down to :00:00).
    2. Query ContractEvent for that bucket grouped by (contract, event_type).
    3. Upsert EventAggregation rows (update_or_create on unique_together key).
    4. Also upsert a per-contract *total* bucket (event_type='').
    5. Compare each new bucket against the 7-day rolling average for the same
       hour-of-week slot.  Flag as anomaly when the count drops by more than
       ANALYTICS_ANOMALY_DROP_PCT % (default 50 %) and the baseline is >= MIN.
    6. Fire a Notification for the contract owner when an anomaly is detected.

    Constraints
    -----------
    - Runs on the low_priority Celery queue.
    - Completed in < 5 seconds even with thousands of contracts because it
      uses a single GROUP BY query, not per-contract loops.
    """
    from .models import EventAggregation  # noqa: PLC0415

    _start = time.monotonic()
    m = _get_metrics()

    now = timezone.now()
    # Bucket = the most recently *completed* hour (standard for scheduled aggregations)
    # e.g. if now = 16:35, bucket covers 15:00–16:00
    bucket_end = now.replace(minute=0, second=0, microsecond=0)
    bucket_start = bucket_end - timedelta(hours=1)

    # ── 1. Aggregate last-hour events by (contract, event_type) ──────────────
    raw_aggs = (
        ContractEvent.objects.filter(
            timestamp__gte=bucket_start,
            timestamp__lt=bucket_end,
        )
        .values("contract_id", "event_type")
        .annotate(count=Count("id"))
    )

    # Accumulate per-contract totals while iterating
    contract_totals: dict[int, int] = {}
    per_type_rows: list[dict] = []

    for row in raw_aggs:
        cid = row["contract_id"]
        contract_totals[cid] = contract_totals.get(cid, 0) + row["count"]
        per_type_rows.append(row)

    # Add synthetic total buckets (event_type='')
    for contract_pk, total in contract_totals.items():
        per_type_rows.append(
            {"contract_id": contract_pk, "event_type": "", "count": total}
        )

    # ── 2. Upsert aggregation rows ────────────────────────────────────────────
    anomaly_drop_pct = int(getattr(settings, "ANALYTICS_ANOMALY_DROP_PCT", 50))
    anomaly_min_baseline = int(getattr(settings, "ANALYTICS_ANOMALY_MIN_BASELINE", 10))

    upserted = 0
    anomalies: list[int] = []  # contract_id list

    # Pre-compute 7-day rolling average for each (contract, event_type) for the
    # same hour-of-day slot so we can do anomaly detection in one pass.
    # We look back 7 × 24 hours and average across matching hour-of-day buckets.
    rolling_lookback_start = bucket_start - timedelta(days=7)
    rolling_map: dict[tuple, float] = {}
    for rolling_row in (
        EventAggregation.objects.filter(
            timestamp__gte=rolling_lookback_start,
            timestamp__lt=bucket_start,
            timestamp__hour=bucket_start.hour,
        )
        .values("contract_id", "event_type")
        .annotate(avg_count=Avg("event_count"))
    ):
        rolling_map[(rolling_row["contract_id"], rolling_row["event_type"])] = (
            rolling_row["avg_count"] or 0.0
        )

    for row in per_type_rows:
        contract_pk: int = row["contract_id"]
        event_type: str = row["event_type"]
        count: int = row["count"]

        rolling_avg = rolling_map.get((contract_pk, event_type), 0.0)
        is_anomaly = False
        if (
            rolling_avg >= anomaly_min_baseline
            and count < rolling_avg * (1 - anomaly_drop_pct / 100.0)
        ):
            is_anomaly = True
            if event_type == "":  # fire alert only on the per-contract total
                anomalies.append(contract_pk)

        EventAggregation.objects.update_or_create(
            contract_id=contract_pk,
            event_type=event_type,
            timestamp=bucket_start,
            defaults={"event_count": count, "is_anomaly": is_anomaly},
        )
        upserted += 1

    # ── 3. Fire anomaly alerts ────────────────────────────────────────────────
    if anomalies:
        _fire_volume_anomaly_alerts(anomalies, bucket_start, rolling_map, anomaly_drop_pct)

    # ── 4. Metrics + summary ──────────────────────────────────────────────────
    elapsed = time.monotonic() - _start
    m.task_duration_seconds.labels(task_name="aggregate_event_statistics").observe(elapsed)

    total_events = ContractEvent.objects.count()
    active_contracts = TrackedContract.objects.filter(is_active=True).count()

    summary = {
        "bucket_start": bucket_start.isoformat(),
        "upserted": upserted,
        "anomalies": len(anomalies),
        "total_events": total_events,
        "active_contracts": active_contracts,
        "elapsed_seconds": round(elapsed, 3),
        "timestamp": now.isoformat(),
    }

    logger.info(
        "aggregate_event_statistics complete: upserted=%d anomalies=%d elapsed=%.3fs",
        upserted,
        len(anomalies),
        elapsed,
        extra=summary,
    )
    return summary


def _fire_volume_anomaly_alerts(
    contract_pks: list[int],
    bucket_start,
    rolling_map: dict,
    anomaly_drop_pct: int,
) -> None:
    """Create in-app Notifications for contract owners on volume-drop anomalies."""
    from .models import Notification, TrackedContract  # noqa: PLC0415
    from .services.notifications import create_and_push  # noqa: PLC0415

    contracts = TrackedContract.objects.filter(pk__in=contract_pks).select_related("owner")
    for contract in contracts:
        rolling_avg = rolling_map.get((contract.pk, ""), 0.0)
        title = f"Event volume anomaly: {contract.name}"
        message = (
            f"Event volume for {contract.contract_id[:8]}… dropped by >{anomaly_drop_pct}% "
            f"at {bucket_start:%Y-%m-%d %H:00 UTC}. "
            f"Rolling avg: {rolling_avg:.1f} req/hr."
        )
        try:
            create_and_push(
                user=contract.owner,
                notification_type=Notification.NotificationType.ALERT,
                title=title,
                message=message,
                link=f"/contracts/{contract.contract_id}/analytics/",
            )
        except Exception:
            logger.exception(
                "Failed to send anomaly notification for contract %s",
                contract.contract_id,
            )


@shared_task(name="ingest.tasks.warm_event_count_cache")
def warm_event_count_cache() -> dict[str, Any]:
    """
    Periodically warm cache with frequently accessed contract event counts (issue #587).
    
    This task proactively caches event counts for active contracts to improve
    cache hit rates and reduce database load for frequently accessed data.
    """
    _start = time.monotonic()
    from .cache_utils import get_event_count
    
    # Get all active contracts ordered by last activity (most recent first)
    active_contracts = TrackedContract.objects.filter(
        is_active=True
    ).order_by('-last_event_at')[:100]  # Warm top 100 most active contracts
    
    warmed_count = 0
    for contract in active_contracts:
        try:
            # Call get_event_count which will cache the result
            count = get_event_count(contract.contract_id)
            warmed_count += 1
            logger.debug(
                "Warmed cache for contract %s: %d events",
                contract.contract_id,
                count,
                extra={"contract_id": contract.contract_id, "event_count": count},
            )
        except Exception as exc:
            logger.warning(
                "Failed to warm cache for contract %s: %s",
                contract.contract_id,
                exc,
                extra={"contract_id": contract.contract_id},
            )
    
    elapsed = time.monotonic() - _start
    logger.info(
        "Cache warming completed: %d contracts processed in %.2fs",
        warmed_count,
        elapsed,
        extra={"contracts_warmed": warmed_count, "duration_seconds": round(elapsed, 3)},
    )
    
    m = _get_metrics()
    m.task_duration_seconds.labels(task_name="warm_event_count_cache").observe(elapsed)
    
    return {
        "contracts_warmed": warmed_count,
        "duration_seconds": round(elapsed, 3),
        "timestamp": timezone.now().isoformat(),
    }


@shared_task(name="ingest.tasks.log_daily_platform_stats")
def log_daily_platform_stats() -> dict[str, Any]:
    """
    Log platform usage stats for the last 24 hours.
    """
    window_end = timezone.now()
    window_start = window_end - timedelta(hours=24)

    total_events = ContractEvent.objects.filter(
        timestamp__gte=window_start,
        timestamp__lt=window_end,
    ).count()
    new_contracts = TrackedContract.objects.filter(
        created_at__gte=window_start,
        created_at__lt=window_end,
    ).count()

    logger.info(
        "Daily platform stats for %s to %s: %d events ingested, %d contracts registered",
        window_start.isoformat(),
        window_end.isoformat(),
        total_events,
        new_contracts,
        extra={
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "total_events_ingested": total_events,
            "new_contracts_registered": new_contracts,
        },
    )

    return {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "total_events_ingested": total_events,
        "new_contracts_registered": new_contracts,
    }


@shared_task(name="ingest.tasks.reconcile_event_completeness")
def reconcile_event_completeness() -> dict[str, Any]:
    """
    Detect ledger gaps, record completeness, and trigger backfill repairs.
    """
    _start = time.monotonic()
    m = _get_metrics()
    summaries: list[dict[str, Any]] = []
    repair_jobs = 0

    for contract in TrackedContract.objects.filter(is_active=True):
        summary = _calculate_completeness(contract)
        summaries.append(summary)

        IndexerState.objects.update_or_create(
            key=f"completeness:{contract.id}",
            defaults={"value": json.dumps(summary)},
        )

        if summary["missing_ledgers"] > 0:
            m.ledger_gaps_total.labels(
                contract_id=_short_contract_id(contract.contract_id)
            ).inc(len(summary["gaps"]))
            m.missing_events_total.labels(
                contract_id=_short_contract_id(contract.contract_id)
            ).inc(summary["missing_ledgers"])
            for gap in summary["gaps"][:10]:
                backfill_contract_events.delay(
                    contract.contract_id,
                    gap["from_ledger"],
                    gap["to_ledger"],
                )
                repair_jobs += 1

        if summary["completeness_percentage"] < 99.9:
            logger.warning(
                "Contract completeness dropped below SLO",
                extra={
                    "contract_id": contract.contract_id,
                    "completeness_percentage": summary["completeness_percentage"],
                },
            )

    m.task_duration_seconds.labels(task_name="reconcile_event_completeness").observe(
        time.monotonic() - _start
    )
    return {"contracts_checked": len(summaries), "repair_jobs": repair_jobs}


@shared_task(name="ingest.tasks.snapshot_contract_state")
def snapshot_contract_state() -> dict[str, int]:
    """
    Capture contract state snapshots for active contracts at configured intervals.
    """
    from soroscan.ingest.services.contract_state import (
        create_contract_snapshot,
        should_snapshot_contract,
        snapshot_interval,
    )
    from soroscan.ingest.stellar_client import SorobanClient

    client = SorobanClient()
    interval = snapshot_interval()
    captured = 0
    skipped = 0

    for contract in TrackedContract.objects.filter(is_active=True):
        if not should_snapshot_contract(contract, interval):
            skipped += 1
            continue

        ledger = contract.last_indexed_ledger
        state = client.get_contract_state(contract.contract_id, ledger=ledger)
        create_contract_snapshot(contract, ledger, state)
        captured += 1

    return {"captured": captured, "skipped": skipped, "interval": interval}


@shared_task(bind=True, queue="backfill", max_retries=3, default_retry_delay=60, soft_time_limit=300)
def backfill_contract_events(
    self,
    contract_id: str,
    from_ledger: int,
    to_ledger: int,
) -> dict[str, Any]:
    """
    Backfill events for one contract within an inclusive ledger range.
    """
    _start = time.monotonic()
    m = _get_metrics()

    start_ledger = _safe_int(from_ledger, default=0)
    end_ledger = _safe_int(to_ledger, default=0)

    if start_ledger <= 0 or end_ledger <= 0 or start_ledger > end_ledger:
        raise ValueError("Invalid ledger range provided")

    try:
        contract = get_cached_contract(contract_id)
        if not contract:
            raise TrackedContract.DoesNotExist()
    except TrackedContract.DoesNotExist as exc:
        raise ValueError(f"Tracked contract not found: {contract_id}") from exc

    next_ledger = start_ledger
    if contract.last_indexed_ledger is not None:
        next_ledger = max(next_ledger, contract.last_indexed_ledger + 1)

    client = SorobanClient()
    processed_events = 0
    created_events = 0
    updated_events = 0

    try:
        short_cid = _short_contract_id(contract.contract_id)
        for batch_start in range(next_ledger, end_ledger + 1, BATCH_LEDGER_SIZE):
            batch_end = min(batch_start + BATCH_LEDGER_SIZE - 1, end_ledger)
            _batch_start_time = time.monotonic()
            batch_events = client.get_events_range(
                contract.contract_id, batch_start, batch_end
            )

            # Create batch_cache for this batch to avoid redundant RPC calls
            batch_cache = {}

            if not batch_events:
                logger.warning(
                    "No events returned for contract=%s ledgers=%s-%s",
                    contract.contract_id,
                    batch_start,
                    batch_end,
                )

            for fallback_event_index, event in enumerate(batch_events):
                result = _upsert_contract_event(
                    contract,
                    event,
                    fallback_event_index,
                    client=client,
                    batch_cache=batch_cache,
                )
                # Handle rate-limited events (returns None, False)
                if result[0] is None:
                    continue
                _, created = result
                processed_events += 1
                if created:
                    created_events += 1
                else:
                    updated_events += 1

            contract.last_indexed_ledger = batch_end
            contract.save(update_fields=["last_indexed_ledger"])

            # Record per-batch metrics.
            ledger_span = batch_end - batch_start + 1
            m.backfill_ledgers_processed_total.labels(contract_id=short_cid).inc(
                ledger_span
            )
            m.backfill_batch_duration_seconds.labels(contract_id=short_cid).observe(
                time.monotonic() - _batch_start_time
            )

        # Ensure gauge is fresh after a bulk backfill.
        m.active_contracts_gauge.set(
            TrackedContract.objects.filter(is_active=True).count()
        )
        return {
            "contract_id": contract.contract_id,
            "from_ledger": start_ledger,
            "to_ledger": end_ledger,
            "last_indexed_ledger": contract.last_indexed_ledger,
            "processed_events": processed_events,
            "created_events": created_events,
            "updated_events": updated_events,
        }

    except Exception as exc:
        logger.exception(
            "Backfill failed for contract=%s range=%s-%s",
            contract.contract_id,
            start_ledger,
            end_ledger,
        )
        m.ingest_errors_total.labels(
            task_name="backfill_contract_events",
            error_type=type(exc).__name__,
        ).inc()
        
        # Log retry information
        attempt_number = self.request.retries + 1
        if self.request.retries < self.max_retries:
            _log_task_retry(
                "backfill_contract_events",
                attempt_number + 1,
                type(exc).__name__,
                countdown=60,  # default_retry_delay from task decorator
            )
        
        raise self.retry(exc=exc)
    finally:
        # Always record duration, even if an exception occurred.
        m.task_duration_seconds.labels(task_name="backfill_contract_events").observe(
            time.monotonic() - _start
        )


@shared_task(bind=True, queue="backfill", soft_time_limit=300)
def reprocess_events(
    self,
    contract_id: str,
    dry_run: bool = False,
    batch_size: int = 500,
    checkpoint_id: int = 0,
    rollback_on_error: bool = True,
) -> dict[str, Any]:
    """Reprocess historical events for a contract in batches."""
    from .reprocessing import reprocess_contract_events  # noqa: PLC0415

    result = reprocess_contract_events(
        contract_id,
        dry_run=dry_run,
        batch_size=batch_size,
        checkpoint_id=checkpoint_id,
        rollback_on_error=rollback_on_error,
    )
    return {
        "contract_id": result.contract_id,
        "total_events": result.total_events,
        "processed_events": result.processed_events,
        "updated_events": result.updated_events,
        "failed_events": result.failed_events,
        "last_checkpoint_id": result.last_checkpoint_id,
        "progress_percent": result.progress_percent,
        "dry_run": result.dry_run,
        "rolled_back": result.rolled_back,
    }


# ---------------------------------------------------------------------------
# Issue: Event-driven alerts — condition evaluator and dispatch tasks
# ---------------------------------------------------------------------------


def _get_field(data: dict, dotted_path: str):
    """Traverse a dot-notation path through nested dicts."""
    current = data
    for part in dotted_path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _as_number(v):
    """Coerce a value to float for numeric comparison, or None if not numeric.

    Booleans are excluded even though ``bool`` is a subclass of ``int`` in
    Python — otherwise ``True`` would numerically equal ``1``/``"1"``.
    """
    if isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _values_equal(current, value) -> bool:
    """Compare two operands, treating numerically-equal values (e.g. the int
    ``1000``, the float ``1000.0``, and the Decimal ``1000.00`` produced by a
    model field) as equal regardless of representation. Falls back to string
    comparison for non-numeric operands.
    """
    lhs_num, rhs_num = _as_number(current), _as_number(value)
    if lhs_num is not None and rhs_num is not None:
        return lhs_num == rhs_num
    return str(current) == str(value)


def evaluate_condition(condition: dict, event_data: dict) -> bool:
    """
    Evaluate a JSON condition AST against flattened event data.

    Supported ops (case-insensitive):
      - Logical: and, or, not
            - Comparison: eq, neq, gt, gte, lt, lte, contains, startswith, in, regex
    """
    op = (condition.get("op") or "").lower()

    if op == "not":
        sub = condition.get("condition", {})
        return not evaluate_condition(sub, event_data)

    if op in ("and", "or"):
        subs = condition.get("conditions", [])
        if op == "and":
            return all(evaluate_condition(c, event_data) for c in subs)
        return any(evaluate_condition(c, event_data) for c in subs)

    # Field comparison
    field = condition.get("field", "")
    value = condition.get("value")
    current = _get_field(event_data, field)

    if op == "eq":
        return _values_equal(current, value)
    if op == "neq":
        return not _values_equal(current, value)
    if op in ("gt", "gte", "lt", "lte"):
        try:
            lhs, rhs = float(str(current)), float(str(value))
            return {
                "gt": lhs > rhs,
                "gte": lhs >= rhs,
                "lt": lhs < rhs,
                "lte": lhs <= rhs,
            }[op]
        except (TypeError, ValueError):
            return False
    if op == "contains":
        return (
            str(value).lower() in str(current).lower() if current is not None else False
        )
    if op == "startswith":
        return str(current).startswith(str(value)) if current is not None else False
    if op == "in":
        if isinstance(value, list):
            return any(_values_equal(current, item) for item in value)
        return _values_equal(current, value)
    if op == "regex":
        if current is None:
            return False
        try:
            return re.search(str(value), str(current)) is not None
        except re.error:
            return False

    logger.warning("Unknown condition op '%s' — treating as False", op)
    return False


def _alert_channel_targets(rule) -> list[tuple[str, str]]:
    """
    Build (action_type, target) pairs: multi-channel JSON or legacy single field.
    """
    raw = getattr(rule, "channels", None) or []
    if isinstance(raw, list) and len(raw) > 0:
        out: list[tuple[str, str]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            ch_type = (item.get("type") or "").strip().lower()
            target = (item.get("target") or "").strip()
            if ch_type in ("slack", "email", "webhook") and target:
                out.append((ch_type, target))
        if out:
            return out
    if rule.action_target:
        return [(rule.action_type, rule.action_target)]
    return []


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=5,
)
def send_alert(self, rule_id: int, event_id: int) -> str:
    """
    Send alert(s) for a matched AlertRule / ContractEvent pair.
    When ``channels`` is set, delivers to email, Slack, and webhook in one task
    (real-time via the existing Celery path). Retries with exponential backoff
    if any channel fails.
    """
    from django.core.cache import cache
    from .models import AlertRule, AlertExecution

    try:
        rule = AlertRule.objects.select_related("contract").get(
            id=rule_id, is_active=True
        )
    except AlertRule.DoesNotExist:
        return "skipped:rule_gone"

    try:
        event = ContractEvent.objects.select_related("contract").get(id=event_id)
    except ContractEvent.DoesNotExist:
        return "skipped:event_gone"

    payload = {
        "rule": rule.name,
        "contract": event.contract.contract_id,
        "event_type": event.event_type,
        "payload": event.payload,
        "ledger": event.ledger,
        "timestamp": event.timestamp.isoformat(),
    }

    # Deduplicate identical alerts for a short window to prevent floods.
    dedup_window = int(getattr(settings, "ALERT_DEDUP_WINDOW_SECONDS", 300))
    dedup_material = json.dumps(
        {
            "rule_id": rule.id,
            "contract": payload["contract"],
            "event_type": payload["event_type"],
            "ledger": payload["ledger"],
            "payload": payload["payload"],
        },
        sort_keys=True,
    )
    dedup_hash = hashlib.sha256(dedup_material.encode("utf-8")).hexdigest()
    dedup_key = f"soroscan:alerts:dedup:{rule.id}:{dedup_hash}"
    if not cache.add(dedup_key, "1", timeout=dedup_window):
        _get_metrics().alert_deduplicated_total.labels(scope="alert_rule").inc()
        logger.info(
            "Deduplicated alert for rule=%s event=%s",
            rule.id,
            event.id,
            extra={"rule_id": rule.id, "event_id": event.id},
        )
        return "skipped:deduplicated"

    targets = _alert_channel_targets(rule)
    if not targets:
        logger.warning(
            "Alert rule %s has no channels or action_target",
            rule_id,
            extra={"rule_id": rule_id, "event_id": event_id},
        )
        return "skipped:no_targets"

    successes = 0
    failures: list[Exception] = []

    for action_type, target in targets:
        try:
            if action_type == "slack":
                _send_slack_alert(target, payload)
            elif action_type == "email":
                _send_email_alert(target, rule.name, payload)
            elif action_type == "webhook":
                _send_webhook_alert(target, payload)
            else:
                raise ValueError(f"Unknown action_type: {action_type}")
            AlertExecution.objects.create(
                rule=rule,
                event=event,
                status="sent",
                response="ok",
                channel=action_type,
            )
            successes += 1
        except Exception as exc:
            failures.append(exc)
            AlertExecution.objects.create(
                rule=rule,
                event=event,
                status="failed",
                response=str(exc)[:500],
                channel=action_type,
            )

    if successes:
        logger.info(
            "Alert '%s': %d/%d channel(s) ok for event %s",
            rule.name,
            successes,
            len(targets),
            event_id,
            extra={"rule_id": rule_id, "event_id": event_id},
        )

    if failures and successes == 0:
        err = failures[0]
        logger.warning(
            "Alert '%s' all channels failed (attempt %d): %s",
            rule.name,
            self.request.retries + 1,
            err,
            extra={"rule_id": rule_id, "event_id": event_id},
        )
        raise err

    if failures:
        logger.warning(
            "Alert '%s' partial failure: %s",
            rule.name,
            failures[0],
            extra={"rule_id": rule_id, "event_id": event_id},
        )

    return "sent" if successes else "failed"


def _send_slack_alert(channel_or_url: str, payload: dict) -> None:
    from django.conf import settings

    text = (
        f"*SoroScan Alert: {payload['rule']}*\n"
        f"Contract: `{payload['contract']}`\n"
        f"Event: `{payload['event_type']}` @ ledger {payload['ledger']}\n"
        f"```{json.dumps(payload['payload'], indent=2)[:800]}```"
    )
    timeout = getattr(settings, "SLACK_ALERT_TIMEOUT_SECONDS", 10)
    resp = requests.post(
        channel_or_url,
        json={"text": text},
        timeout=timeout,
    )
    resp.raise_for_status()


def _send_email_alert(to_addr: str, rule_name: str, payload: dict) -> None:
    from django.core.mail import send_mail

    subject = f"[SoroScan] Alert: {rule_name}"
    body = (
        f"Alert rule '{rule_name}' was triggered.\n\n"
        f"Contract:   {payload['contract']}\n"
        f"Event type: {payload['event_type']}\n"
        f"Ledger:     {payload['ledger']}\n"
        f"Timestamp:  {payload['timestamp']}\n\n"
        f"Payload:\n{json.dumps(payload['payload'], indent=2)}"
    )
    send_mail(
        subject=subject,
        message=body,
        from_email=None,  # uses DEFAULT_FROM_EMAIL
        recipient_list=[to_addr],
        fail_silently=False,
    )


def _send_webhook_alert(url: str, payload: dict) -> None:
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()


@shared_task
def evaluate_alert_rules(event_id: int) -> int:
    """
    Check all active AlertRules for the contract that owns *event_id*.
    Dispatches ``send_alert`` tasks for every matching rule.
    Returns the number of rules that matched.
    """
    from .models import AlertRule

    try:
        event = ContractEvent.objects.select_related("contract").get(id=event_id)
    except ContractEvent.DoesNotExist:
        return 0

    rules = AlertRule.objects.filter(
        contract=event.contract,
        is_active=True,
    ).order_by(
        "id"
    )[: AlertRule.MAX_RULES_PER_CONTRACT]

    event_data = {
        "event_type": event.event_type,
        "ledger": event.ledger,
        "payload": event.payload or {},
        # Flatten payload fields under decodedPayload for AST compatibility
        "decodedPayload": event.payload or {},
    }

    m = _get_metrics()
    matched = 0
    no_match = 0
    for rule in rules:
        try:
            if evaluate_condition(rule.condition, event_data):
                # Fire-and-forget; exponential backoff handled inside send_alert
                send_alert.apply_async(
                    args=[rule.id, event_id],
                    queue="default",
                )
                matched += 1
                m.alert_rules_evaluated_total.labels(outcome="matched").inc()
            else:
                no_match += 1
                m.alert_rules_evaluated_total.labels(outcome="no_match").inc()
        except Exception:
            logger.exception(
                "Error evaluating condition for rule %s",
                rule.id,
                extra={"rule_id": rule.id},
            )

    return matched


def _month_start(value: date | None = None) -> date:
    base = value or timezone.now().date()
    return date(base.year, base.month, 1)


def _month_end(value: date | None = None) -> date:
    start = _month_start(value)
    _, days = calendar.monthrange(start.year, start.month)
    return date(start.year, start.month, days)


def _decimal(value: float | int | Decimal) -> Decimal:
    return Decimal(str(value))


def _round_cost(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _cost_pricing() -> dict[str, Decimal]:
    return {
        "rpc_per_call": _decimal(getattr(settings, "COST_RPC_PER_CALL_USD", "0.00001")),
        "storage_per_gb": _decimal(getattr(settings, "COST_STORAGE_PER_GB_USD", "0.10")),
        "compute_per_unit": _decimal(getattr(settings, "COST_COMPUTE_PER_UNIT_USD", "0.00002")),
    }


def _emit_budget_alerts(
    org: Organization,
    snapshot: OrganizationCostSnapshot,
    budget: OrganizationBudget,
) -> int:
    from .services.notifications import create_and_push

    if not budget.is_active or budget.monthly_budget_usd <= 0:
        return 0

    projected = _decimal(snapshot.projected_monthly_cost_usd)
    budget_amount = _decimal(budget.monthly_budget_usd)
    utilization = (projected / budget_amount * Decimal("100")) if budget_amount > 0 else Decimal("0")
    month_tag = snapshot.month.strftime("%Y-%m")

    thresholds = [
        (budget.warning_threshold_percent, "warning"),
        (budget.critical_threshold_percent, "critical"),
    ]
    sent = 0
    for threshold, level in thresholds:
        if utilization < _decimal(threshold):
            continue
        dedup_key = f"soroscan:budget_alert:{org.id}:{month_tag}:{threshold}"
        if not cache.add(dedup_key, "1", timeout=3600):
            continue
        create_and_push(
            user=org.owner,
            notification_type="alert",
            title=f"Budget {level.title()} Threshold Reached",
            message=(
                f"Projected monthly cost is ${snapshot.projected_monthly_cost_usd} "
                f"({utilization.quantize(Decimal('0.01'))}%) for organization '{org.name}'."
            ),
            link="/admin/ingest/organizationcostsnapshot/",
        )
        sent += 1
    return sent


@shared_task(name="ingest.tasks.aggregate_organization_costs")
def aggregate_organization_costs(month: str | None = None) -> dict[str, Any]:
    """
    Aggregate organization usage into monthly cost snapshots and projections.
    """
    if month:
        parsed = datetime.strptime(month, "%Y-%m").date()
        start_date = _month_start(parsed)
    else:
        start_date = _month_start()
    end_date = _month_end(start_date)

    start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
    end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

    pricing = _cost_pricing()
    results: list[dict[str, Any]] = []

    for org in Organization.objects.all():
        contract_ids = list(
            TrackedContract.objects.filter(organization=org).values_list("id", flat=True)
        )
        if not contract_ids:
            snapshot, _ = OrganizationCostSnapshot.objects.update_or_create(
                organization=org,
                month=start_date,
                defaults={
                    "rpc_calls": 0,
                    "storage_bytes": 0,
                    "compute_units": 0,
                    "rpc_cost_usd": Decimal("0"),
                    "storage_cost_usd": Decimal("0"),
                    "compute_cost_usd": Decimal("0"),
                    "actual_cost_usd": Decimal("0"),
                    "projected_monthly_cost_usd": Decimal("0"),
                    "breakdown": {"contracts": {}, "event_types": {}, "storage": {}},
                },
            )
            results.append({"organization_id": org.id, "projected_monthly_cost_usd": str(snapshot.projected_monthly_cost_usd)})
            continue

        invocations = ContractInvocation.objects.filter(
            contract_id__in=contract_ids,
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        )
        events = ContractEvent.objects.filter(
            contract_id__in=contract_ids,
            timestamp__gte=start_dt,
            timestamp__lte=end_dt,
        ).select_related("contract")

        rpc_calls = invocations.count()
        event_count = events.count()
        storage_bytes = 0
        by_contract: dict[str, dict[str, Any]] = {}
        by_event_type: dict[str, int] = {}

        for event in events.iterator(chunk_size=500):
            payload_blob = json.dumps(event.payload or {}, sort_keys=True)
            payload_size = len(payload_blob.encode("utf-8"))
            storage_bytes += payload_size

            contract_key = event.contract.contract_id
            info = by_contract.setdefault(
                contract_key,
                {
                    "events": 0,
                    "storage_bytes": 0,
                    "rpc_calls": 0,
                },
            )
            info["events"] += 1
            info["storage_bytes"] += payload_size

            by_event_type[event.event_type] = by_event_type.get(event.event_type, 0) + 1

        invocations_per_contract = invocations.values("contract__contract_id").annotate(count=Count("id"))
        for row in invocations_per_contract:
            contract_key = row["contract__contract_id"]
            info = by_contract.setdefault(
                contract_key,
                {
                    "events": 0,
                    "storage_bytes": 0,
                    "rpc_calls": 0,
                },
            )
            info["rpc_calls"] = row["count"]

        compute_units = rpc_calls + (event_count * 2)

        storage_gb = _decimal(storage_bytes) / _decimal(1024**3)
        rpc_cost = _round_cost(_decimal(rpc_calls) * pricing["rpc_per_call"])
        storage_cost = _round_cost(storage_gb * pricing["storage_per_gb"])
        compute_cost = _round_cost(_decimal(compute_units) * pricing["compute_per_unit"])
        actual_cost = _round_cost(rpc_cost + storage_cost + compute_cost)

        today = timezone.now().date()
        if today < start_date:
            days_elapsed = 1
        elif today > end_date:
            days_elapsed = (end_date - start_date).days + 1
        else:
            days_elapsed = max(1, (today - start_date).days + 1)
        days_in_month = (end_date - start_date).days + 1
        projected_cost = _round_cost(actual_cost * _decimal(days_in_month) / _decimal(days_elapsed))

        total_contract_events = sum(v["events"] for v in by_contract.values()) or 1
        for data in by_contract.values():
            weight = _decimal(data["events"]) / _decimal(total_contract_events)
            allocated_storage = _round_cost(storage_cost * weight)
            allocated_compute = _round_cost(compute_cost * weight)
            allocated_rpc = _round_cost(_decimal(data.get("rpc_calls", 0)) * pricing["rpc_per_call"])
            data["estimated_cost_usd"] = str(_round_cost(allocated_storage + allocated_compute + allocated_rpc))

        breakdown = {
            "contracts": by_contract,
            "event_types": by_event_type,
            "storage": {
                "bytes": storage_bytes,
                "gigabytes": float(storage_gb.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)),
            },
        }

        snapshot, _ = OrganizationCostSnapshot.objects.update_or_create(
            organization=org,
            month=start_date,
            defaults={
                "rpc_calls": rpc_calls,
                "storage_bytes": storage_bytes,
                "compute_units": compute_units,
                "rpc_cost_usd": rpc_cost,
                "storage_cost_usd": storage_cost,
                "compute_cost_usd": compute_cost,
                "actual_cost_usd": actual_cost,
                "projected_monthly_cost_usd": projected_cost,
                "breakdown": breakdown,
            },
        )

        budget = OrganizationBudget.objects.filter(organization=org).first()
        alerts_sent = _emit_budget_alerts(org, snapshot, budget) if budget else 0
        results.append(
            {
                "organization_id": org.id,
                "rpc_calls": rpc_calls,
                "storage_bytes": storage_bytes,
                "compute_units": compute_units,
                "actual_cost_usd": str(actual_cost),
                "projected_monthly_cost_usd": str(projected_cost),
                "alerts_sent": alerts_sent,
            }
        )

    return {
        "month": start_date.isoformat(),
        "organizations": results,
    }


@shared_task(bind=True, max_retries=0)
def run_webhook_replay_job(self, job_id: int) -> dict[str, Any]:
    """Celery entrypoint for webhook replay jobs (issue #1329)."""
    from soroscan.ingest.services.webhook_replay import run_replay_job

    return run_replay_job(job_id)


# ---------------------------------------------------------------------------
# Dead Letter Queue replay (issue #1311)
# ---------------------------------------------------------------------------


@shared_task(
    name="ingest.tasks.replay_dead_letter",
    bind=True,
    max_retries=2,
    soft_time_limit=30,
)
def replay_dead_letter(self, dead_letter_id: int) -> dict[str, Any]:
    """
    Re-dispatch a webhook delivery from a dead-letter entry.

    Loads the WebhookDeadLetter record, verifies the subscription is active,
    and dispatches the original event. On success the DLQ entry is marked resolved.
    """
    try:
        dlq = WebhookDeadLetter.objects.select_related("subscription", "event").get(
            id=dead_letter_id
        )
    except WebhookDeadLetter.DoesNotExist:
        logger.warning("DLQ entry %s not found — skipping replay", dead_letter_id)
        return {"status": "skipped", "reason": "not_found"}

    if dlq.resolved:
        return {"status": "skipped", "reason": "already_resolved"}

    if dlq.event is None:
        dlq.resolved = True
        dlq.resolution_note = "Auto-resolved: original event no longer exists"
        dlq.save(update_fields=["resolved", "resolution_note"])
        return {"status": "skipped", "reason": "event_missing"}

    subscription = dlq.subscription
    if not subscription.is_active:
        # Re-activate the subscription so dispatch_webhook can proceed
        WebhookSubscription.objects.filter(pk=subscription.pk).update(
            is_active=True,
            status=WebhookSubscription.STATUS_ACTIVE,
            failure_count=0,
        )
        subscription.refresh_from_db()

    dispatch_webhook.delay(subscription.id, dlq.event.id, replay=True)

    dlq.resolved = True
    dlq.resolution_note = f"Replayed by task at {timezone.now().isoformat()}"
    dlq.save(update_fields=["resolved", "resolution_note"])

    _get_metrics().webhook_dead_letter_depth.set(
        WebhookDeadLetter.objects.filter(resolved=False).count()
    )

    logger.info(
        "DLQ entry %s replayed for subscription=%s event=%s",
        dead_letter_id,
        subscription.id,
        dlq.event.id,
        extra={"dlq_id": dead_letter_id, "webhook_id": subscription.id, "event_id": dlq.event.id},
    )
    return {"status": "replayed", "dlq_id": dead_letter_id}


def _check_single_contract_health(contract: TrackedContract, now=None, cutoff_1h=None) -> tuple[str, str]:
    """
    Checks and updates health status for a single contract.
    Returns (status, error_message).
    """
    if now is None:
        now = timezone.now()
    if cutoff_1h is None:
        cutoff_1h = now - timedelta(hours=1)

    last_event = ContractEvent.objects.filter(contract=contract).order_by("-timestamp").first()
    if last_event:
        last_event_time = last_event.timestamp
    else:
        last_event_time = contract.created_at

    minutes_since = int((now - last_event_time).total_seconds() / 60) if last_event_time else 0

    decode_errors_1h = ContractEvent.objects.filter(
        contract=contract,
        timestamp__gte=cutoff_1h,
        decoding_status="failed",
    ).count()

    health, _ = ContractHealthCheck.objects.get_or_create(contract=contract)
    old_status = health.status

    if minutes_since > 120:
        new_status = ContractHealthCheck.Status.FAILED
        msg = f"No events for {minutes_since} minutes"
    elif minutes_since > 30 or decode_errors_1h >= 5:
        new_status = ContractHealthCheck.Status.DEGRADED
        msg = f"No events for {minutes_since} minutes" if minutes_since > 30 else f"{decode_errors_1h} ABI decode errors in last hour"
    else:
        new_status = ContractHealthCheck.Status.HEALTHY
        msg = ""


    health.status = new_status
    health.minutes_since_last_event = minutes_since
    health.abi_decode_errors_1h = decode_errors_1h
    health.error_message = msg
    if new_status in (ContractHealthCheck.Status.FAILED, ContractHealthCheck.Status.DEGRADED):
        health.consecutive_failures += 1
    elif new_status == ContractHealthCheck.Status.HEALTHY:
        health.consecutive_failures = 0
    health.last_checked_at = now
    health.save()

    if old_status == ContractHealthCheck.Status.HEALTHY and new_status in (
        ContractHealthCheck.Status.DEGRADED,
        ContractHealthCheck.Status.FAILED,
    ):
        send_health_alert.delay(contract.contract_id, new_status, msg)

    return new_status, msg


@shared_task
def check_contract_health() -> dict[str, Any]:
    """
    Evaluates health status for all active tracked contracts.
    Updates or creates ContractHealthCheck records and sends alerts on status degradation.
    """
    checked_count = 0
    healthy_count = 0
    degraded_count = 0
    failed_count = 0
    errors = []

    now = timezone.now()
    cutoff_1h = now - timedelta(hours=1)

    contracts = TrackedContract.objects.filter(is_active=True, is_paused=False)
    for contract in contracts:
        checked_count += 1
        try:
            new_status, _ = _check_single_contract_health(contract=contract, now=now, cutoff_1h=cutoff_1h)
            if new_status == ContractHealthCheck.Status.HEALTHY:
                healthy_count += 1
            elif new_status == ContractHealthCheck.Status.DEGRADED:
                degraded_count += 1
            else:
                failed_count += 1
        except Exception as e:
            logger.error("Error checking health for contract %s: %s", contract.contract_id, e)
            errors.append({"contract_id": contract.contract_id, "error": str(e)})

    return {
        "checked": checked_count,
        "healthy": healthy_count,
        "degraded": degraded_count,
        "failed": failed_count,
        "errors": errors,
    }


@shared_task
def send_health_alert(contract_id: str, status: str, message: str) -> str:
    """
    Sends an in-app notification when contract health degrades.
    """
    try:
        contract = TrackedContract.objects.select_related("owner").get(contract_id=contract_id)
    except TrackedContract.DoesNotExist:
        return "skipped:contract_gone"

    from soroscan.ingest.services.notifications import create_and_push
    if contract.owner:
        create_and_push(
            user=contract.owner,
            title=f"Contract Health Alert: {status.upper()}",
            message=f"Contract '{contract.name or contract.contract_id}' status changed to {status}: {message}",
            link=f"/contracts/{contract.contract_id}",
            notification_type="contract_health",
        )
    return "sent"


@shared_task
def detect_contract_upgrades() -> dict[str, int]:
    """
    Detects contract deployments and upgrades by checking verified bytecode hashes against existing ContractDeployment records.
    """
    new_deployments = 0
    upgrades_detected = 0

    verifications = ContractVerification.objects.filter(
        status=ContractVerification.Status.VERIFIED
    ).select_related("contract")

    for ver in verifications:
        contract = ver.contract
        bytecode_hash = ver.bytecode_hash
        if not bytecode_hash:
            continue

        existing = ContractDeployment.objects.filter(contract=contract, bytecode_hash=bytecode_hash).first()
        if existing:
            continue

        prev_deployment = ContractDeployment.objects.filter(contract=contract).first()
        is_upgrade = prev_deployment is not None

        ContractDeployment.objects.create(
            contract=contract,
            bytecode_hash=bytecode_hash,
            ledger_deployed=0,
            is_upgrade=is_upgrade,
        )

        if is_upgrade:
            upgrades_detected += 1
        else:
            new_deployments += 1

    return {"new_deployments": new_deployments, "upgrades_detected": upgrades_detected}


def _detect_anomaly(rule: RemediationRule, contract: TrackedContract) -> tuple[bool, dict[str, Any]]:
    """
    Evaluates a single RemediationRule condition against a contract.
    Returns (triggered, snapshot_dict).
    """
    cond = rule.condition or {}
    cond_type = cond.get("type")
    now = timezone.now()

    if cond_type == "no_events_for_minutes" or cond_type == RemediationRule.CONDITION_INGESTION_LAG:
        minutes = cond.get("minutes", cond.get("window_minutes", 60))
        last_evt = ContractEvent.objects.filter(contract=contract).order_by("-timestamp").first()
        if last_evt:
            last_event = last_evt.timestamp
        else:
            last_event = contract.last_event_at

        diff_minutes = (now - last_event).total_seconds() / 60 if last_event else 999999
        if diff_minutes >= minutes:
            return True, {"type": cond_type, "minutes_since": diff_minutes}
        return False, {"type": cond_type, "minutes_since": diff_minutes}

    elif cond_type == RemediationRule.CONDITION_WEBHOOK_FAILURE_BURST:
        window_minutes = cond.get("window_minutes", 60)
        threshold = cond.get("failure_threshold", 3)
        cutoff = now - timedelta(minutes=window_minutes)
        failures = WebhookDeliveryLog.objects.filter(
            subscription__contract=contract,
            status=WebhookDeliveryLog.STATUS_FAILED,
            timestamp__gte=cutoff,
        ).count()
        if failures >= threshold:
            return True, {"type": cond_type, "failed": failures}
        return False, {"type": cond_type, "failed": failures}

    elif cond_type == RemediationRule.CONDITION_RPC_UNAVAILABLE:
        window_minutes = cond.get("window_minutes", 60)
        min_errors = cond.get("min_errors", 3)
        cutoff = now - timedelta(minutes=window_minutes)
        rpc_errors = IngestError.objects.filter(
            contract_id=contract.contract_id,
            error_type=IngestError.ErrorType.RPC_ERROR,
            created_at__gte=cutoff,
        ).count()
        if rpc_errors >= min_errors:
            return True, {"type": cond_type, "rpc_errors": rpc_errors}
        return False, {"type": cond_type, "rpc_errors": rpc_errors}

    return False, {"type": cond_type}


@shared_task
def evaluate_remediation_rules() -> dict[str, int]:
    """
    Evaluates enabled RemediationRules, creates/alerts incidents, and executes remediation actions.
    """
    detected_count = 0
    alerted_count = 0
    executed_count = 0
    resolved_count = 0

    now = timezone.now()

    rules = RemediationRule.objects.filter(enabled=True)
    for rule in rules:
        cond = rule.condition or {}
        cid = cond.get("contract_id")
        if cid:
            contracts = TrackedContract.objects.filter(contract_id=cid)
        else:
            contracts = TrackedContract.objects.all()

        for contract in contracts:
            triggered, snapshot = _detect_anomaly(rule, contract)
            incident = RemediationIncident.objects.filter(
                rule=rule, contract=contract, status__in=[RemediationIncident.STATUS_ALERTED, RemediationIncident.STATUS_EXECUTED]
            ).first()

            if triggered:
                if not incident:
                    grace = timedelta(minutes=rule.grace_period_minutes)
                    incident = RemediationIncident.objects.create(
                        rule=rule,
                        contract=contract,
                        status=RemediationIncident.STATUS_ALERTED,
                        first_detected_at=now,
                        action_after_at=now + grace,
                        anomaly_snapshot=snapshot,
                    )
                    detected_count += 1

                    if rule.alert_target:
                        try:
                            requests.post(rule.alert_target, json={"rule": rule.name, "contract": contract.contract_id, "snapshot": snapshot}, timeout=5)
                        except Exception:
                            pass
                    alerted_count += 1

                if incident.status == RemediationIncident.STATUS_ALERTED and now >= incident.action_after_at:
                    if not rule.dry_run:
                        for action in (rule.actions or []):
                            atype = action.get("type")
                            if atype == "pause_contract":
                                TrackedContract.objects.filter(pk=contract.pk).update(is_active=False)
                            elif atype == "disable_webhooks":
                                WebhookSubscription.objects.filter(contract=contract).update(
                                    is_active=False, status=WebhookSubscription.STATUS_SUSPENDED
                                )
                    incident.status = RemediationIncident.STATUS_EXECUTED
                    incident.executed_at = now
                    incident.save()
                    executed_count += 1
                elif incident.status == RemediationIncident.STATUS_EXECUTED and rule.dry_run:
                    executed_count += 1
            else:
                if incident:
                    incident.status = RemediationIncident.STATUS_RESOLVED
                    incident.resolved_at = now
                    incident.save()
                    AdminAction.objects.create(
                        action="remediation_resolved",
                        object_type="TrackedContract",
                        object_id=contract.contract_id,
                        changes={"description": f"Remediation rule '{rule.name}' incident resolved for {contract.contract_id}"},
                    )
                    resolved_count += 1

    return {
        "detected": detected_count,
        "alerted": alerted_count,
        "executed": executed_count,
        "resolved": resolved_count,
    }


@shared_task
def enforce_retention_policies() -> dict[str, int]:
    """
    Enforces data retention policies by deleting events older than retention_days.
    Returns dict mapping contract_id to count of deleted events.
    """
    results = {}
    policies = DataRetentionPolicy.objects.select_related("contract").all()
    now = timezone.now()

    for policy in policies:
        cutoff = now - timedelta(days=policy.retention_days)
        deleted_count, _ = ContractEvent.objects.filter(
            contract=policy.contract,
            timestamp__lt=cutoff,
        ).delete()
        if deleted_count > 0:
            results[policy.contract.contract_id] = deleted_count

    return results


@shared_task
def process_deletion_requests() -> dict[str, dict[str, Any]]:
    """
    Processes pending GDPR DataDeletionRequests by scrubbing matching PII fields in payloads.
    """
    results = {}
    pending_status = getattr(DataDeletionRequest, "STATUS_PENDING", "pending")
    completed_status = getattr(DataDeletionRequest, "STATUS_COMPLETED", "completed")

    pending_requests = DataDeletionRequest.objects.filter(
        status=pending_status
    ).prefetch_related("contracts")

    for req in pending_requests:
        events_scrubbed = 0
        subject = req.subject_identifier

        contracts = req.contracts.all()
        for contract in contracts:
            pii_fields = PIIField.objects.filter(contract=contract)
            for pii in pii_fields:
                field_path = pii.field_path
                events = ContractEvent.objects.filter(contract=contract)
                if pii.event_type:
                    events = events.filter(event_type=pii.event_type)

                for event in events:
                    if isinstance(event.payload, dict) and event.payload.get(field_path) == subject:
                        event.payload[field_path] = "[DELETED]"
                        event.save(update_fields=["payload"])
                        events_scrubbed += 1

        req.status = completed_status
        req.completed_at = timezone.now()
        req.save(update_fields=["status", "completed_at"])

        results[str(req.pk)] = {"status": "completed", "events_deleted": events_scrubbed}

    return results


@shared_task
def archive_old_events() -> dict[str, int]:
    """
    Archives and deletes events older than retention_days according to DataRetentionPolicy rules.
    Returns {"archived": archived_count, "deleted": deleted_count, "errors": error_count}.
    """
    from .models import DataRetentionPolicy, ContractEvent
    archived_count = 0
    deleted_count = 0
    error_count = 0

    now = timezone.now()
    policies = DataRetentionPolicy.objects.all()

    for policy in policies:
        try:
            cutoff = now - timedelta(days=policy.retention_days)
            qs = ContractEvent.objects.filter(timestamp__lt=cutoff)
            if policy.contract:
                qs = qs.filter(contract=policy.contract)

            count = qs.count()
            if count > 0:
                if policy.archive_enabled:
                    archived_count += count
                count_deleted, _ = qs.delete()
                deleted_count += count_deleted
        except Exception:
            error_count += 1

    return {
        "archived": archived_count,
        "deleted": deleted_count,
        "errors": error_count,
    }


@shared_task(name="ingest.tasks.cleanup_silk_data")
def cleanup_silk_data(days_to_keep: int = 7) -> int:
    """
    Deletes silk profiling request logs older than `days_to_keep` days.
    """
    try:
        from django.conf import settings
        if "silk" not in getattr(settings, "INSTALLED_APPS", []):
            return 0
        from silk.models import Request as SilkRequest
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(days=days_to_keep)
        deleted_count, _ = SilkRequest.objects.filter(start_time__lt=cutoff).delete()
        return deleted_count
    except Exception:
        return 0




    logger.info(
        "Health alert sent for contract %s (status=%s)",
        contract_id,
        status,
        extra={"contract_id": contract_id, "health_status": status},
    )
    return "sent"


@shared_task(bind=True, max_retries=0)
def run_webhook_replay_job(self, job_id: int) -> dict[str, Any]:
    """Celery entrypoint for webhook replay jobs (issue #1329)."""
    from soroscan.ingest.services.webhook_replay import run_replay_job

    return run_replay_job(job_id)
