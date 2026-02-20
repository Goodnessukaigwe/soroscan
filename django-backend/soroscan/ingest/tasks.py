"""
Celery tasks for SoroScan background processing.
"""
import hashlib
import hmac
import logging
from datetime import datetime, timezone as dt_timezone
from typing import Any

import jsonschema
import requests
from celery import shared_task
from django.utils import timezone

from .models import ContractEvent, TrackedContract, WebhookSubscription, IndexerState
from .stellar_client import SorobanClient

logger = logging.getLogger(__name__)
BATCH_LEDGER_SIZE = 200


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


def _upsert_contract_event(
    contract: TrackedContract,
    event: Any,
    fallback_event_index: int = 0,
) -> tuple[ContractEvent, bool]:
    ledger = _safe_int(_event_attr(event, "ledger", "ledger_sequence"), default=0)
    event_index = _extract_event_index(event, fallback_event_index)
    tx_hash = str(_event_attr(event, "tx_hash", "transaction_hash", default="") or "")
    event_type = str(_event_attr(event, "type", "event_type", default="unknown") or "unknown")
    payload = _event_attr(event, "value", "payload", default={}) or {}
    raw_xdr = str(_event_attr(event, "xdr", "raw_xdr", default="") or "")

    timestamp = _event_attr(event, "timestamp", default=timezone.now())
    if isinstance(timestamp, datetime) and timezone.is_naive(timestamp):
        timestamp = timezone.make_aware(timestamp, dt_timezone.utc)
    if not isinstance(timestamp, datetime):
        timestamp = timezone.now()

    return ContractEvent.objects.update_or_create(
        contract=contract,
        ledger=ledger,
        event_index=event_index,
        defaults={
            "tx_hash": tx_hash,
            "event_type": event_type,
            "payload": payload,
            "timestamp": timestamp,
            "raw_xdr": raw_xdr,
        },
    )


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


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def dispatch_webhook(self, event_data: dict[str, Any], webhook_id: int) -> bool:
    """
    Send event data to a webhook subscriber.

    Args:
        event_data: The event payload to send
        webhook_id: ID of the WebhookSubscription

    Returns:
        True if successful, False otherwise
    """
    try:
        webhook = WebhookSubscription.objects.get(id=webhook_id, is_active=True)
    except WebhookSubscription.DoesNotExist:
        logger.warning(
            "Webhook %s not found or inactive",
            webhook_id,
            extra={"webhook_id": webhook_id},
        )
        return False

    # Generate HMAC signature
    payload_str = str(event_data).encode("utf-8")
    signature = hmac.new(
        webhook.secret.encode("utf-8"),
        msg=payload_str,
        digestmod=hashlib.sha256,
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-SoroScan-Signature": signature,
        "X-SoroScan-Timestamp": datetime.utcnow().isoformat(),
    }

    try:
        response = requests.post(
            webhook.target_url,
            json=event_data,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()

        # Update success state
        webhook.last_triggered = timezone.now()
        webhook.failure_count = 0
        webhook.save(update_fields=["last_triggered", "failure_count"])

        contract_id = event_data.get("contract_id")
        logger.info(
            "Webhook %s delivered successfully",
            webhook_id,
            extra={"webhook_id": webhook_id, "contract_id": contract_id},
        )
        return True

    except requests.RequestException as exc:
        # Update failure count
        webhook.failure_count += 1
        webhook.save(update_fields=["failure_count"])
        contract_id = event_data.get("contract_id")

        # Disable webhook after too many failures
        if webhook.failure_count >= 10:
            webhook.is_active = False
            webhook.save(update_fields=["is_active"])
            logger.error(
                "Webhook %s disabled after %s failures",
                webhook_id,
                webhook.failure_count,
                extra={"webhook_id": webhook_id, "contract_id": contract_id},
            )
            return False

        logger.warning(
            "Webhook %s failed, retrying: %s",
            webhook_id,
            exc,
            extra={"webhook_id": webhook_id, "contract_id": contract_id},
        )
        raise self.retry(exc=exc)


@shared_task
def process_new_event(event_data: dict[str, Any]) -> None:
    """
    Process a newly indexed event and trigger webhooks.

    Args:
        event_data: Decoded event data from the ledger
    """
    contract_id = event_data.get("contract_id")
    event_type = event_data.get("event_type")

    if not contract_id:
        logger.warning("Event missing contract_id", extra={})
        return

    # Find matching webhooks
    webhooks = WebhookSubscription.objects.filter(
        contract__contract_id=contract_id,
        is_active=True,
    ).filter(
        # Match specific event type or all events (blank event_type)
        event_type__in=[event_type, ""]
    )

    # Dispatch to all matching webhooks
    for webhook in webhooks:
        dispatch_webhook.delay(event_data, webhook.id)

    logger.info(
        "Dispatched event to %s webhooks",
        webhooks.count(),
        extra={"contract_id": contract_id},
    )


@shared_task
def sync_events_from_horizon() -> int:
    """
    Sync events from Horizon/Soroban RPC.

    This task runs periodically to fetch new events from the ledger
    and store them in the database.

    Returns:
        Number of new events indexed
    """
    from stellar_sdk import SorobanServer
    from django.conf import settings

    # Get last processed cursor
    cursor_state, _ = IndexerState.objects.get_or_create(
        key="horizon_cursor",
        defaults={"value": "now"},
    )
    cursor = cursor_state.value

    server = SorobanServer(settings.SOROBAN_RPC_URL)
    new_events = 0

    try:
        # Get list of tracked contract IDs
        contract_ids = list(
            TrackedContract.objects.filter(is_active=True).values_list("contract_id", flat=True)
        )

        if not contract_ids:
            logger.info("No active contracts to index", extra={})
            return 0

        # Fetch events from Soroban RPC
        # Note: Actual implementation depends on stellar-sdk version
        # This is a simplified example
        events_response = server.get_events(
            start_ledger=int(cursor) if cursor.isdigit() else None,
            filters=[
                {
                    "type": "contract",
                    "contractIds": contract_ids,
                }
            ],
            pagination={"limit": 100},
        )

        for fallback_event_index, event in enumerate(events_response.events):
            # Find the tracked contract
            try:
                contract = TrackedContract.objects.get(contract_id=event.contract_id)
            except TrackedContract.DoesNotExist:
                continue

            payload = event.value  # Decoded payload
            passed, version_used = validate_event_payload(
                contract, event.type, payload, ledger=event.ledger
            )
            validation_status = "passed" if passed else "failed"
            schema_version = version_used

            # Create or get event record
            event_record, created = ContractEvent.objects.get_or_create(
                tx_hash=event.tx_hash,
                ledger=event.ledger,
                event_type=event.type,
                defaults={
                    "contract": contract,
                    "payload": payload,
                    "timestamp": timezone.now(),  # Should parse from ledger
                    "raw_xdr": event.xdr if hasattr(event, "xdr") else "",
                    "validation_status": validation_status,
                    "schema_version": schema_version,
                },
            )
            if not created:
                if (
                    event_record.validation_status != validation_status
                    or event_record.schema_version != schema_version
                ):
                    event_record.validation_status = validation_status
                    event_record.schema_version = schema_version
                    event_record.save(update_fields=["validation_status", "schema_version"])

            if created:
                new_events += 1
                # Trigger webhooks for new events
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

            if contract.last_indexed_ledger is None or event_record.ledger > contract.last_indexed_ledger:
                contract.last_indexed_ledger = event_record.ledger
                contract.save(update_fields=["last_indexed_ledger"])

        # Update cursor
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
        return new_events

    except Exception as e:
        logger.exception("Failed to sync events from Horizon", extra={})
        return 0


@shared_task(bind=True, queue="backfill", max_retries=3, default_retry_delay=60)
def backfill_contract_events(
    self,
    contract_id: str,
    from_ledger: int,
    to_ledger: int,
) -> dict[str, Any]:
    """
    Backfill events for one contract within an inclusive ledger range.
    """
    start_ledger = _safe_int(from_ledger, default=0)
    end_ledger = _safe_int(to_ledger, default=0)

    if start_ledger <= 0 or end_ledger <= 0 or start_ledger > end_ledger:
        raise ValueError("Invalid ledger range provided")

    try:
        contract = TrackedContract.objects.get(contract_id=contract_id)
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
        for batch_start in range(next_ledger, end_ledger + 1, BATCH_LEDGER_SIZE):
            batch_end = min(batch_start + BATCH_LEDGER_SIZE - 1, end_ledger)
            batch_events = client.get_events_range(contract.contract_id, batch_start, batch_end)

            if not batch_events:
                logger.warning(
                    "No events returned for contract=%s ledgers=%s-%s",
                    contract.contract_id,
                    batch_start,
                    batch_end,
                )

            for fallback_event_index, event in enumerate(batch_events):
                _, created = _upsert_contract_event(contract, event, fallback_event_index)
                processed_events += 1
                if created:
                    created_events += 1
                else:
                    updated_events += 1

            contract.last_indexed_ledger = batch_end
            contract.save(update_fields=["last_indexed_ledger"])

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
        raise self.retry(exc=exc)
