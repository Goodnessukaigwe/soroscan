"""Replay stored ContractEvent rows through existing processing and webhook delivery.

Used by ``python manage.py replay_events`` to retest webhook delivery or event
processing against local or remote Django/Celery environments. Events are always
fetched via the Django ORM and ordered by their original timestamps.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from django.db.models import QuerySet
from django.utils import timezone

from soroscan.ingest.models import (
    ContractEvent,
    TrackedContract,
    WebhookDeliveryLog,
    WebhookSubscription,
)

logger = logging.getLogger(__name__)

ENV_LOCAL = "local"
ENV_REMOTE = "remote"
TARGET_WEBHOOKS = "webhooks"
TARGET_PROCESSING = "processing"

VALID_ENVIRONMENTS = (ENV_LOCAL, ENV_REMOTE)
VALID_TARGETS = (TARGET_WEBHOOKS, TARGET_PROCESSING)

DEFAULT_LIMIT = 100
DEFAULT_MAX_DELAY_SECONDS = 60.0


class ReplayError(Exception):
    """Raised when replay cannot start (unknown contract, bad filters, etc.)."""


@dataclass
class ReplayDelivery:
    event_id: int
    event_type: str
    ledger: int
    event_index: int
    original_timestamp: str | None
    webhook_id: int | None = None
    webhook_url: str | None = None
    status: str = ""
    status_code: int | None = None
    error: str = ""
    success: bool = False
    queued: bool = False
    task_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReplayReport:
    contract_id: str
    environment: str
    target: str
    mode: str
    database: dict[str, Any]
    filters: dict[str, Any]
    summary: dict[str, int] = field(
        default_factory=lambda: {
            "events_matched": 0,
            "events_processed": 0,
            "webhook_dispatches": 0,
            "successes": 0,
            "failures": 0,
            "queued": 0,
            "skipped": 0,
        }
    )
    deliveries: list[ReplayDelivery] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def describe_database_target() -> dict[str, Any]:
    """Return a credential-free snapshot of the configured database."""
    db = settings.DATABASES.get("default", {})
    name = db.get("NAME") or ""
    host = db.get("HOST") or ""
    engine = db.get("ENGINE") or ""

    database_url = getattr(settings, "DATABASE_URL", "") or ""
    if not host and database_url:
        parsed = urlparse(database_url)
        host = parsed.hostname or ""
        name = name or (parsed.path or "").lstrip("/")

    return {
        "engine": engine.split(".")[-1] if engine else "",
        "name": str(name),
        "host": host or "localhost",
        "debug": bool(getattr(settings, "DEBUG", False)),
        "celery_eager": bool(getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)),
    }


def parse_iso_datetime(value: str, flag_name: str) -> datetime:
    """Parse an ISO-8601 timestamp and ensure it is timezone-aware."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ReplayError(f"Invalid {flag_name}: {exc}") from exc
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def original_timestamp_iso(event: ContractEvent) -> str | None:
    """Return the event's original timestamp as ISO-8601, preserving stored time."""
    ts = event.timestamp
    if ts is None:
        return None
    if timezone.is_naive(ts):
        ts = timezone.make_aware(ts, dt_timezone.utc)
    return ts.isoformat()


def event_to_replay_payload(event: ContractEvent) -> dict[str, Any]:
    """Build the event_data dict used by ``process_new_event``, with original time."""
    return {
        "contract_id": event.contract.contract_id,
        "event_type": event.event_type,
        "payload": event.payload,
        "ledger": event.ledger,
        "event_index": event.event_index,
        "tx_hash": event.tx_hash,
        "timestamp": original_timestamp_iso(event),
        "decodedPayload": event.decoded_payload or {},
    }


def fetch_events_for_replay(
    contract_id: str,
    *,
    event_type: str | None = None,
    from_ledger: int | None = None,
    to_ledger: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    event_id: int | None = None,
    limit: int = DEFAULT_LIMIT,
) -> QuerySet[ContractEvent]:
    """Fetch stored events via the ORM, ordered by original timestamp."""
    if not TrackedContract.objects.filter(contract_id=contract_id).exists():
        raise ReplayError(f"No TrackedContract found with contract_id={contract_id!r}")

    qs = (
        ContractEvent.objects.filter(contract__contract_id=contract_id)
        .select_related("contract")
        .order_by("timestamp", "ledger", "event_index", "id")
    )

    if event_id is not None:
        qs = qs.filter(pk=event_id)
    if event_type:
        qs = qs.filter(event_type=event_type)
    if from_ledger is not None:
        qs = qs.filter(ledger__gte=from_ledger)
    if to_ledger is not None:
        qs = qs.filter(ledger__lte=to_ledger)
    if from_date:
        qs = qs.filter(timestamp__gte=parse_iso_datetime(from_date, "--from-date"))
    if to_date:
        qs = qs.filter(timestamp__lte=parse_iso_datetime(to_date, "--to-date"))

    if limit and limit > 0:
        return qs[:limit]
    return qs


def matching_webhooks(
    contract_id: str,
    event: ContractEvent,
    webhook_id: int | None = None,
) -> list[WebhookSubscription]:
    """Return active webhooks that would receive *event*, matching live dispatch rules."""
    from soroscan.ingest.tasks import evaluate_condition

    qs = WebhookSubscription.objects.filter(
        contract__contract_id=contract_id,
        is_active=True,
        status=WebhookSubscription.STATUS_ACTIVE,
    ).select_related("contract")

    if webhook_id is not None:
        qs = qs.filter(pk=webhook_id)

    matches: list[WebhookSubscription] = []
    for webhook in qs:
        if webhook.event_type and webhook.event_type != event.event_type:
            continue
        if webhook.filter_condition:
            if not evaluate_condition(webhook.filter_condition, event_to_replay_payload(event)):
                continue
        matches.append(webhook)
    return matches


def _sleep_for_original_gap(
    previous_ts: datetime | None,
    current_ts: datetime | None,
    *,
    realtime: bool,
    max_delay_seconds: float,
) -> float:
    """Sleep to preserve original inter-event timing when ``realtime`` is enabled."""
    if not realtime or previous_ts is None or current_ts is None:
        return 0.0
    delta = (current_ts - previous_ts).total_seconds()
    if delta <= 0:
        return 0.0
    delay = min(delta, max_delay_seconds)
    time.sleep(delay)
    return delay


def _latest_delivery_log(webhook: WebhookSubscription, event: ContractEvent) -> WebhookDeliveryLog | None:
    return (
        WebhookDeliveryLog.objects.filter(subscription=webhook, event=event)
        .order_by("-attempt_number", "-id")
        .first()
    )


def _dispatch_webhook(
    webhook: WebhookSubscription,
    event: ContractEvent,
    environment: str,
) -> ReplayDelivery:
    """Replay a single webhook delivery using the existing Celery task."""
    from soroscan.ingest.tasks import dispatch_webhook

    delivery = ReplayDelivery(
        event_id=event.id,
        event_type=event.event_type,
        ledger=event.ledger,
        event_index=event.event_index,
        original_timestamp=original_timestamp_iso(event),
        webhook_id=webhook.id,
        webhook_url=webhook.target_url,
    )

    if environment == ENV_REMOTE:
        async_result = dispatch_webhook.delay(webhook.id, event.id, True)
        delivery.status = "queued"
        delivery.success = True
        delivery.queued = True
        delivery.task_id = str(getattr(async_result, "id", "") or "")
        return delivery

    error = ""
    success = False
    status = "failed"
    try:
        result = dispatch_webhook.apply(args=[webhook.id, event.id, True], throw=False)
        success = bool(result.successful() and result.result)
        if success:
            status = "success"
        elif result.result:
            error = str(result.result)
    except Exception as exc:  # noqa: BLE001 — report any dispatch failure in the replay summary
        error = str(exc)
        status = "error"

    attempt = _latest_delivery_log(webhook, event)
    delivery.success = success
    delivery.status = status
    delivery.status_code = getattr(attempt, "status_code", None)
    delivery.error = error or getattr(attempt, "error", "") or ""
    if attempt and attempt.success:
        delivery.success = True
        delivery.status = "success"
    elif attempt and not success:
        delivery.status = getattr(attempt, "status", None) or status
    return delivery


def _dispatch_processing(event: ContractEvent, environment: str) -> ReplayDelivery:
    """Re-run ``process_new_event`` with the stored original timestamp."""
    from soroscan.ingest.tasks import process_new_event

    event_data = event_to_replay_payload(event)
    delivery = ReplayDelivery(
        event_id=event.id,
        event_type=event.event_type,
        ledger=event.ledger,
        event_index=event.event_index,
        original_timestamp=event_data["timestamp"],
    )

    if environment == ENV_REMOTE:
        async_result = process_new_event.delay(event_data)
        delivery.status = "queued"
        delivery.success = True
        delivery.queued = True
        delivery.task_id = str(getattr(async_result, "id", "") or "")
        return delivery

    try:
        result = process_new_event.apply(args=[event_data], throw=False)
        if result.successful():
            delivery.success = True
            delivery.status = "success"
        else:
            delivery.status = "failed"
            delivery.error = str(result.result) if result.result else "Task failed"
    except Exception as exc:  # noqa: BLE001
        delivery.status = "error"
        delivery.error = str(exc)

    logs = list(
        WebhookDeliveryLog.objects.filter(event=event).order_by("-id")[:1]
    )
    if logs:
        delivery.status_code = logs[0].status_code
        if logs[0].success:
            delivery.success = True
            delivery.status = "success"
    return delivery


def replay_events(
    contract_id: str,
    *,
    environment: str = ENV_LOCAL,
    target: str = TARGET_WEBHOOKS,
    event_type: str | None = None,
    from_ledger: int | None = None,
    to_ledger: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    event_id: int | None = None,
    limit: int = DEFAULT_LIMIT,
    dry_run: bool = False,
    webhook_id: int | None = None,
    realtime: bool = False,
    max_delay_seconds: float = DEFAULT_MAX_DELAY_SECONDS,
) -> ReplayReport:
    """Fetch matching events and replay them with original timestamps.

    * ``environment=local`` runs Celery tasks eagerly (``apply``) so delivery
      status is available immediately — typical for a developer laptop.
    * ``environment=remote`` enqueues tasks (``delay``) onto the configured
      broker, which is how production/staging workers consume work.
    """
    if environment not in VALID_ENVIRONMENTS:
        raise ReplayError(f"environment must be one of {VALID_ENVIRONMENTS}")
    if target not in VALID_TARGETS:
        raise ReplayError(f"target must be one of {VALID_TARGETS}")
    if max_delay_seconds < 0:
        raise ReplayError("--max-delay must be >= 0")

    if webhook_id is not None:
        try:
            webhook = WebhookSubscription.objects.select_related("contract").get(pk=webhook_id)
        except WebhookSubscription.DoesNotExist as exc:
            raise ReplayError(f"No WebhookSubscription found with id={webhook_id}") from exc
        if str(webhook.contract.contract_id) != str(contract_id):
            raise ReplayError(f"Webhook {webhook_id} does not belong to contract {contract_id}")

    queryset = fetch_events_for_replay(
        contract_id,
        event_type=event_type,
        from_ledger=from_ledger,
        to_ledger=to_ledger,
        from_date=from_date,
        to_date=to_date,
        event_id=event_id,
        limit=limit,
    )
    events: list[ContractEvent] = list(queryset)

    report = ReplayReport(
        contract_id=contract_id,
        environment=environment,
        target=target,
        mode="dry-run" if dry_run else "live",
        database=describe_database_target(),
        filters={
            "event_type": event_type,
            "from_ledger": from_ledger,
            "to_ledger": to_ledger,
            "from_date": from_date,
            "to_date": to_date,
            "event_id": event_id,
            "limit": limit,
            "webhook_id": webhook_id,
            "realtime": realtime,
        },
    )
    report.summary["events_matched"] = len(events)

    previous_ts: datetime | None = None
    for event in events:
        report.summary["events_processed"] += 1
        _sleep_for_original_gap(
            previous_ts,
            event.timestamp,
            realtime=realtime and not dry_run,
            max_delay_seconds=max_delay_seconds,
        )
        previous_ts = event.timestamp

        if target == TARGET_PROCESSING:
            if dry_run:
                report.deliveries.append(
                    ReplayDelivery(
                        event_id=event.id,
                        event_type=event.event_type,
                        ledger=event.ledger,
                        event_index=event.event_index,
                        original_timestamp=original_timestamp_iso(event),
                        status="dry-run",
                    )
                )
                continue
            delivery = _dispatch_processing(event, environment)
            _record_delivery(report, delivery)
            continue

        webhooks = matching_webhooks(contract_id, event, webhook_id=webhook_id)
        if not webhooks:
            report.summary["skipped"] += 1
            continue

        for webhook in webhooks:
            if dry_run:
                report.summary["webhook_dispatches"] += 1
                report.deliveries.append(
                    ReplayDelivery(
                        event_id=event.id,
                        event_type=event.event_type,
                        ledger=event.ledger,
                        event_index=event.event_index,
                        original_timestamp=original_timestamp_iso(event),
                        webhook_id=webhook.id,
                        webhook_url=webhook.target_url,
                        status="dry-run",
                    )
                )
                continue
            delivery = _dispatch_webhook(webhook, event, environment)
            _record_delivery(report, delivery)

    return report


def _record_delivery(report: ReplayReport, delivery: ReplayDelivery) -> None:
    report.summary["webhook_dispatches"] += 1
    report.deliveries.append(delivery)
    if delivery.queued:
        report.summary["queued"] += 1
    elif delivery.success:
        report.summary["successes"] += 1
    else:
        report.summary["failures"] += 1
