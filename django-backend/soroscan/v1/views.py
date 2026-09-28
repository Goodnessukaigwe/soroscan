"""
Public v1 API views consumed by the TypeScript SDK.

These endpoints return the cursor-based pagination shape expected by
@soroscan/sdk while sourcing data from the ingest models.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from soroscan.ingest.models import ContractEvent, TrackedContract

from rest_framework.permissions import IsAuthenticated
from soroscan.ingest.models import WebhookDeadLetter
from soroscan.ingest.services.webhook_replay import create_replay_job


def _isoformat(value) -> str | None:
    if value is None:
        return None
    text = value.isoformat()
    if text.endswith("+00:00"):
        return text.replace("+00:00", "Z")
    return text


def _event_to_sdk(event: ContractEvent) -> dict:
    return {
        "id": str(event.id),
        "ledger": event.ledger,
        "ledgerClosedAt": _isoformat(event.timestamp),
        "txHash": event.tx_hash,
        "contractId": event.contract.contract_id,
        "type": event.event_type,
        "topics": [{"type": "symbol", "value": event.event_type}],
        "value": event.payload,
        "inSuccessfulContractCall": True,
        "pagingToken": f"{event.ledger}-{event.event_index}",
    }


def _contract_to_sdk(contract: TrackedContract) -> dict:
    return {
        "id": contract.contract_id,
        "network": contract.network,
        "type": "custom",
        "wasmHash": "",
        "creator": "",
        "createdAt": _isoformat(contract.created_at),
        "createdLedger": contract.last_indexed_ledger or 0,
        "lastActivityAt": _isoformat(contract.last_event_at),
        "totalEvents": contract.events.count(),
        "spec": None,
        "verified": False,
        "verifiedAt": None,
        "sourceCode": None,
        "label": contract.name,
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def list_events(request):
    """
    List contract events in the cursor-based shape expected by the TypeScript SDK.

    Query params:
    - first (int) - Maximum items to return, capped at 200 (default 20)
    - contractId (string) - Filter by Soroban contract ID
    - eventType (string) - Filter by event type label

    - 200: Paginated event list with pageInfo cursors
    """
    try:
        first = min(int(request.query_params.get("first", 20)), 200)
    except (TypeError, ValueError):
        first = 20

    queryset = ContractEvent.objects.select_related("contract").order_by("-timestamp")

    contract_id = request.query_params.get("contractId")
    if contract_id:
        queryset = queryset.filter(contract__contract_id=contract_id)

    event_type = request.query_params.get("eventType")
    if event_type:
        queryset = queryset.filter(event_type=event_type)

    total = queryset.count()
    events = list(queryset[:first])
    items = [_event_to_sdk(event) for event in events]

    return Response(
        {
            "items": items,
            "pageInfo": {
                "hasNextPage": total > first,
                "hasPreviousPage": False,
                "startCursor": items[0]["pagingToken"] if items else None,
                "endCursor": items[-1]["pagingToken"] if items else None,
            },
            "totalCount": total,
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def get_contract(request, contract_id: str):
    """
    Retrieve a single tracked contract for the TypeScript SDK.

    - 200: Contract metadata and activity summary
    - 404: Contract not found
    """
    try:
        contract = TrackedContract.objects.get(contract_id=contract_id)
    except TrackedContract.DoesNotExist:
        return Response(
            {"code": "NOT_FOUND", "message": "Contract not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(_contract_to_sdk(contract))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def bulk_replay_dead_letters(request):
    """
    Bulk replay dead-letter webhooks.
    Expected payload: {"dead_letter_ids": [1, 2, 3]}
    """
    dead_letter_ids = request.data.get("dead_letter_ids", [])
    if not isinstance(dead_letter_ids, list) or not dead_letter_ids:
        return Response(
            {"error": "A non-empty list of dead_letter_ids is required."}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    dead_letters = WebhookDeadLetter.objects.filter(id__in=dead_letter_ids, resolved=False).select_related('subscription', 'event')
    
    jobs_created = []
    for dl in dead_letters:
        if dl.event:
            # Leverage the existing replay job creation logic
            job = create_replay_job(
                subscription=dl.subscription,
                requested_by=request.user,
                contract_id=dl.subscription.contract.contract_id,
                event_type=dl.event.event_type,
                limit=1
            )
            jobs_created.append(job.pk)
            
            # Optionally mark as resolved or pending
            dl.resolved = True
            dl.resolution_note = f"Enqueued replay job {job.pk}"
            dl.save(update_fields=["resolved", "resolution_note"])

    return Response({
        "message": f"Successfully queued {len(jobs_created)} replay jobs.",
        "job_ids": jobs_created
    }, status=status.HTTP_202_ACCEPTED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def replay_dlq_webhooks(request):
    """
    Re-queue dead-lettered webhook deliveries in bulk (issue #1406).

    Accepts either an explicit ``delivery_ids`` list or a ``contract_id`` to
    replay every dead-lettered delivery for one contract:

    ``{"delivery_ids": [1, 2, 3]}`` or ``{"contract_id": "C..."}``

    The work is handed to the ``replay_dead_letter_webhooks`` Celery task and
    the request returns as soon as it is queued.
    """
    if not request.user.is_staff:
        return Response(
            {"error": "Admin access required"},
            status=status.HTTP_403_FORBIDDEN,
        )

    from soroscan.ingest.tasks import replay_dead_letter_webhooks

    delivery_ids = request.data.get("delivery_ids")
    contract_id = request.data.get("contract_id")

    if delivery_ids is not None and not isinstance(delivery_ids, list):
        return Response(
            {"error": "delivery_ids must be a list of delivery log ids."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if contract_id is not None and not isinstance(contract_id, str):
        return Response(
            {"error": "contract_id must be a string."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not delivery_ids and not contract_id:
        return Response(
            {"error": "Provide either delivery_ids or contract_id."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    async_result = replay_dead_letter_webhooks.delay(
        delivery_ids=delivery_ids,
        contract_id=contract_id,
    )

    return Response(
        {
            "message": "Dead-letter replay queued.",
            "task_id": str(async_result.id),
            "delivery_ids": delivery_ids,
            "contract_id": contract_id,
        },
        status=status.HTTP_202_ACCEPTED,
    )
