"""
API Views for SoroScan event ingestion.
"""
import hashlib
import hmac
import json
import logging
import re
import time
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Max, Min, Q, Avg, Sum
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control, cache_page
from django.views.decorators.vary import vary_on_headers
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiParameter
from rest_framework import renderers, serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.pagination import PageNumberPagination

import requests as http_requests

from soroscan.throttles import IngestRateThrottle, UnauthenticatedIPRateThrottle
from soroscan.webhook_signing import build_x_signature_header, public_key_base64

from .cache_utils import cache_result, get_or_set_json, query_cache_ttl, stable_cache_key
from .decorators import validate_webhook_signature
from .telemetry import tracer
from .models import (  # noqa: E402
    APIKey,
    AdminAction,
    ArchivedEventBatch,
    ContractEvent,
    ContractHealthCheck,
    ContractInvocation,
    ContractSnapshot,
    ContractSource,
    ContractVerification,
    Organization,
    OrganizationCostSnapshot,
    OrganizationBudget,
    OrganizationMembership,
    IngestError,
    IndexerState,
    Team,
    TeamMembership,
    TrackedContract,
    WebhookDeliveryLog,
    WebhookSubscription,
)
from .cache_utils import get_cached_contract
from .serializers import (
    APIKeySerializer,
    BulkMetadataImportSerializer,
    ContractEventSerializer,
    ContractInvocationSerializer,
    ContractSnapshotSerializer,
    ContractSourceSerializer,
    ContractVerificationSerializer,
    EventDeduplicationConfigSerializer,
    EventDeduplicationTestSerializer,
    EventSearchSerializer,
    EventsByContractsRequestSerializer,
    OrganizationBudgetSerializer,
    OrganizationCorsSerializer,
    OrganizationCostSnapshotSerializer,
    RecordEventRequestSerializer,
    AddIndexerRequestSerializer,
    StructuredEventRequestSerializer,
    TeamMemberAddSerializer,
    TeamSerializer,
    TrackedContractSerializer,
    WebhookDeliveryLogSerializer,
    WebhookReplayJobSerializer,
    WebhookReplayRequestSerializer,
    WebhookSubscriptionSerializer,
)
from .stellar_client import SorobanClient

logger = logging.getLogger(__name__)

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 1000


class AdminActionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = AdminAction
        fields = [
            "id",
            "username",
            "action",
            "object_type",
            "object_id",
            "timestamp",
            "ip_address",
            "changes",
        ]


def _frontend_base_url() -> str:
    return getattr(settings, "FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")


class TrackedContractViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing tracked contracts.

    Endpoints:
    - GET /contracts/ - List all tracked contracts
    - POST /contracts/ - Register a new contract
    - GET /contracts/{id}/ - Get contract details
    - PUT /contracts/{id}/ - Update contract
    - DELETE /contracts/{id}/ - Delete contract
    - GET /contracts/{id}/events/ - Get events for contract
    - GET /contracts/{id}/stats/ - Get contract statistics
    """

    queryset = TrackedContract.objects.all()
    serializer_class = TrackedContractSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["is_active"]
    search_fields = ["name", "alias", "contract_id"]
    ordering_fields = ["created_at", "name", "alias"]
    ordering = ["-created_at"]
    action_throttle_scopes = {
        "stats": "contract_stats",
        "bulk_import_metadata": "contract_bulk_import",
        "dedup_test": "dedup_test",
    }

    @staticmethod
    def _collect_warnings(items: list[dict]) -> list[dict[str, str]]:
        warnings: list[dict[str, str]] = []
        for item in items:
            for warning in item.get("warnings", []):
                if warning not in warnings:
                    warnings.append(warning)
        return warnings

    @method_decorator(cache_control(max_age=query_cache_ttl()))
    def list(self, request, *args, **kwargs):
        """Cache the contracts list per user (issue #1011)."""
        user_id = request.user.id if request.user and request.user.is_authenticated else "anon"
        page = request.query_params.get("page", "1")
        page_size = request.query_params.get("page_size", "default")
        is_active = request.query_params.get("is_active", "all")
        search = request.query_params.get("search", "")
        ordering = request.query_params.get("ordering", "")
        cache_key = f"contract_list_user_{user_id}_p{page}_s{page_size}_a{is_active}_q{search}_o{ordering}"

        def _build():
            response = super(TrackedContractViewSet, self).list(request, *args, **kwargs)
            if isinstance(response.data, dict) and "results" in response.data:
                response.data["warnings"] = self._collect_warnings(response.data["results"])
            return response.data

        data = get_or_set_json(cache_key, query_cache_ttl(), _build)
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        if isinstance(response.data, dict):
            response.data.setdefault("warnings", [])
        return response

    def create(self, request, *args, **kwargs):
        dry_run = request.query_params.get("dry_run", "").lower() == "true"
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if dry_run:
            return Response({"detail": "Valid"}, status=status.HTTP_200_OK)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
        self._invalidate_list_cache()

    def perform_update(self, serializer):
        instance = serializer.save()
        self._invalidate_list_cache()
        from .tasks import alert_downstream_contract_change

        alert_downstream_contract_change.delay(instance.contract_id, "modified")

    def _invalidate_list_cache(self):
        from django.core.cache import cache as _cache

        if hasattr(_cache, "delete_pattern"):
            _cache.delete_pattern("*contract_list*")
        else:
            _cache.clear()

    def destroy(self, request, *args, **kwargs):
        response = super().destroy(request, *args, **kwargs)
        self._invalidate_list_cache()
        return response

    def get_queryset(self):
        qs = TrackedContract.objects.all()
        user = self.request.user
        if self.request.method in ["GET", "HEAD", "OPTIONS"]:
            if user.is_authenticated:
                return qs.filter(Q(owner=user) | Q(team__memberships__user=user)).distinct()
            return qs
        return qs.filter(owner=self.request.user)

    @extend_schema(responses=ContractEventSerializer(many=True))
    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        """Get all events for a specific contract."""
        contract = self.get_object()
        events = contract.events.select_related("contract").all()[:100]
        serializer = ContractEventSerializer(events, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=inline_serializer(
            name="ContractPauseRequest",
            fields={
                "reason": serializers.CharField(required=False, allow_blank=True),
                "resume_at": serializers.DateTimeField(required=False, allow_null=True),
            },
        ),
        responses=TrackedContractSerializer,
    )
    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        """Suspend indexing for this contract; historical data stays queryable."""
        contract = self.get_object()
        reason = request.data.get("reason", "")
        resume_at_raw = request.data.get("resume_at")
        resume_at = parse_datetime(resume_at_raw) if resume_at_raw else None
        if resume_at_raw and resume_at is None:
            return Response(
                {"detail": "resume_at must be a valid ISO 8601 datetime."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        contract.pause(reason=reason, resume_at=resume_at)
        contract.refresh_from_db()
        return Response(TrackedContractSerializer(contract).data)

    @extend_schema(responses=TrackedContractSerializer)
    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        """Resume indexing for a previously paused contract."""
        contract = self.get_object()
        contract.resume()
        contract.refresh_from_db()
        return Response(TrackedContractSerializer(contract).data)

    @extend_schema(
        responses=inline_serializer(
            name="ContractStats",
            fields={
                "total_events": serializers.IntegerField(),
                "unique_event_types": serializers.IntegerField(),
                "latest_ledger": serializers.IntegerField(),
                "last_activity": serializers.DateTimeField(),
                "contract_id": serializers.CharField(),
                "name": serializers.CharField(),
            },
        )
    )
    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        """Get statistics for a contract."""
        contract = self.get_object()
        cache_key = stable_cache_key(
            "rest_contract_stats",
            {"contract_pk": contract.pk, "cid": contract.contract_id},
        )

        def _build():
            agg = contract.events.aggregate(
                total_events=Count("id"),
                unique_event_types=Count("event_type", distinct=True),
                latest_ledger=Max("ledger"),
            )
            agg["contract_id"] = contract.contract_id
            agg["name"] = contract.name
            agg["last_activity"] = contract.last_event_at
            return agg

        stats = get_or_set_json(cache_key, query_cache_ttl(), _build)
        return Response(stats)

    @action(detail=True, methods=["get"])
    def completeness(self, request, pk=None):
        contract = self.get_object()
        state = IndexerState.objects.filter(key=f"completeness:{contract.id}").first()
        if state:
            try:
                return Response(json.loads(state.value))
            except json.JSONDecodeError:
                pass

        from .tasks import _calculate_completeness

        return Response(_calculate_completeness(contract))

    @extend_schema(responses=ContractSnapshotSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="snapshots")
    def snapshots(self, request, pk=None):
        """List contract state snapshots, optionally filtered by ledger range."""
        contract = self.get_object()
        qs = ContractSnapshot.objects.filter(contract=contract).prefetch_related("changes")

        ledger_min = request.query_params.get("ledger_min")
        ledger_max = request.query_params.get("ledger_max")
        if ledger_min is not None:
            qs = qs.filter(ledger_sequence__gte=int(ledger_min))
        if ledger_max is not None:
            qs = qs.filter(ledger_sequence__lte=int(ledger_max))

        serializer = ContractSnapshotSerializer(qs.order_by("-ledger_sequence"), many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def completeness_dashboard(self, request):
        from .tasks import _calculate_completeness

        rows = []
        for contract in self.get_queryset():
            state = IndexerState.objects.filter(key=f"completeness:{contract.id}").first()
            if state:
                try:
                    rows.append(json.loads(state.value))
                    continue
                except json.JSONDecodeError:
                    pass
            rows.append(_calculate_completeness(contract))

        rows.sort(key=lambda item: item.get("completeness_percentage", 100.0))
        return Response({"contracts": rows})

    @action(detail=True, methods=["post"])
    def upload_source(self, request, pk=None):
        """
        Upload contract source code for verification.
        Accepts a file (Rust code or tarball) and optional ABI JSON.
        """
        contract = self.get_object()

        # Check permissions - only contract owner or team members
        if contract.owner != request.user and not contract.team.members.filter(user=request.user).exists():
            return Response({"error": "Permission denied"}, status=403)

        serializer = ContractSourceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(contract=contract, uploaded_by=request.user)
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @action(detail=True, methods=["post"])
    def verify_source(self, request, pk=None):
        """
        Verify contract source against deployed bytecode.
        """
        contract = self.get_object()

        # Get latest source
        try:
            source = contract.sources.latest('uploaded_at')
        except ContractSource.DoesNotExist:
            return Response({"error": "No source uploaded"}, status=400)

        # Placeholder verification logic
        # In real implementation, this would:
        # 1. Extract/compile source code to get bytecode
        # 2. Query Stellar network for deployed bytecode
        # 3. Compare hashes

        # For now, mark as verified
        verification, created = ContractVerification.objects.get_or_create(
            contract=contract,
            defaults={
                'source': source,
                'status': 'verified',
                'bytecode_hash': 'placeholder_hash',
                'compiler_version': 'unknown',
                'verified_at': timezone.now(),
            }
        )

        if not created:
            verification.status = 'verified'
            verification.source = source
            verification.bytecode_hash = 'placeholder_hash'
            verification.compiler_version = 'unknown'
            verification.verified_at = timezone.now()
            verification.save()

        serializer = ContractVerificationSerializer(verification)
        return Response(serializer.data)

    @extend_schema(
        responses=EventDeduplicationConfigSerializer,
        request=EventDeduplicationConfigSerializer,
    )
    @action(detail=True, methods=["get", "put", "patch"], url_path="dedup-config")
    def dedup_config(self, request, pk=None):
        """Get or update event deduplication field configuration (issue #1328)."""
        from .models import EventDeduplicationConfig

        contract = self.get_object()
        if request.method == "GET":
            config = getattr(contract, "dedup_config", None)
            if config is None:
                return Response({"enabled": False, "fields": []})
            return Response(
                EventDeduplicationConfigSerializer(
                    {"enabled": config.enabled, "fields": config.fields or []}
                ).data
            )

        if not request.user.is_staff and contract.owner_id != request.user.id:
            return Response({"detail": "Admin or owner access required."}, status=403)

        serializer = EventDeduplicationConfigSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        config, _ = EventDeduplicationConfig.objects.update_or_create(
            contract=contract,
            defaults={
                "enabled": serializer.validated_data["enabled"],
                "fields": serializer.validated_data["fields"],
            },
        )
        return Response(
            EventDeduplicationConfigSerializer(
                {"enabled": config.enabled, "fields": config.fields or []}
            ).data
        )

    @extend_schema(
        request=EventDeduplicationTestSerializer,
        responses={
            200: inline_serializer(
                name="DedupTestResponse",
                fields={
                    "dedup_enabled": serializers.BooleanField(),
                    "dedup_hash": serializers.CharField(required=False),
                    "material": serializers.JSONField(required=False),
                    "fields": serializers.ListField(
                        child=serializers.CharField(), required=False
                    ),
                },
            )
        },
    )
    @action(detail=True, methods=["post"], url_path="dedup-test")
    def dedup_test(self, request, pk=None):
        """Test dedup fingerprint computation for a sample event (issue #1328)."""
        from soroscan.ingest.services.event_dedup import fingerprint_event

        contract = self.get_object()
        config = getattr(contract, "dedup_config", None)
        if not config or not config.enabled:
            return Response({"dedup_enabled": False})

        serializer = EventDeduplicationTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payload = data.get("payload") or {}
        raw = {
            "event_type": data.get("event_type"),
            "ledger": data.get("ledger"),
            "event_index": data.get("event_index"),
            "tx_hash": data.get("tx_hash"),
            "payload": payload,
        }
        dedup_hash, material = fingerprint_event(
            config.fields or [],
            event_type=data.get("event_type"),
            ledger=data.get("ledger"),
            event_index=data.get("event_index"),
            tx_hash=data.get("tx_hash"),
            payload=payload,
            raw=raw,
        )
        return Response(
            {
                "dedup_enabled": True,
                "dedup_hash": dedup_hash,
                "material": material,
                "fields": config.fields or [],
            }
        )

    @extend_schema(
        request=BulkMetadataImportSerializer,
        responses={
            200: inline_serializer(
                name="BulkMetadataImportResponse",
                fields={
                    "mode": serializers.CharField(),
                    "created": serializers.IntegerField(),
                    "updated": serializers.IntegerField(),
                    "errors": serializers.IntegerField(),
                },
            )
        },
    )
    @action(detail=False, methods=["post"], url_path="metadata/bulk-import")
    def bulk_import_metadata(self, request):
        """
        Bulk import contract metadata from CSV or JSON (issue #1327).

        Accepts multipart file upload (``file``) or raw ``content`` string.
        """
        from soroscan.ingest.services.metadata_bulk_import import (
            BulkImportError,
            detect_format,
            import_metadata_rows,
            parse_rows,
        )

        if not request.user.is_staff:
            return Response({"detail": "Admin access required."}, status=403)

        serializer = BulkMetadataImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dry_run = serializer.validated_data.get("dry_run", False)
        on_error = serializer.validated_data.get("on_error", "rollback")

        upload = request.FILES.get("file")
        raw = serializer.validated_data.get("content") or ""
        filename = None
        if upload is not None:
            raw = upload.read().decode("utf-8")
            filename = getattr(upload, "name", None)

        if not raw.strip():
            return Response(
                {"detail": "Provide a CSV/JSON file or content body."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            fmt = detect_format(filename, serializer.validated_data.get("format"))
            rows = parse_rows(raw, fmt)
            report = import_metadata_rows(rows, dry_run=dry_run, on_error=on_error)
        except BulkImportError as exc:
            return Response(
                {"detail": str(exc), "report": exc.report},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(report)


class ContractEventViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for querying indexed events.

    Endpoints:
    - GET /events/ - List all events (paginated)
    - GET /events/{id}/ - Get event details
    - GET /events/search/ - Full-text + field-level search
    """

    queryset = ContractEvent.objects.all()
    serializer_class = ContractEventSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = [
        "contract__contract_id",
        "event_type",
        "ledger",
        "tx_hash",
        "validation_status",
        "decoding_status",
        "signature_status",
    ]
    ordering_fields = ["timestamp", "ledger"]
    ordering = ["-timestamp"]
    action_throttle_scopes = {
        "search": "events_search",
    }

    def get_queryset(self):
        qs = ContractEvent.objects.select_related("contract").all()
        
        # Support comma-separated 'type' filter (Issue #476)
        event_types = self.request.query_params.get("type")
        if event_types:
            types_list = [t.strip() for t in event_types.split(",") if t.strip()]
            if types_list:
                qs = qs.filter(event_type__in=types_list)
                
        return qs

    @extend_schema(
        request=EventsByContractsRequestSerializer,
        responses=ContractEventSerializer(many=True),
    )
    @action(detail=False, methods=["post"], url_path="by-contracts")
    def by_contracts(self, request):
        """Return one ordered page of events emitted by up to ten contracts."""
        payload = EventsByContractsRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        filters = payload.validated_data

        queryset = ContractEvent.objects.select_related("contract").filter(
            contract__contract_id__in=filters["contract_ids"]
        )
        if filters.get("event_type"):
            queryset = queryset.filter(event_type=filters["event_type"])
        if filters.get("ledger_min") is not None:
            queryset = queryset.filter(ledger__gte=filters["ledger_min"])
        if filters.get("ledger_max") is not None:
            queryset = queryset.filter(ledger__lte=filters["ledger_max"])

        queryset = queryset.order_by(filters["ordering"], "-id")
        count = queryset.count()
        offset = (filters["page"] - 1) * filters["page_size"]
        events = queryset[offset : offset + filters["page_size"]]
        return Response(
            {
                "count": count,
                "next": None,
                "previous": None,
                "results": self.get_serializer(events, many=True).data,
                "contract_ids": filters["contract_ids"],
            }
        )

    @extend_schema(
        parameters=[
            inline_serializer(
                name="EventSearchParams",
                fields={
                    "q": serializers.CharField(required=False),
                    "contract_id": serializers.CharField(required=False),
                    "event_type": serializers.CharField(required=False),
                    "payload_contains": serializers.CharField(required=False),
                    "payload_field": serializers.CharField(required=False),
                    "payload_op": serializers.ChoiceField(
                        choices=["eq", "neq", "gte", "lte", "gt", "lt", "contains", "startswith", "in"],
                        required=False,
                    ),
                    "payload_value": serializers.CharField(required=False),
                    "page": serializers.IntegerField(required=False),
                    "page_size": serializers.IntegerField(required=False),
                },
            )
        ],
        responses=EventSearchSerializer(many=True),
    )
    @action(detail=False, methods=["get"])
    def search(self, request):
        """
        Full-text and field-level search on contract event payloads.

        Query params:
        - q                 — free-text substring match against JSON payload text
        - contract_id       — filter by contract
        - event_type        — filter by event type
        - payload_contains  — JSON containment sub-string (fast with GIN index)
        - payload_field     — dot-notation field path, e.g. decodedPayload.to
        - payload_op        — operator: eq|neq|gte|lte|gt|lt|contains|startswith|in
        - payload_value     — value for field comparison
        - page / page_size  — pagination (max 1000 per page)
        """
        qs = ContractEvent.objects.select_related("contract").all()

        # --- contract / event_type pre-filters --------------------------------
        contract_id = request.GET.get("contract_id")
        if contract_id:
            qs = qs.filter(contract__contract_id=contract_id)

        event_type = request.GET.get("event_type")
        if event_type:
            qs = qs.filter(event_type=event_type)

        # --- free-text substring search against JSON cast to text -------------
        q = request.GET.get("q", "").strip()
        if q:
            from django.db.models import TextField
            qs = qs.annotate(
                _decoded_payload_text=Cast("decoded_payload", output_field=TextField()),
            ).filter(_decoded_payload_text__icontains=q)

        # --- payload_contains: JSON containment using GIN index ---------------
        payload_contains = request.GET.get("payload_contains", "").strip()
        if payload_contains:
            from django.db.models import TextField
            if not q:  # avoid double annotation
                qs = qs.annotate(
                    _decoded_payload_text=Cast("decoded_payload", output_field=TextField()),
                )
            qs = qs.filter(_decoded_payload_text__icontains=payload_contains)

        # --- payload_field / payload_op / payload_value -----------------------
        payload_field = request.GET.get("payload_field", "").strip()
        payload_op = request.GET.get("payload_op", "eq").strip().lower()
        payload_value = request.GET.get("payload_value")

        if payload_field and payload_value is not None:
            # Build ORM lookup key from dot-notation → Django JSONField traversal
            # e.g. "decodedPayload.to" → payload__decodedPayload__to
            orm_path = "payload__" + payload_field.replace(".", "__")

            op_map = {
                "eq": "",
                "neq": None,  # handled below
                "gte": "__gte",
                "lte": "__lte",
                "gt": "__gt",
                "lt": "__lt",
                "contains": "__icontains",
                "startswith": "__istartswith",
                "in": "__in",
            }
            suffix = op_map.get(payload_op, "")
            if payload_op == "neq":
                qs = qs.exclude(**{orm_path: payload_value})
            elif payload_op == "in":
                values = [v.strip() for v in payload_value.split(",")]
                qs = qs.filter(**{f"{orm_path}__in": values})
            else:
                qs = qs.filter(**{f"{orm_path}{suffix}": payload_value})

        # --- pagination -------------------------------------------------------
        try:
            page = max(1, int(request.GET.get("page", 1)))
            page_size = min(max(1, int(request.GET.get("page_size", 50))), 1000)
        except (ValueError, TypeError):
            page = 1
            page_size = 50

        qs = qs.order_by("-timestamp")
        cache_key = stable_cache_key(
            "rest_event_search",
            dict(request.GET.items()),
        )

        def _build():
            total = qs.count()
            offset = (page - 1) * page_size
            items = list(qs[offset : offset + page_size])
            ser = EventSearchSerializer(items, many=True)
            return {
                "count": total,
                "page": page,
                "page_size": page_size,
                "results": ser.data,
            }

        payload = get_or_set_json(cache_key, query_cache_ttl(), _build)
        return Response(payload)


class ContractInvocationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for querying contract invocations.

    Endpoints:
    - GET /api/contracts/{contract_id}/invocations/ - List invocations
    - GET /api/invocations/{id}/ - Get invocation details
    """

    serializer_class = ContractInvocationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["caller", "function_name"]
    ordering_fields = ["created_at", "ledger_sequence"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Filter by contract and user ownership."""
        contract_id = self.kwargs.get("contract_id")
        qs = ContractInvocation.objects.select_related("contract").filter(
            contract__owner=self.request.user
        )
        if contract_id:
            qs = qs.filter(contract__contract_id=contract_id)
        return qs

    def get_serializer_context(self):
        """Add include_events flag from query params."""
        context = super().get_serializer_context()
        context["include_events"] = self.request.query_params.get("include_events") == "true"
        return context

    def list(self, request, *args, **kwargs):
        """
        List invocations with optional filters.

        Query params:
        - caller: Filter by caller address
        - function_name: Filter by function name
        - since: ISO timestamp for start of range
        - until: ISO timestamp for end of range
        - include_events: Include nested events (default: false)
        """
        queryset = self.filter_queryset(self.get_queryset())

        # Timestamp range filtering
        since = request.query_params.get("since")
        until = request.query_params.get("until")
        if since:
            queryset = queryset.filter(created_at__gte=since)
        if until:
            queryset = queryset.filter(created_at__lte=until)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)



class WebhookSubscriptionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing webhook subscriptions.

    Endpoints:
    - GET /webhooks/ - List all webhooks
    - POST /webhooks/ - Create a new webhook
    - GET /webhooks/{id}/ - Get webhook details
    - PUT /webhooks/{id}/ - Update webhook
    - DELETE /webhooks/{id}/ - Delete webhook
    - POST /webhooks/{id}/test/ - Send a test webhook
    """

    queryset = WebhookSubscription.objects.all()
    serializer_class = WebhookSubscriptionSerializer
    action_throttle_scopes = {
        "replay": "webhook_replay",
    }

    def get_queryset(self):
        # Public read access, but filter by owner for write operations
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return WebhookSubscription.objects.all()
        return WebhookSubscription.objects.filter(contract__owner=self.request.user)

    @extend_schema(
        request=None,
        responses={
            200: inline_serializer(
                name="TestWebhookResponse",
                fields={"status": serializers.CharField()},
            )
        },
    )
    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """
        Send a test delivery directly to the webhook endpoint.

        The request is sent synchronously with a proper HMAC-SHA256 signature
        so the subscriber can verify authenticity.  A 200 response from this
        endpoint does NOT mean the delivery succeeded — check the response body
        for the actual outcome.
        """
        webhook = self.get_object()
        test_payload = {
            "event_type": "test",
            "payload": {"message": "This is a test webhook"},
            "contract_id": webhook.contract.contract_id,
            "timestamp": timezone.now().isoformat(),
        }
        payload_bytes = json.dumps(test_payload, sort_keys=True).encode("utf-8")
        algorithm = (webhook.signature_algorithm or WebhookSubscription.SIGNATURE_SHA256).lower()
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

        headers = {
            "Content-Type": "application/json",
            "X-SoroScan-Signature": f"{prefix}={sig_hex}",
            "X-SoroScan-Timestamp": timezone.now().isoformat(),
        }
        try:
            headers["X-Signature"] = build_x_signature_header(payload_bytes)
        except ValueError:
            pass

        try:
            http_requests.post(
                webhook.target_url,
                data=payload_bytes,
                headers=headers,
                timeout=10,
            )
        except http_requests.RequestException as exc:
            logger.warning(
                "Test webhook delivery to %s failed: %s",
                webhook.target_url,
                exc,
                extra={"webhook_id": webhook.id},
            )

        return Response({"status": "test_webhook_queued"})

    @extend_schema(
        request=None,
        responses={
            200: inline_serializer(
                name="PingWebhookResponse",
                fields={
                    "status": serializers.CharField(),
                    "webhook_id": serializers.IntegerField(),
                },
            )
        },
    )
    @action(detail=True, methods=["post"])
    def ping(self, request, pk=None):
        """
        Dispatch a background task that sends a test ping payload to the webhook
        endpoint.  The task logs whether the target responded with HTTP 200.
        """
        from .tasks import ping_webhook

        webhook = self.get_object()
        ping_webhook.delay(webhook.id)
        return Response({"status": "ping_queued", "webhook_id": webhook.id})

    @extend_schema(
        request=inline_serializer(
            name="WebhookConditionDryRunRequest",
            fields={
                "sample_event": serializers.JSONField(),
            },
        ),
        responses={
            200: inline_serializer(
                name="WebhookConditionDryRunResponse",
                fields={
                    "matched": serializers.BooleanField(),
                },
            )
        },
    )
    @action(detail=True, methods=["post"], url_path="dry-run")
    def dry_run(self, request, pk=None):
        webhook = self.get_object()
        sample_event = request.data.get("sample_event")
        if not isinstance(sample_event, dict):
            return Response(
                {"detail": "sample_event must be an object."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not webhook.filter_condition:
            return Response({"matched": True})

        from .tasks import evaluate_condition

        matched = evaluate_condition(webhook.filter_condition, sample_event)
        return Response({"matched": bool(matched)})

    @extend_schema(
        responses={200: WebhookDeliveryLogSerializer(many=True)},
        parameters=[
            inline_serializer(
                name="DeliveriesFilterParams",
                fields={
                    "status": serializers.CharField(required=False),
                    "since": serializers.DateTimeField(required=False),
                    "until": serializers.DateTimeField(required=False),
                },
            )
        ],
    )
    @action(detail=True, methods=["get"])
    def deliveries(self, request, pk=None):
        """
        Return paginated delivery log history for a webhook subscription.

        Query params:
        - ``status``  — filter by delivery status (pending/success/failed/dead_letter)
        - ``since``   — ISO datetime lower bound for ``timestamp``
        - ``until``   — ISO datetime upper bound for ``timestamp``

        Issue #765.
        """
        from .models import WebhookDeliveryLog

        webhook = self.get_object()
        qs = (
            WebhookDeliveryLog.objects.filter(subscription=webhook)
            .select_related("event")
            .order_by("-timestamp")
        )

        delivery_status = request.query_params.get("status")
        if delivery_status:
            qs = qs.filter(status=delivery_status)

        since = request.query_params.get("since")
        if since:
            qs = qs.filter(timestamp__gte=since)

        until = request.query_params.get("until")
        if until:
            qs = qs.filter(timestamp__lte=until)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = WebhookDeliveryLogSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = WebhookDeliveryLogSerializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=WebhookReplayRequestSerializer,
        responses={202: WebhookReplayJobSerializer},
    )
    @action(detail=True, methods=["post"])
    def replay(self, request, pk=None):
        """
        Replay historical events to this webhook with filters (issue #1329).

        Creates a WebhookReplayJob, rate-limits dispatch, and tracks status.
        """
        from soroscan.ingest.services.webhook_replay import create_replay_job
        from .tasks import run_webhook_replay_job

        webhook = self.get_object()
        if (
            not request.user.is_staff
            and webhook.contract.owner_id != getattr(request.user, "id", None)
        ):
            return Response({"detail": "Permission denied."}, status=403)

        serializer = WebhookReplayRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            job = create_replay_job(
                subscription=webhook,
                requested_by=request.user if request.user.is_authenticated else None,
                contract_id=data.get("contract_id") or webhook.contract.contract_id,
                event_type=data.get("event_type") or None,
                from_date=data.get("from_date") or None,
                to_date=data.get("to_date") or None,
                from_ledger=data.get("from_ledger"),
                to_ledger=data.get("to_ledger"),
                limit=data.get("limit", 100),
                rate_limit_per_second=data.get("rate_limit_per_second", 5.0),
                dry_run=data.get("dry_run", False),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        run_webhook_replay_job.delay(job.id)
        return Response(
            WebhookReplayJobSerializer(job.to_status_dict()).data,
            status=status.HTTP_202_ACCEPTED,
        )

    @extend_schema(responses=WebhookReplayJobSerializer)
    @action(detail=True, methods=["get"], url_path=r"replay/(?P<job_id>[^/.]+)")
    def replay_status(self, request, pk=None, job_id=None):
        """Return status for a webhook replay job (issue #1329)."""
        from .models import WebhookReplayJob

        webhook = self.get_object()
        job = get_object_or_404(
            WebhookReplayJob, pk=job_id, subscription=webhook
        )
        return Response(WebhookReplayJobSerializer(job.to_status_dict()).data)

    @extend_schema(responses=WebhookReplayJobSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="replays")
    def replays(self, request, pk=None):
        """List replay jobs for a webhook subscription."""
        from .models import WebhookReplayJob

        webhook = self.get_object()
        jobs = WebhookReplayJob.objects.filter(subscription=webhook).order_by("-created_at")[:50]
        return Response(
            [WebhookReplayJobSerializer(j.to_status_dict()).data for j in jobs]
        )


class TeamViewSet(viewsets.ModelViewSet):
    """
    Teams: multi-tenant organization of contracts and members.

    - GET /teams/ — teams the current user belongs to
    - POST /teams/ — create a team (creator becomes admin)
    - POST /teams/{id}/members/ — add a user (admin only)
    """

    serializer_class = TeamSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [OrderingFilter]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]

    def get_queryset(self):
        return Team.objects.filter(memberships__user=self.request.user).distinct()

    @extend_schema(
        request=TeamMemberAddSerializer,
        responses={
            201: inline_serializer(
                name="TeamMemberAdded",
                fields={"status": serializers.CharField()},
            )
        },
    )
    @action(detail=True, methods=["post"], url_path="members")
    def members(self, request, pk=None):
        team = self.get_object()
        admin = TeamMembership.objects.filter(
            team=team,
            user=request.user,
            role=TeamMembership.Role.ADMIN,
        ).exists()
        if not admin:
            return Response(
                {"detail": "Only team admins can add members."},
                status=status.HTTP_403_FORBIDDEN,
            )
        ser = TeamMemberAddSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            new_user = User.objects.get(pk=ser.validated_data["user_id"])
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        _, created = TeamMembership.objects.get_or_create(
            team=team,
            user=new_user,
            defaults={"role": ser.validated_data["role"]},
        )
        if not created:
            return Response({"status": "already_member"}, status=status.HTTP_200_OK)
        return Response({"status": "created"}, status=status.HTTP_201_CREATED)


class APIKeyViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing API keys with tiered rate limiting.

    Endpoints:
    - GET /api-keys/ - List your API keys
    - POST /api-keys/ - Create a new API key
    - GET /api-keys/{id}/ - Get key details (key value shown only on creation)
    - DELETE /api-keys/{id}/ - Revoke an API key
    """

    serializer_class = APIKeySerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return APIKey.objects.filter(user=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        key_instance = serializer.save(user=self.request.user)
        # Expose plain-text key *only* in the creation response
        self.request._created_key_plain = key_instance.key

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        plain_key = getattr(request, "_created_key_plain", None)
        if plain_key:
            response.data["key"] = plain_key
        return response

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    request=RecordEventRequestSerializer,
    responses={
        202: inline_serializer(
            name="RecordEventAccepted",
            fields={
                "status": serializers.CharField(),
                "tx_hash": serializers.CharField(),
                "transaction_status": serializers.CharField(),
            },
        ),
        400: inline_serializer(
            name="RecordEventFailed",
            fields={
                "status": serializers.CharField(),
                "error": serializers.CharField(),
                "transaction_status": serializers.CharField(),
            },
        ),
        401: inline_serializer(
            name="Unauthorized",
            fields={
                "detail": serializers.CharField(),
            },
        ),
        500: inline_serializer(
            name="RecordEventError",
            fields={
                "status": serializers.CharField(),
                "error": serializers.CharField(),
            },
        ),
        429: inline_serializer(
            name="RateLimitExceeded",
            fields={
                "detail": serializers.CharField(),
            },
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([IngestRateThrottle, AnonRateThrottle, UserRateThrottle])
def record_event_view(request):
    """
    Record a new event by submitting a transaction to the SoroScan contract.

    Request body:
    {
        "contract_id": "CABC...",
        "event_type": "swap",
        "payload_hash": "abc123..."  // 64-char hex string
    }
    """
    serializer = RecordEventRequestSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data

    try:
        with tracer.start_as_current_span(
            "event.record",
            attributes={
                "contract_id": data["contract_id"],
                "event_type": data["event_type"],
            },
        ):
            client = SorobanClient()
            result = client.record_event(
                target_contract_id=data["contract_id"],
                event_type=data["event_type"],
                payload_hash_hex=data["payload_hash"],
            )

        if result.success:
            return Response(
                {
                    "status": "submitted",
                    "tx_hash": result.tx_hash,
                    "transaction_status": result.status,
                },
                status=status.HTTP_202_ACCEPTED,
            )
        else:
            return Response(
                {
                    "status": "failed",
                    "error": result.error,
                    "transaction_status": result.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    except Exception as e:
        logger.exception(
            "Failed to record event",
            extra={"contract_id": data.get("contract_id")},
        )
        return Response(
            {"status": "error", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@extend_schema(request=StructuredEventRequestSerializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([IngestRateThrottle, AnonRateThrottle, UserRateThrottle])
def record_structured_event_view(request):
    """Relay a versioned, deduplicated SC-38 event to the core contract."""
    serializer = StructuredEventRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    with tracer.start_as_current_span(
        "event.record",
        attributes={
            "contract_id": data["contract_id"],
            "event_type": data["event_type"],
        },
    ):
        result = SorobanClient().record_structured_event(
            target_contract_id=data["contract_id"],
            event_type=data["event_type"],
            payload_hash_hex=data["payload_hash"],
            schema_version=data["schema_version"],
            correlation_id_hex=data["correlation_id"],
        )
    if result.success:
        return Response(
            {
                "status": "submitted",
                "tx_hash": result.tx_hash,
                "transaction_status": result.status,
            },
            status=status.HTTP_202_ACCEPTED,
        )
    return Response(
        {"status": "failed", "error": result.error, "transaction_status": result.status},
        status=status.HTTP_400_BAD_REQUEST,
    )


@extend_schema(
    request=AddIndexerRequestSerializer,
    responses={
        202: inline_serializer(
            name="AddIndexerResponse",
            fields={
                "status": serializers.CharField(),
                "tx_hash": serializers.CharField(),
                "transaction_status": serializers.CharField(),
            },
        ),
        400: inline_serializer(
            name="AddIndexerFailed",
            fields={
                "status": serializers.CharField(),
                "error": serializers.CharField(),
                "transaction_status": serializers.CharField(),
            },
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([IngestRateThrottle, AnonRateThrottle, UserRateThrottle])
def add_indexer_view(request):
    """
    Authorize an indexer address on the SoroScan contract (SC-9).

    Request body:
    {
        "indexer_address": "GABC..."
    }
    """
    serializer = AddIndexerRequestSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    indexer_address = serializer.validated_data["indexer_address"]

    try:
        client = SorobanClient()
        result = client.add_indexer(indexer_address=indexer_address)

        if result.success:
            return Response(
                {
                    "status": "submitted",
                    "tx_hash": result.tx_hash,
                    "transaction_status": result.status,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        return Response(
            {
                "status": "failed",
                "error": result.error,
                "transaction_status": result.status,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    except Exception as e:
        logger.exception(
            "Failed to add indexer",
            extra={"indexer_address": indexer_address},
        )
        return Response(
            {"status": "error", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="indexer_address",
            type=str,
            location=OpenApiParameter.QUERY,
            required=True,
        ),
    ],
    responses={
        200: inline_serializer(
            name="IsIndexerResponse",
            fields={
                "is_indexer": serializers.BooleanField(),
            },
        ),
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def is_indexer_view(request):
    """Check whether an address is authorized on the SoroScan contract (SC-15)."""
    indexer_address = request.query_params.get("indexer_address")
    if not indexer_address:
        return Response(
            {"indexer_address": ["This field is required."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    client = SorobanClient()
    success, value = client.is_indexer(indexer_address)
    if not success:
        return Response(
            {"status": "error", "error": str(value)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response({"is_indexer": bool(value)})


@extend_schema(
    responses={
        200: inline_serializer(
            name="GetAdminResponse",
            fields={
                "admin_address": serializers.CharField(allow_null=True),
            },
        ),
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_admin_view(request):
    """Return the current SoroScan contract admin address (SC-15)."""
    client = SorobanClient()
    success, value = client.get_admin()
    if not success:
        return Response(
            {"status": "error", "error": str(value)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response({"admin_address": value})


@extend_schema(
    responses=inline_serializer(
        name="WebhookSigningPublicKeyResponse",
        fields={
            "algorithm": serializers.CharField(),
            "public_key": serializers.CharField(),
            "header": serializers.CharField(),
            "format": serializers.CharField(),
        },
    )
)
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([UnauthenticatedIPRateThrottle])
def webhook_signing_public_key_view(request):
    """Return the platform Ed25519 public key used for webhook X-Signature headers."""
    return Response(
        {
            "algorithm": "ed25519",
            "public_key": public_key_base64(),
            "header": "X-Signature",
            "format": "ed25519=<base64-signature>",
        }
    )


@extend_schema(
    responses=inline_serializer(
        name="HealthCheckResponse",
        fields={
            "status": serializers.CharField(),
            "service": serializers.CharField(),
        },
    )
)
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([UnauthenticatedIPRateThrottle])
def health_check(request):
    """Health check endpoint."""
    return Response({"status": "healthy", "service": "soroscan"})


@extend_schema(
    responses=inline_serializer(
        name="NetworkListResponse",
        fields={
            "networks": serializers.ListField(
                child=inline_serializer(
                    name="NetworkEntry",
                    fields={
                        "id": serializers.CharField(),
                        "name": serializers.CharField(),
                        "rpc_url": serializers.CharField(),
                        "network_passphrase": serializers.CharField(),
                    },
                )
            )
        },
    )
)
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([UnauthenticatedIPRateThrottle])
def networks_view(request):
    """Return the list of Soroban networks supported by this indexer."""
    networks = getattr(settings, "SOROBAN_NETWORKS", [])
    return Response({"networks": networks})


@extend_schema(
    responses=inline_serializer(
        name="ContractStatusResponse",
        fields={
            "total_contracts": serializers.IntegerField(),
            "active_contracts": serializers.IntegerField(),
            "paused_contracts": serializers.IntegerField(),
            "total_events_indexed": serializers.IntegerField(),
            "last_event_timestamp": serializers.DateTimeField(allow_null=True),
            "events_per_minute": serializers.IntegerField(),
        },
    )
)
@api_view(["GET"])
@cache_result(ttl=60)
def contract_status(request):
    """Return aggregate contract and event indexing snapshot statistics."""
    contract_agg = TrackedContract.objects.aggregate(
        total_contracts=Count("id"),
        active_contracts=Count("id", filter=Q(is_active=True)),
        paused_contracts=Count("id", filter=Q(is_active=False)),
    )

    one_minute_ago = timezone.now() - timedelta(seconds=60)
    event_agg = ContractEvent.objects.aggregate(
        total_events_indexed=Count("id"),
        last_event_timestamp=Max("timestamp"),
        events_per_minute=Count("id", filter=Q(timestamp__gte=one_minute_ago)),
    )

    return Response(
        {
            "total_contracts": contract_agg["total_contracts"] or 0,
            "active_contracts": contract_agg["active_contracts"] or 0,
            "paused_contracts": contract_agg["paused_contracts"] or 0,
            "total_events_indexed": event_agg["total_events_indexed"] or 0,
            "last_event_timestamp": event_agg["last_event_timestamp"],
            "events_per_minute": event_agg["events_per_minute"] or 0,
        }
    )


@extend_schema(
    responses=inline_serializer(
        name="VulnerabilityImpactResponse",
        fields={
            "contract_id": serializers.CharField(),
            "affected_contracts": serializers.JSONField(),
            "impacted_count": serializers.IntegerField(),
            "risk_score": serializers.FloatField(),
            "impact_level": serializers.CharField(),
            "has_cycles": serializers.BooleanField(),
        },
    )
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def vulnerability_impact_view(request, contract_id: str):
    from .tasks import assess_vulnerability_impact

    result = assess_vulnerability_impact(contract_id)
    return Response(result)


@extend_schema(
    parameters=[
        inline_serializer(
            name="OrganizationCostBreakdownParams",
            fields={
                "organization_id": serializers.IntegerField(required=False),
                "month": serializers.CharField(required=False),
            },
        )
    ],
    responses=inline_serializer(
        name="OrganizationCostBreakdownResponse",
        fields={
            "results": serializers.JSONField(),
        },
    ),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def organization_cost_breakdown_view(request):
    """Admin endpoint exposing per-organization cost snapshots and budget state."""
    if not request.user.is_staff:
        return Response({"error": "Admin access required"}, status=status.HTTP_403_FORBIDDEN)

    snapshots = OrganizationCostSnapshot.objects.select_related("organization").all()
    org_id = request.query_params.get("organization_id")
    month = request.query_params.get("month")

    if org_id:
        snapshots = snapshots.filter(organization_id=org_id)
    if month:
        try:
            year, month_num = month.split("-", 1)
            snapshots = snapshots.filter(month__year=int(year), month__month=int(month_num))
        except (TypeError, ValueError):
            return Response(
                {"error": "month must be in YYYY-MM format"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    budgets = {
        budget.organization_id: OrganizationBudgetSerializer(budget).data
        for budget in OrganizationBudget.objects.select_related("organization").all()
    }

    payload = []
    for snapshot in snapshots.order_by("-month", "organization__name"):
        item = OrganizationCostSnapshotSerializer(snapshot).data
        item["budget"] = budgets.get(snapshot.organization_id)
        payload.append(item)

    return Response({"results": payload})


@extend_schema(
    summary="Get or update organization CORS origins",
    description=(
        "GET returns the current list of allowed CORS origins for an organization. "
        "PATCH replaces the entire list. "
        "Only the organization owner and admins may update this setting. "
        "Staff users may access any organization."
    ),
    request=OrganizationCorsSerializer,
    responses={200: OrganizationCorsSerializer},
)
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def organization_cors_view(request, pk: int):
    """
    Retrieve or update the per-organization CORS allowed origins.

    - **GET** — returns ``{id, name, cors_origins}`` for the organization.
    - **PATCH** — replaces ``cors_origins`` with the supplied list.

    Permission rules:
    - Staff users can access any organization.
    - Non-staff users may only access organizations where they hold an
      ``owner`` or ``admin`` membership role.
    """
    try:
        org = Organization.objects.get(pk=pk)
    except Organization.DoesNotExist:
        return Response({"error": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

    # Permission check: staff OR org owner/admin.
    if not request.user.is_staff:
        has_permission = OrganizationMembership.objects.filter(
            organization=org,
            user=request.user,
            role__in=[OrganizationMembership.Role.OWNER, OrganizationMembership.Role.ADMIN],
        ).exists()
        if not has_permission:
            return Response(
                {"error": "You do not have permission to manage CORS settings for this organization."},
                status=status.HTTP_403_FORBIDDEN,
            )

    if request.method == "GET":
        serializer = OrganizationCorsSerializer(org)
        return Response(serializer.data)

    # PATCH
    serializer = OrganizationCorsSerializer(org, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    serializer.save()
    logger.info(
        "cors_origins updated for org=%s by user=%s",
        org.slug,
        request.user.username,
    )
    return Response(serializer.data)


def contract_timeline_view(request, contract_id: str):
    """Redirect timeline requests to the frontend contract timeline page."""
    contract = get_cached_contract(contract_id)
    if not contract:
        from django.http import Http404
        raise Http404
    frontend_base = _frontend_base_url()
    return redirect(f"{frontend_base}/contracts/{contract.contract_id}/timeline")


@extend_schema(
    responses=inline_serializer(
        name="TransactionEventsResponse",
        fields={
            "transaction_id": serializers.CharField(),
            "event_count": serializers.IntegerField(),
            "events": ContractEventSerializer(many=True),
        },
    ),
)
@api_view(["GET"])
@permission_classes([AllowAny])
def transaction_events_view(request, tx_id: str):
    """Return all events participating in the same atomic transaction."""
    events = list(
        ContractEvent.objects.select_related("contract")
        .filter(tx_hash=tx_id)
        .order_by("ledger", "event_index", "id")
    )
    serializer = ContractEventSerializer(events, many=True)
    return Response(
        {
            "transaction_id": tx_id,
            "event_count": len(events),
            "events": serializer.data,
        }
    )


def contract_event_explorer_view(request, contract_id: str):
    """Redirect explorer requests to the frontend event explorer page."""
    contract = get_cached_contract(contract_id)
    if not contract:
        from django.http import Http404
        raise Http404
    frontend_base = _frontend_base_url()
    return redirect(f"{frontend_base}/contracts/{contract.contract_id}/events/explorer")


@extend_schema(
    responses=inline_serializer(
        name="ContractEventTypesResponse",
        fields={
            "event_type": serializers.CharField(),
            "count": serializers.IntegerField(),
            "first_seen": serializers.DateTimeField(allow_null=True),
            "last_seen": serializers.DateTimeField(allow_null=True),
        },
        many=True,
    ),
)
@api_view(["GET"])
@permission_classes([AllowAny])
def contract_event_types_view(request, contract_id: str):
    """Get event types and their counts for a specific contract."""
    contract = get_cached_contract(contract_id)
    if not contract:
        from django.http import Http404
        raise Http404
    
    cache_key = stable_cache_key("contract_event_types", {"contract_id": contract_id})
    
    def _build():
        return list(
            ContractEvent.objects.filter(contract=contract)
            .values("event_type")
            .annotate(
                count=Count("id"),
                first_seen=Min("timestamp"),
                last_seen=Max("timestamp")
            )
            .order_by("-count")
        )
    
    result = get_or_set_json(cache_key, 60, _build)
    return Response(result)


MAX_RECENT_EVENTS_LIMIT = 20


@extend_schema(
    parameters=[
        inline_serializer(
            name="ContractRecentEventsParams",
            fields={
                "limit": serializers.IntegerField(required=False),
            },
        )
    ],
    responses=ContractEventSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([AllowAny])
def contract_recent_events_view(request, contract_id: str):
    """Get the most recent events for a specific contract, newest first (SC-30).

    Mirrors the bounded on-chain recent-events ring buffer exposed by the
    SoroScan core contract's ``recent_events`` function, backed here by the
    indexed event history for richer payload data.
    """
    contract = get_cached_contract(contract_id)
    if not contract:
        from django.http import Http404
        raise Http404

    try:
        limit = int(request.query_params.get("limit", 10))
    except (TypeError, ValueError):
        return Response(
            {"detail": "limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST
        )

    if limit <= 0 or limit > MAX_RECENT_EVENTS_LIMIT:
        return Response(
            {
                "detail": f"limit must be between 1 and {MAX_RECENT_EVENTS_LIMIT}",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    cache_key = stable_cache_key(
        "contract_recent_events", {"contract_id": contract_id, "limit": limit}
    )

    def _build():
        events = (
            ContractEvent.objects.select_related("contract")
            .filter(contract=contract)
            .order_by("-ledger", "-event_index", "-id")[:limit]
        )
        return ContractEventSerializer(events, many=True).data

    result = get_or_set_json(cache_key, 15, _build)
    return Response(result)


@extend_schema(
    parameters=[
        inline_serializer(
            name="EventTypeStatisticsParams",
            fields={
                "contract_id": serializers.CharField(required=False),
            },
        )
    ],
    responses=inline_serializer(
        name="EventTypeStatisticsResponse",
        fields={
            "contract_id": serializers.CharField(allow_null=True),
            "total_events": serializers.IntegerField(),
            "event_types": serializers.JSONField(),
        },
    ),
)
@api_view(["GET"])
@permission_classes([AllowAny])
def event_type_statistics_view(request):
    """Return event type distribution globally or for a specific contract."""
    contract_id = request.query_params.get("contract_id")

    contract = None
    if contract_id:
        contract = get_cached_contract(contract_id)
        if not contract:
            from django.http import Http404
            raise Http404

    cache_key = stable_cache_key(
        "event_type_statistics",
        {"contract_id": contract_id or "all"},
    )

    def _build():
        events = ContractEvent.objects.select_related("contract").all()

        if contract:
            events = events.filter(contract=contract)

        total_events = events.count()

        event_types = list(
            events.values("contract__contract_id", "event_type")
            .annotate(
                count=Count("id"),
                first_seen=Min("timestamp"),
                last_seen=Max("timestamp"),
            )
            .order_by("contract__contract_id", "-count", "event_type")
        )

        return {
            "contract_id": contract_id if contract_id else None,
            "total_events": total_events,
            "event_types": [
                {
                    "contract_id": item["contract__contract_id"],
                    "event_type": item["event_type"],
                    "count": item["count"],
                    "first_seen": item["first_seen"],
                    "last_seen": item["last_seen"],
                }
                for item in event_types
            ],
        }

    payload = get_or_set_json(cache_key, query_cache_ttl(), _build)
    return Response(payload)


@extend_schema(
    parameters=[
        inline_serializer(
            name="RestoreArchiveParams",
            fields={"batch_id": serializers.IntegerField()},
        )
    ],
    responses={
        200: inline_serializer(
            name="RestoreArchiveResponse",
            fields={
                "status": serializers.CharField(),
                "restored_count": serializers.IntegerField(),
                "batch_id": serializers.IntegerField(),
            },
        ),
        404: inline_serializer(
            name="RestoreNotFound",
            fields={"detail": serializers.CharField()},
        ),
        429: inline_serializer(
            name="RestoreRateLimited",
            fields={"detail": serializers.CharField()},
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([UserRateThrottle])
def restore_archived_events(request):
    """
    Retrieve an archived event batch from S3 and re-import events into PostgreSQL.

    Query params:
    - batch_id: ID of the ArchivedEventBatch to restore
    """
    batch_id = request.query_params.get("batch_id") or request.data.get("batch_id")
    if not batch_id:
        return Response({"detail": "batch_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    batch = get_object_or_404(ArchivedEventBatch, id=batch_id)

    if batch.status == ArchivedEventBatch.STATUS_RESTORED:
        return Response(
            {"detail": "Batch already restored.", "batch_id": batch.id},
            status=status.HTTP_200_OK,
        )

    try:
        import boto3  # noqa: PLC0415
        import gzip  # noqa: PLC0415

        s3 = boto3.client(
            "s3",
            region_name=getattr(settings, "AWS_S3_REGION_NAME", None),
            endpoint_url=getattr(settings, "AWS_S3_ENDPOINT_URL", None),
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
        )
        policy = batch.policy
        obj = s3.get_object(Bucket=policy.s3_bucket, Key=batch.s3_key)
        compressed = obj["Body"].read()
        raw_json = gzip.decompress(compressed)
        rows = json.loads(raw_json)

    except Exception as exc:
        logger.exception("Failed to download archive batch %s from S3", batch_id)
        return Response(
            {"detail": f"S3 retrieval failed: {str(exc)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    restored_count = 0
    for row in rows:
        try:
            contract = get_cached_contract(row["contract__contract_id"])
            if not contract:
                raise TrackedContract.DoesNotExist(f"Contract {row['contract__contract_id']} not found")
            ContractEvent.objects.get_or_create(
                contract=contract,
                ledger=row["ledger"],
                event_index=row["event_index"],
                defaults={
                    "event_type": row["event_type"],
                    "payload": row["payload"],
                    "payload_hash": row.get("payload_hash", ""),
                    "timestamp": row["timestamp"],
                    "tx_hash": row.get("tx_hash", ""),
                },
            )
            restored_count += 1
        except Exception:
            logger.warning("Skipped row during restore: %s", row.get("id"), exc_info=True)

    batch.status = ArchivedEventBatch.STATUS_RESTORED
    batch.save(update_fields=["status"])

    from .models import ArchivalAuditLog  # noqa: PLC0415
    ArchivalAuditLog.objects.create(
        action=ArchivalAuditLog.ACTION_RESTORE,
        batch=batch,
        policy=batch.policy,
        event_count=restored_count,
        detail=f"Restored by user {request.user.id}",
        performed_by=request.user,
    )

    return Response(
        {"status": "restored", "restored_count": restored_count, "batch_id": batch.id},
        status=status.HTTP_200_OK,
    )


@extend_schema(
    parameters=[
        inline_serializer(
            name="AuditTrailParams",
            fields={
                "action": serializers.CharField(required=False),
                "object_type": serializers.CharField(required=False),
                "object_id": serializers.CharField(required=False),
                "user": serializers.CharField(required=False),
                "since": serializers.DateTimeField(required=False),
                "until": serializers.DateTimeField(required=False),
                "limit": serializers.IntegerField(required=False),
            },
        )
    ],
    responses=AdminActionSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def audit_trail_view(request):
    """Query immutable admin audit trail entries."""
    qs = AdminAction.objects.select_related("user").all().order_by("-timestamp")

    action = request.query_params.get("action")
    object_type = request.query_params.get("object_type")
    object_id = request.query_params.get("object_id")
    username = request.query_params.get("user")
    since = request.query_params.get("since")
    until = request.query_params.get("until")

    if action:
        qs = qs.filter(action=action)
    if object_type:
        qs = qs.filter(object_type=object_type)
    if object_id:
        qs = qs.filter(object_id=object_id)
    if username:
        qs = qs.filter(user__username=username)
    if since:
        qs = qs.filter(timestamp__gte=since)
    if until:
        qs = qs.filter(timestamp__lte=until)

    try:
        limit = max(1, min(int(request.query_params.get("limit", 100)), 1000))
    except (TypeError, ValueError):
        limit = 100

    serializer = AdminActionSerializer(qs[:limit], many=True)
    return Response(serializer.data)


@extend_schema(
    responses=inline_serializer(
        name="AdminIngestErrorsResponse",
        fields={
            "error_type": serializers.CharField(),
            "contract_id": serializers.CharField(allow_null=True),
            "count": serializers.IntegerField(),
            "last_occurrence": serializers.DateTimeField(allow_null=True),
            "sample_error": serializers.CharField(allow_null=True),
        },
        many=True,
    ),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_ingest_errors_view(request):
    """Get recent ingest errors (admin only)."""
    if not request.user.is_staff:
        return Response({"error": "Admin access required"}, status=status.HTTP_403_FORBIDDEN)
    
    # Last 24 hours
    since = timezone.now() - timezone.timedelta(hours=24)
    
    # Group by error_type + contract_id and aggregate
    errors = (
        IngestError.objects.filter(created_at__gte=since)
        .values("error_type", "contract_id")
        .annotate(
            count=Count("id"),
            last_occurrence=Max("created_at"),
            sample_error=Max("sample_error")  # Get one sample error message
        )
        .order_by("-count")
    )
    
    return Response(list(errors))


@extend_schema(
    responses=inline_serializer(
        name="RateLimitAnalyticsResponse",
        fields={
            "window_hours": serializers.IntegerField(),
            "generated_at": serializers.DateTimeField(),
            "api_keys": serializers.JSONField(),
        },
    )
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def rate_limit_analytics_view(request):
    """Return 7-day API key usage analytics from Redis-backed counters."""
    from django.core.cache import cache
    from soroscan.throttles import _BUCKET_TTL

    now_bucket = int(time.time()) // _BUCKET_TTL
    window_hours = 24 * 7
    keys = APIKey.objects.filter(user=request.user, is_active=True).order_by("name")
    results = []

    for key in keys:
        hourly_hits = []
        overages = 0
        for offset in range(window_hours - 1, -1, -1):
            bucket = now_bucket - offset
            history_key = f"soroscan_api_key_quota_history:{key.id}:{bucket}"
            hits = int(cache.get(history_key, 0) or 0)
            if hits > key.quota_per_hour:
                overages += 1
            hourly_hits.append(hits)

        total_hits = sum(hourly_hits)
        avg_hits = (total_hits / window_hours) if window_hours else 0.0
        quota = key.quota_per_hour
        quota_used_percent = (avg_hits / quota * 100.0) if quota > 0 else 0.0
        projected_next_24h_hits = int(round(avg_hits * 24))
        projected_overage = projected_next_24h_hits > quota

        results.append(
            {
                "api_key_id": key.id,
                "name": key.name,
                "tier": key.tier,
                "quota_per_hour": quota,
                "hourly_hits": hourly_hits,
                "avg_hits_per_hour": round(avg_hits, 2),
                "quota_used_percent": round(quota_used_percent, 2),
                "overage_events": overages,
                "projected_next_24h_hits": projected_next_24h_hits,
                "projected_overage": projected_overage,
            }
        )

    return Response(
        {
            "window_hours": window_hours,
            "generated_at": timezone.now(),
            "api_keys": results,
        }
    )


# ---------------------------------------------------------------------------
# Issue #280: GDPR — deletion requests & compliance export
# ---------------------------------------------------------------------------

class DataDeletionRequestSerializer(serializers.ModelSerializer):
    requested_by = serializers.CharField(source="requested_by.username", read_only=True)
    contract_ids = serializers.SerializerMethodField()

    class Meta:
        from .models import DataDeletionRequest
        model = DataDeletionRequest
        fields = [
            "id", "requested_by", "subject_identifier", "contract_ids",
            "status", "events_deleted", "error_message", "requested_at", "completed_at",
        ]
        read_only_fields = ["status", "events_deleted", "error_message", "requested_at", "completed_at"]

    def get_contract_ids(self, obj):
        return list(obj.contracts.values_list("contract_id", flat=True))


@extend_schema(
    request=inline_serializer(
        name="DeletionRequestCreate",
        fields={
            "subject_identifier": serializers.CharField(),
            "contract_ids": serializers.ListField(
                child=serializers.CharField(),
                required=False,
            ),
        },
    ),
    responses=DataDeletionRequestSerializer(),
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def deletion_requests_view(request):
    """
    GET  /api/deletion-requests/   — list all requests (staff) or own requests
    POST /api/deletion-requests/   — submit a new GDPR deletion request
    """
    from .models import DataDeletionRequest, TrackedContract

    if request.method == "GET":
        qs = (
            DataDeletionRequest.objects.all()
            if request.user.is_staff
            else DataDeletionRequest.objects.filter(requested_by=request.user)
        )
        serializer = DataDeletionRequestSerializer(qs, many=True)
        return Response(serializer.data)

    # POST — create a new deletion request
    subject = request.data.get("subject_identifier", "").strip()
    if not subject:
        return Response({"error": "subject_identifier is required"}, status=status.HTTP_400_BAD_REQUEST)

    contract_ids = request.data.get("contract_ids", [])
    req = DataDeletionRequest.objects.create(
        requested_by=request.user,
        subject_identifier=subject,
    )
    if contract_ids:
        contracts = TrackedContract.objects.filter(contract_id__in=contract_ids)
        req.contracts.set(contracts)

    return Response(DataDeletionRequestSerializer(req).data, status=status.HTTP_201_CREATED)


@extend_schema(
    parameters=[
        inline_serializer(
            name="ComplianceExportParams",
            fields={
                "from": serializers.DateTimeField(required=False),
                "to": serializers.DateTimeField(required=False),
            },
        )
    ],
    responses={200: {"type": "string", "format": "binary", "description": "CSV audit trail export"}},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def compliance_export_view(request):
    """
    GET /api/compliance-export/?from={iso}&to={iso}
    Returns a CSV audit trail of AuditLog entries for compliance auditors.
    Staff only.
    """
    import csv
    from django.http import StreamingHttpResponse
    from .models import AuditLog

    if not request.user.is_staff:
        return Response({"error": "Staff only"}, status=status.HTTP_403_FORBIDDEN)

    qs = AuditLog.objects.select_related("user").order_by("timestamp")
    from_ts = request.query_params.get("from")
    to_ts = request.query_params.get("to")
    if from_ts:
        qs = qs.filter(timestamp__gte=from_ts)
    if to_ts:
        qs = qs.filter(timestamp__lte=to_ts)

    def rows():
        yield ["id", "timestamp", "user", "action", "model_name", "object_id", "ip_address", "changes"]
        for entry in qs.iterator():
            yield [
                entry.id,
                entry.timestamp.isoformat(),
                entry.user.username if entry.user else "",
                entry.action,
                entry.model_name,
                entry.object_id,
                entry.ip_address or "",
                json.dumps(entry.changes),
            ]

    class EchoBuffer:
        def write(self, value):
            return value

    writer = csv.writer(EchoBuffer())
    response = StreamingHttpResponse(
        (writer.writerow(row) for row in rows()),
        content_type="text/csv",
    )
    response["Content-Disposition"] = 'attachment; filename="compliance_audit.csv"'
    return response


# ---------------------------------------------------------------------------
# Issue #592: Batch webhook delivery status
# ---------------------------------------------------------------------------

@extend_schema(
    request=inline_serializer(
        name="WebhookBatchStatusRequest",
        fields={
            "delivery_ids": serializers.ListField(
                child=serializers.IntegerField(),
                help_text="WebhookDeliveryLog primary keys to look up",
            ),
        },
    ),
    responses={
        200: inline_serializer(
            name="WebhookBatchStatusResponse",
            fields={
                "deliveries": serializers.ListField(
                    child=inline_serializer(
                        name="WebhookDeliveryStatusEntry",
                        fields={
                            "id": serializers.IntegerField(),
                            "subscription_id": serializers.IntegerField(allow_null=True),
                            "success": serializers.BooleanField(allow_null=True),
                            "http_status_code": serializers.IntegerField(allow_null=True),
                            "status": serializers.CharField(),
                            "attempt_number": serializers.IntegerField(allow_null=True),
                            "timestamp": serializers.DateTimeField(allow_null=True),
                        },
                    )
                ),
            },
        ),
        400: inline_serializer(
            name="WebhookBatchStatusBadRequest",
            fields={"detail": serializers.CharField()},
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@validate_webhook_signature(lambda request: getattr(settings, "INDEXER_SECRET_KEY", "") or "")
def webhook_batch_delivery_status_view(request):
    """
    POST /api/webhooks/deliveries/batch-status/

    Look up delivery status for multiple WebhookDeliveryLog records in one query.
    """
    delivery_ids = request.data.get("delivery_ids")
    if not isinstance(delivery_ids, list) or not delivery_ids:
        return Response(
            {"detail": "delivery_ids must be a non-empty list of integers."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        parsed_ids = [int(delivery_id) for delivery_id in delivery_ids]
    except (TypeError, ValueError):
        return Response(
            {"detail": "delivery_ids must contain only integers."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if len(parsed_ids) > 200:
        return Response(
            {"detail": "delivery_ids may contain at most 200 ids."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    logs = (
        WebhookDeliveryLog.objects.filter(pk__in=parsed_ids)
        .only(
            "id",
            "subscription_id",
            "success",
            "status_code",
            "attempt_number",
            "timestamp",
        )
        .order_by("id")
    )
    by_id = {log.id: log for log in logs}

    deliveries = []
    for delivery_id in parsed_ids:
        log = by_id.get(delivery_id)
        if log is None:
            deliveries.append(
                {
                    "id": delivery_id,
                    "subscription_id": None,
                    "success": None,
                    "http_status_code": None,
                    "status": "not_found",
                    "attempt_number": None,
                    "timestamp": None,
                }
            )
            continue

        deliveries.append(
            {
                "id": log.id,
                "subscription_id": log.subscription_id,
                "success": log.success,
                "http_status_code": log.status_code,
                "status": "success" if log.success else "failed",
                "attempt_number": log.attempt_number,
                "timestamp": log.timestamp,
            }
        )

    return Response({"deliveries": deliveries})


@extend_schema(
    parameters=[
        inline_serializer(
            name="WebhookDeliveryMetricsParams",
            fields={
                "subscription_id": serializers.IntegerField(required=False),
                "minutes": serializers.IntegerField(required=False),
                "recent": serializers.IntegerField(required=False),
            },
        )
    ],
    responses=inline_serializer(
        name="WebhookDeliveryMetricsResponse",
        fields={
            "total_deliveries": serializers.IntegerField(),
            "success_count": serializers.IntegerField(),
            "success_rate_percent": serializers.FloatField(allow_null=True),
            "avg_latency_ms": serializers.FloatField(allow_null=True),
            "recent_deliveries": serializers.JSONField(),
            "failure_breakdown": serializers.JSONField(),
            "time_range": serializers.JSONField(),
        },
    ),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@validate_webhook_signature(lambda request: getattr(settings, "INDEXER_SECRET_KEY", "") or "")
def webhook_delivery_metrics_view(request):
    """
    GET /api/webhooks/deliveries/metrics/

    Returns webhook delivery health metrics.

    Query params:
    - subscription_id: optional integer to restrict to a specific subscription
    - minutes: optional integer for a relative time range (last N minutes)
    - recent: optional integer number of recent deliveries to include (default 10)
    """
    now = timezone.now()

    # Time range: prefer `minutes` when provided, otherwise default to 24 hours
    minutes = request.query_params.get("minutes")
    try:
        minutes = int(minutes) if minutes is not None else None
    except (TypeError, ValueError):
        return Response({"detail": "minutes must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

    if minutes is not None and minutes <= 0:
        return Response({"detail": "minutes must be > 0."}, status=status.HTTP_400_BAD_REQUEST)

    if minutes is None:
        start = now - timedelta(hours=24)
    else:
        start = now - timedelta(minutes=minutes)

    qs = WebhookDeliveryLog.objects.filter(timestamp__gte=start, timestamp__lte=now)

    subscription_id = request.query_params.get("subscription_id")
    if subscription_id is not None:
        try:
            subpk = int(subscription_id)
        except (TypeError, ValueError):
            return Response({"detail": "subscription_id must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
        qs = qs.filter(subscription_id=subpk)

    # Aggregates
    total = qs.count()
    success_count = qs.filter(success=True).count()
    success_rate = (success_count / total) * 100.0 if total > 0 else None
    avg_latency = qs.aggregate(avg_latency_ms=Avg("latency_ms"))["avg_latency_ms"]

    # Recent deliveries
    try:
        recent_n = int(request.query_params.get("recent", 10))
    except (TypeError, ValueError):
        recent_n = 10

    recent_qs = qs.order_by("-timestamp")[: recent_n]
    recent_deliveries = list(
        recent_qs.values(
            "id",
            "subscription_id",
            "status_code",
            "success",
            "error",
            "attempt_number",
            "timestamp",
        )
    )

    # Failure breakdown by status_code (including null network errors)
    failed = qs.filter(success=False)
    breakdown_qs = (
        failed.values("status_code")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    failure_breakdown = []
    for row in breakdown_qs:
        code = row["status_code"]
        key = "network_error" if code is None else str(code)
        failure_breakdown.append({"code": key, "count": row["count"]})

    resp = {
        "total_deliveries": total,
        "success_count": success_count,
        "success_rate_percent": success_rate,
        "avg_latency_ms": avg_latency,
        "recent_deliveries": recent_deliveries,
        "failure_breakdown": failure_breakdown,
        "time_range": {"start": start, "end": now},
    }

    return Response(resp)


# ---------------------------------------------------------------------------
# Issue #284: Contract deployment timeline
# ---------------------------------------------------------------------------

class ContractDeploymentSerializer(serializers.ModelSerializer):
    class Meta:
        from .models import ContractDeployment
        model = ContractDeployment
        fields = [
            "id", "bytecode_hash", "ledger_deployed", "deployer_address",
            "is_upgrade", "tx_hash", "notes", "detected_at",
        ]


class ContractABIVersionSerializer(serializers.ModelSerializer):
    class Meta:
        from .models import ContractABIVersion
        model = ContractABIVersion
        fields = [
            "id", "version_number", "valid_from_ledger", "valid_to_ledger",
            "has_breaking_changes", "breaking_change_details", "created_at",
        ]


@extend_schema(
    responses=inline_serializer(
        name="DeploymentTimelineResponse",
        fields={
            "contract_id": serializers.CharField(),
            "deployments": ContractDeploymentSerializer(many=True),
            "abi_versions": ContractABIVersionSerializer(many=True),
            "compatibility_warnings": serializers.JSONField(),
        },
    ),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def deployment_timeline_view(request, contract_id):
    """
    GET /api/contracts/<contract_id>/deployments/
    Returns the full deployment history and ABI versions for a contract.
    Includes compatibility warnings for breaking ABI changes.
    """
    from .models import ContractDeployment, ContractABIVersion

    contract = get_cached_contract(contract_id)
    if not contract:
        from django.http import Http404
        raise Http404
    deployments = ContractDeployment.objects.filter(contract=contract).order_by("ledger_deployed")
    abi_versions = ContractABIVersion.objects.filter(contract=contract).order_by("version_number")

    warnings = []
    for av in abi_versions:
        if av.has_breaking_changes:
            warnings.append({
                "abi_version": av.version_number,
                "ledger": av.valid_from_ledger,
                "detail": av.breaking_change_details or "Breaking ABI change detected",
            })

    return Response({
        "contract_id": contract_id,
        "deployments": ContractDeploymentSerializer(deployments, many=True).data,
        "abi_versions": ContractABIVersionSerializer(abi_versions, many=True).data,
        "compatibility_warnings": warnings,
    })


# ---------------------------------------------------------------------------
# Issue: Contract Identity Endpoint
# ---------------------------------------------------------------------------

@extend_schema(
    responses=inline_serializer(
        name="ContractIdentityResponse",
        fields={
            "contract_id": serializers.CharField(),
            "network_passphrase": serializers.CharField(),
            "rpc_url": serializers.CharField(),
        },
    )
)
@api_view(["GET"])
@permission_classes([AllowAny])
def contract_identity_view(request):
    """
    GET /api/contract/identity/
    Returns the SoroScan contract ID and network information.
    Allows clients to verify where events are coming from.
    """
    return Response({
        "contract_id": getattr(settings, "SOROSCAN_CONTRACT_ID", ""),
        "network_passphrase": getattr(settings, "STELLAR_NETWORK_PASSPHRASE", ""),
        "rpc_url": getattr(settings, "SOROBAN_RPC_URL", ""),
    })


# ---------------------------------------------------------------------------
# Issue: Supported event schema (ABI) versions
# ---------------------------------------------------------------------------

# Canonical list of Soroban contract event schema (ABI) versions that the
# indexer is able to decode and validate.  New versions are appended as the
# event format evolves; ``latest`` advertises the recommended version for new
# events.  Each entry documents the supported ``schema_version`` value used by
# SC-38 structured events.
SUPPORTED_EVENT_SCHEMA_VERSIONS: list[dict[str, object]] = [
    {
        "version": 1,
        "name": "SoroScan Event Schema v1",
        "description": (
            "Initial event schema version covering the SC-20, SC-21, SC-31, "
            "SC-36 and SC-38 contract standards."
        ),
        "status": "supported",
    },
]


@extend_schema(
    responses=inline_serializer(
        name="SchemaVersionsResponse",
        fields={
            "versions": serializers.ListField(
                child=inline_serializer(
                    name="SchemaVersionEntry",
                    fields={
                        "version": serializers.IntegerField(),
                        "name": serializers.CharField(),
                        "description": serializers.CharField(),
                        "status": serializers.CharField(),
                    },
                )
            ),
            "latest": serializers.IntegerField(),
            "count": serializers.IntegerField(),
        },
    ),
    description=(
        "Return the list of Soroban contract event schema (ABI) versions that "
        "this indexer supports for decoding and validation."
    ),
)
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([UnauthenticatedIPRateThrottle])
def schema_versions_view(request):
    """
    GET /api/schema/versions/

    Returns the supported Soroban contract event schema (ABI) versions.
    """
    latest = max(
        (entry["version"] for entry in SUPPORTED_EVENT_SCHEMA_VERSIONS),
        default=None,
    )
    return Response(
        {
            "versions": SUPPORTED_EVENT_SCHEMA_VERSIONS,
            "latest": latest,
            "count": len(SUPPORTED_EVENT_SCHEMA_VERSIONS),
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([UserRateThrottle])
def bulk_contract_metadata_view(request):
    """
    POST /api/ingest/contracts/metadata/bulk/

    Accepts a list of contract IDs and returns metadata for each.
    Maximum 50 contract IDs per request.
    """
    from .models import ContractMetadata
    from .serializers import BulkContractMetadataRequestSerializer, ContractMetadataSerializer

    req_serializer = BulkContractMetadataRequestSerializer(data=request.data)
    req_serializer.is_valid(raise_exception=True)
    contract_ids = req_serializer.validated_data["contract_ids"]

    metadata_qs = ContractMetadata.objects.select_related("contract").filter(
        contract__contract_id__in=contract_ids
    )
    metadata_map = {m.contract.contract_id: m for m in metadata_qs}

    results = []
    missing = []
    for cid in contract_ids:
        if cid in metadata_map:
            results.append(ContractMetadataSerializer(metadata_map[cid]).data)
        else:
            missing.append(cid)

    return Response({
        "results": results,
        "missing": missing,
        "total_found": len(results),
        "total_missing": len(missing),
    })


# ---------------------------------------------------------------------------
# Issue #491: EXPLAIN ANALYZE endpoint for query debugging
# ---------------------------------------------------------------------------

_ALLOWED_STATEMENTS = re.compile(
    r"^\s*(SELECT|WITH|EXPLAIN)\b",
    re.IGNORECASE,
)


@extend_schema(
    request=inline_serializer(
        name="DBExplainRequest",
        fields={
            "query": serializers.CharField(
                help_text="SQL SELECT statement to explain",
            ),
            "analyze": serializers.BooleanField(
                default=False,
                help_text="If true, runs EXPLAIN ANALYZE instead of EXPLAIN",
            ),
        },
    ),
    responses={
        200: inline_serializer(
            name="DBExplainResponse",
            fields={
                "query_plan": serializers.CharField(),
                "analyzed": serializers.BooleanField(),
            },
        ),
        400: inline_serializer(
            name="DBExplainError",
            fields={"error": serializers.CharField()},
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([UserRateThrottle])
def db_explain_view(request):
    """
    POST /api/admin/db/explain/

    Returns the query execution plan for a given SQL SELECT statement.
    Secured to admin (staff) users only and rate-limited to 10/min
    (configurable via ENDPOINT_RATE_LIMIT_DB_EXPLAIN) to prevent abuse
    of expensive EXPLAIN ANALYZE queries.
    """
    # Dedicated throttle scope check (issue #1291) — also enforce the
    # db_explain limit even when USER rate is higher.  We manually
    # delegate to DBExplainThrottle so function-views respect the
    # separate bucket.
    from soroscan.throttles import DBExplainThrottle

    throttle = DBExplainThrottle()
    if not throttle.allow_request(request, db_explain_view):  # type: ignore[arg-type]
        return Response(
            {"detail": f"Request was throttled. Expected available in {throttle.wait():.0f} seconds."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    if not request.user or not request.user.is_staff:
        return Response(
            {"error": "Admin access required."},
            status=status.HTTP_403_FORBIDDEN,
        )

    sql = (request.data.get("query") or "").strip()
    if not sql:
        return Response(
            {"error": "A SQL query is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not _ALLOWED_STATEMENTS.match(sql):
        return Response(
            {"error": "Only SELECT, WITH, and EXPLAIN statements are allowed."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Reject multi-statement payloads such as "SELECT 1; DROP TABLE foo"
    # Trailing semicolon is allowed, but any additional non-whitespace
    # statement after the first semicolon is denied.
    stripped = sql.strip()
    # Strip one trailing semicolon for the check, then look for any remaining semicolon
    without_trailing = stripped.rstrip(";").strip()
    if ";" in without_trailing:
        return Response(
            {"error": "Multiple statements not allowed; provide a single SELECT/WITH/EXPLAIN."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    # Also handle the case where the user supplied "SELECT 1; DROP"
    # without_trailing already catches interior ;, but if they did "SELECT 1; "
    # the rstrip approach would hide it — so also check count vs allowed trailing
    if stripped.count(";") > 1 or (stripped.endswith(";") and ";" in stripped[:-1]):
        return Response(
            {"error": "Multiple statements not allowed; provide a single SELECT/WITH/EXPLAIN."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    analyze = bool(request.data.get("analyze", False))
    prefix = "EXPLAIN ANALYZE" if analyze else "EXPLAIN"
    logger.info(
        "db_explain requested by %s analyze=%s query=%.120s",
        getattr(request.user, "username", str(getattr(request.user, "id", "unknown"))),
        analyze,
        sql,
    )

    try:
        from django.db import connection

        with connection.cursor() as cursor:
            try:
                cursor.execute(f"{prefix} {sql}")
            except Exception:
                if analyze:
                    # SQLite doesn't support EXPLAIN ANALYZE; fall back to EXPLAIN
                    cursor.execute(f"EXPLAIN {sql}")
                else:
                    raise
            plan = "\n".join(
                " ".join(str(cell) for cell in row) for row in cursor.fetchall()
            )
    except Exception as exc:
        return Response(
            {"error": f"Failed to execute EXPLAIN: {exc}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response({"query_plan": plan, "analyzed": analyze})


# ---------------------------------------------------------------------------
# Issue #488: Cache stats endpoint
# ---------------------------------------------------------------------------

@extend_schema(
    responses=inline_serializer(
        name="CacheStatsResponse",
        fields={
            "backend": serializers.CharField(),
            "default_ttl": serializers.IntegerField(),
            "status": serializers.CharField(),
        },
    ),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@throttle_classes([UserRateThrottle])
def cache_stats_view(request):
    """
    GET /api/cache/stats/

    Returns cache hit/miss statistics and current cache backend info.
    """
    from django.core.cache import cache as django_cache

    backend_info = str(type(django_cache._cache).__name__)

    return Response({
        "backend": backend_info,
        "default_ttl": getattr(settings, "QUERY_CACHE_TTL_SECONDS", 60),
        "status": "ok",
    })


# ---------------------------------------------------------------------------
# Contract health endpoint (Issue: indexing failure alerting)
# ---------------------------------------------------------------------------

@extend_schema(
    parameters=[
        OpenApiParameter(
            name="contract_id",
            location=OpenApiParameter.PATH,
            description="Stellar contract address (C…, 56 chars)",
            required=True,
            type=str,
        )
    ],
    responses=inline_serializer(
        name="ContractHealthResponse",
        fields={
            "contract_id": serializers.CharField(),
            "status": serializers.ChoiceField(choices=["healthy", "degraded", "failed"]),
            "last_event_time": serializers.DateTimeField(allow_null=True),
            "minutes_since_last_event": serializers.IntegerField(),
            "abi_decode_errors_1h": serializers.IntegerField(),
            "consecutive_failures": serializers.IntegerField(),
            "error_message": serializers.CharField(allow_blank=True),
            "checked_at": serializers.DateTimeField(allow_null=True),
        },
    ),
    description=(
        "Return the current indexing health of a contract. "
        "Status is **healthy** (events flowing normally), **degraded** (no events for "
        ">30 min or ABI decode spike), or **failed** (no events for >2 hours). "
        "Updated every 5 minutes by the ``check_contract_health`` Celery task."
    ),
)
@api_view(["GET"])
@permission_classes([AllowAny])
def contract_health_view(request, contract_id: str):
    """GET /api/ingest/contracts/{contract_id}/health/"""
    contract = get_cached_contract(contract_id)
    if not contract:
        return Response(
            {"detail": f"Contract '{contract_id}' not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        health = ContractHealthCheck.objects.get(contract=contract)
    except ContractHealthCheck.DoesNotExist:
        # No health record yet — infer from last_event_at on the contract itself
        last_event_time = contract.last_event_at
        if last_event_time:
            minutes_since = int(
                (timezone.now() - last_event_time).total_seconds() / 60
            )
        else:
            minutes_since = None

        return Response(
            {
                "contract_id": contract_id,
                "status": "healthy",
                "last_event_time": last_event_time,
                "minutes_since_last_event": minutes_since,
                "abi_decode_errors_1h": 0,
                "consecutive_failures": 0,
                "error_message": "",
                "checked_at": None,
            }
        )

    return Response(
        {
            "contract_id": contract_id,
            "status": health.status,
            "last_event_time": health.last_event_time,
            "minutes_since_last_event": health.minutes_since_last_event,
            "abi_decode_errors_1h": health.abi_decode_errors_1h,
            "consecutive_failures": health.consecutive_failures,
            "error_message": health.error_message,
            "checked_at": health.checked_at,
        }
    )


@extend_schema(
    responses=inline_serializer(
        name="AllContractHealthResponse",
        fields={
            "total": serializers.IntegerField(),
            "healthy": serializers.IntegerField(),
            "degraded": serializers.IntegerField(),
            "failed": serializers.IntegerField(),
            "contracts": serializers.JSONField(),
        },
    ),
    description="Return health status for all active contracts. Staff only.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def all_contracts_health_view(request):
    """GET /api/analytics/contracts/health/ — overview for admin dashboard."""
    if not request.user.is_staff:
        return Response(
            {"detail": "Staff access required."},
            status=status.HTTP_403_FORBIDDEN,
        )

    health_qs = (
        ContractHealthCheck.objects.select_related("contract")
        .order_by("status", "-checked_at")
    )

    contracts_data = [
        {
            "contract_id": h.contract.contract_id,
            "name": h.contract.name,
            "network": h.contract.network,
            "status": h.status,
            "last_event_time": h.last_event_time.isoformat() if h.last_event_time else None,
            "minutes_since_last_event": h.minutes_since_last_event,
            "abi_decode_errors_1h": h.abi_decode_errors_1h,
            "consecutive_failures": h.consecutive_failures,
            "error_message": h.error_message,
            "checked_at": h.checked_at.isoformat() if h.checked_at else None,
        }
        for h in health_qs
    ]

    counts: dict = {"healthy": 0, "degraded": 0, "failed": 0}
    for c in contracts_data:
        counts[c["status"]] = counts.get(c["status"], 0) + 1

    return Response(
        {
            "total": len(contracts_data),
            "healthy": counts["healthy"],
            "degraded": counts["degraded"],
            "failed": counts["failed"],
            "contracts": contracts_data,
        }
    )


# ---------------------------------------------------------------------------
# Analytics endpoint — event volume, trends, anomalies, export
# ---------------------------------------------------------------------------

# Maximum range allowed for analytics queries (1 year)
_ANALYTICS_MAX_RANGE_DAYS = 365

# Map of API granularity → (truncation unit, roll-up key function)
_GRANULARITY_TRUNC: dict[str, str] = {
    "hourly": "hour",
    "daily": "day",
    "weekly": "week",
    "monthly": "month",
}

_RANGE_ALIASES: dict[str, int] = {
    "1d": 1,
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "1y": 365,
}


def _parse_range(raw: str | None) -> int:
    """Return number of days for a range string like '30d' or plain int string."""
    if not raw:
        return 30
    if raw in _RANGE_ALIASES:
        return _RANGE_ALIASES[raw]
    try:
        days = int(raw.rstrip("d"))
        return min(max(days, 1), _ANALYTICS_MAX_RANGE_DAYS)
    except (ValueError, AttributeError):
        return 30


class AnalyticsViewSet(viewsets.ViewSet):
    """
    ViewSet for pre-computed event analytics.

    GET /api/ingest/analytics/                     — platform-wide summary widget data
    GET /api/ingest/analytics/event_volume/        — time-series event counts
    GET /api/ingest/analytics/top_contracts/       — most active contracts
    GET /api/ingest/analytics/event_type_breakdown/ — event type distribution
    GET /api/ingest/analytics/anomalies/           — buckets flagged as anomalies
    GET /api/ingest/analytics/export/              — CSV / JSON export

    All read-only, authentication required.
    """

    permission_classes = [IsAuthenticated]

    # ── Platform summary (dashboard widgets) ─────────────────────────────────

    @extend_schema(
        responses=inline_serializer(
            name="AnalyticsSummary",
            fields={
                "total_events": serializers.IntegerField(),
                "active_contracts": serializers.IntegerField(),
                "events_last_24h": serializers.IntegerField(),
                "events_last_7d": serializers.IntegerField(),
                "unique_event_types": serializers.IntegerField(),
                "anomalies_last_7d": serializers.IntegerField(),
                "top_event_type": serializers.CharField(allow_null=True),
            },
        )
    )
    def list(self, request):
        """
        GET /api/ingest/analytics/
        Platform-wide summary numbers for dashboard stat widgets.
        Cached for QUERY_CACHE_TTL_SECONDS.
        """
        from .models import EventAggregation  # noqa: PLC0415

        cache_key = stable_cache_key("analytics_summary", {"user_id": request.user.pk})

        def _build():
            now = timezone.now()
            cutoff_24h = now - timedelta(hours=24)
            cutoff_7d = now - timedelta(days=7)

            base_qs = EventAggregation.objects.filter(event_type="")

            totals = base_qs.aggregate(
                total=Sum("event_count"),
                last_24h=Sum("event_count", filter=Q(timestamp__gte=cutoff_24h)),
                last_7d=Sum("event_count", filter=Q(timestamp__gte=cutoff_7d)),
                anomalies_7d=Count("id", filter=Q(is_anomaly=True, timestamp__gte=cutoff_7d)),
            )

            active_contracts = TrackedContract.objects.filter(is_active=True).count()
            unique_types = (
                EventAggregation.objects.exclude(event_type="")
                .values("event_type")
                .distinct()
                .count()
            )
            top_row = (
                EventAggregation.objects.exclude(event_type="")
                .filter(timestamp__gte=cutoff_7d)
                .values("event_type")
                .annotate(total=Sum("event_count"))
                .order_by("-total")
                .first()
            )

            return {
                "total_events": totals["total"] or 0,
                "active_contracts": active_contracts,
                "events_last_24h": totals["last_24h"] or 0,
                "events_last_7d": totals["last_7d"] or 0,
                "unique_event_types": unique_types,
                "anomalies_last_7d": totals["anomalies_7d"] or 0,
                "top_event_type": top_row["event_type"] if top_row else None,
            }

        return Response(get_or_set_json(cache_key, query_cache_ttl(), _build))

    # ── Time-series: event volume ─────────────────────────────────────────────

    @extend_schema(
        parameters=[
            OpenApiParameter("granularity", str, description="hourly|daily|weekly|monthly", default="daily"),
            OpenApiParameter("range", str, description="Range alias (7d, 30d, 90d, 1y) or Nd", default="30d"),
            OpenApiParameter("contract_id", str, description="Filter to a single contract", required=False),
            OpenApiParameter("event_type", str, description="Filter to a single event type", required=False),
        ],
        responses=inline_serializer(
            name="EventVolumeResponse",
            fields={
                "metric": serializers.CharField(),
                "granularity": serializers.CharField(),
                "range_days": serializers.IntegerField(),
                "data": serializers.ListField(child=serializers.JSONField()),
            },
        ),
    )
    @action(detail=False, methods=["get"], url_path="event_volume")
    def event_volume(self, request):
        """
        GET /api/ingest/analytics/event_volume/

        Returns time-series event count data.
        Queries pre-computed EventAggregation rows; rolls up to requested granularity.
        """
        from .models import EventAggregation  # noqa: PLC0415
        from django.db.models.functions import TruncHour, TruncDay, TruncWeek, TruncMonth  # noqa: PLC0415

        granularity = request.query_params.get("granularity", "daily")
        if granularity not in _GRANULARITY_TRUNC:
            return Response(
                {"detail": f"granularity must be one of: {', '.join(_GRANULARITY_TRUNC)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        range_days = _parse_range(request.query_params.get("range", "30d"))
        since = timezone.now() - timedelta(days=range_days)

        qs = EventAggregation.objects.filter(timestamp__gte=since)

        contract_id = request.query_params.get("contract_id")
        if contract_id:
            contract = get_cached_contract(contract_id)
            if not contract:
                return Response(
                    {"detail": f"Contract '{contract_id}' not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            qs = qs.filter(contract=contract)

        event_type = request.query_params.get("event_type")
        if event_type is not None:
            qs = qs.filter(event_type=event_type)
        else:
            # Default: return totals (event_type='')
            qs = qs.filter(event_type="")

        trunc_fn_map = {
            "hourly": TruncHour,
            "daily": TruncDay,
            "weekly": TruncWeek,
            "monthly": TruncMonth,
        }
        TruncFn = trunc_fn_map[granularity]

        rows = (
            qs.annotate(bucket=TruncFn("timestamp"))
            .values("bucket", "contract_id")
            .annotate(
                count=Sum("event_count"),
                has_anomaly=Count("id", filter=Q(is_anomaly=True)),
            )
            .order_by("bucket")
        )

        # Enrich with contract_id strings (avoid N+1 by pre-fetching id→contract_id map)
        contract_pks = {r["contract_id"] for r in rows}
        pk_to_cid = dict(
            TrackedContract.objects.filter(pk__in=contract_pks).values_list("id", "contract_id")
        )

        data = [
            {
                "timestamp": r["bucket"].isoformat(),
                "contract_id": pk_to_cid.get(r["contract_id"], ""),
                "count": r["count"] or 0,
                "has_anomaly": r["has_anomaly"] > 0,
            }
            for r in rows
        ]

        return Response(
            {
                "metric": "event_volume",
                "granularity": granularity,
                "range_days": range_days,
                "data": data,
            }
        )

    # ── Top contracts ─────────────────────────────────────────────────────────

    @extend_schema(
        parameters=[
            OpenApiParameter("range", str, default="7d"),
            OpenApiParameter("limit", int, default=10),
        ],
        responses=inline_serializer(
            name="TopContractsResponse",
            fields={
                "range_days": serializers.IntegerField(),
                "contracts": serializers.ListField(child=serializers.JSONField()),
            },
        ),
    )
    @action(detail=False, methods=["get"], url_path="top_contracts")
    def top_contracts(self, request):
        """Most active contracts by total event count over the requested range."""
        from .models import EventAggregation  # noqa: PLC0415

        range_days = _parse_range(request.query_params.get("range", "7d"))
        limit = min(int(request.query_params.get("limit", 10)), 100)
        since = timezone.now() - timedelta(days=range_days)

        rows = (
            EventAggregation.objects.filter(timestamp__gte=since, event_type="")
            .values("contract_id")
            .annotate(total=Sum("event_count"))
            .order_by("-total")[:limit]
        )

        contract_pks = [r["contract_id"] for r in rows]
        pk_to_info = {
            c.pk: {"contract_id": c.contract_id, "name": c.name, "network": c.network}
            for c in TrackedContract.objects.filter(pk__in=contract_pks)
        }

        contracts = [
            {
                **pk_to_info.get(r["contract_id"], {"contract_id": "", "name": "", "network": ""}),
                "event_count": r["total"] or 0,
            }
            for r in rows
        ]

        return Response({"range_days": range_days, "contracts": contracts})

    # ── Event type breakdown ──────────────────────────────────────────────────

    @extend_schema(
        parameters=[
            OpenApiParameter("range", str, default="7d"),
            OpenApiParameter("contract_id", str, required=False),
        ],
        responses=inline_serializer(
            name="EventTypeBreakdownResponse",
            fields={
                "range_days": serializers.IntegerField(),
                "breakdown": serializers.ListField(child=serializers.JSONField()),
            },
        ),
    )
    @action(detail=False, methods=["get"], url_path="event_type_breakdown")
    def event_type_breakdown(self, request):
        """Distribution of event types by count over the requested range."""
        from .models import EventAggregation  # noqa: PLC0415

        range_days = _parse_range(request.query_params.get("range", "7d"))
        since = timezone.now() - timedelta(days=range_days)

        qs = EventAggregation.objects.filter(
            timestamp__gte=since,
        ).exclude(event_type="")

        contract_id = request.query_params.get("contract_id")
        if contract_id:
            contract = get_cached_contract(contract_id)
            if not contract:
                return Response(
                    {"detail": f"Contract '{contract_id}' not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            qs = qs.filter(contract=contract)

        rows = (
            qs.values("event_type")
            .annotate(total=Sum("event_count"))
            .order_by("-total")
        )

        grand_total = sum(r["total"] or 0 for r in rows)

        breakdown = [
            {
                "event_type": r["event_type"],
                "count": r["total"] or 0,
                "pct": round((r["total"] or 0) / grand_total * 100, 2) if grand_total else 0.0,
            }
            for r in rows
        ]

        return Response({"range_days": range_days, "breakdown": breakdown})

    # ── Anomalies ─────────────────────────────────────────────────────────────

    @extend_schema(
        parameters=[OpenApiParameter("range", str, default="7d")],
        responses=inline_serializer(
            name="AnomalyListResponse",
            fields={
                "range_days": serializers.IntegerField(),
                "anomalies": serializers.ListField(child=serializers.JSONField()),
            },
        ),
    )
    @action(detail=False, methods=["get"], url_path="anomalies")
    def anomalies(self, request):
        """Return aggregation buckets flagged as anomalies within the range."""
        from .models import EventAggregation  # noqa: PLC0415

        range_days = _parse_range(request.query_params.get("range", "7d"))
        since = timezone.now() - timedelta(days=range_days)

        rows = (
            EventAggregation.objects.filter(
                is_anomaly=True,
                event_type="",
                timestamp__gte=since,
            )
            .select_related("contract")
            .order_by("-timestamp")
        )

        anomaly_data = [
            {
                "timestamp": r.timestamp.isoformat(),
                "contract_id": r.contract.contract_id,
                "contract_name": r.contract.name,
                "event_count": r.event_count,
            }
            for r in rows
        ]

        return Response({"range_days": range_days, "anomalies": anomaly_data})

    # ── CSV / JSON export ─────────────────────────────────────────────────────

    @extend_schema(
        parameters=[
            OpenApiParameter("range", str, default="30d"),
            OpenApiParameter("contract_id", str, required=False),
            OpenApiParameter("export_format", str, description="csv or json", default="json"),
        ],
        responses={200: serializers.CharField()},
    )
    @action(detail=False, methods=["get"], url_path="export",
            renderer_classes=[renderers.JSONRenderer, renderers.BrowsableAPIRenderer])
    def export(self, request):
        """
        GET /api/ingest/analytics/export/

        Download analytics data as CSV or JSON.
        Range capped at 1 year.  CSV streams efficiently for large result sets.
        """
        from .models import EventAggregation  # noqa: PLC0415
        import csv as csv_module  # noqa: PLC0415
        from django.http import StreamingHttpResponse  # noqa: PLC0415

        range_days = _parse_range(request.query_params.get("range", "30d"))
        since = timezone.now() - timedelta(days=range_days)
        fmt = request.query_params.get("export_format", request.query_params.get("format", "json")).lower()

        qs = (
            EventAggregation.objects.filter(timestamp__gte=since)
            .select_related("contract")
            .order_by("contract_id", "event_type", "timestamp")
        )

        contract_id = request.query_params.get("contract_id")
        if contract_id:
            contract = get_cached_contract(contract_id)
            if not contract:
                return Response(
                    {"detail": f"Contract '{contract_id}' not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            qs = qs.filter(contract=contract)

        if fmt == "csv":
            columns = ["timestamp", "contract_id", "contract_name", "event_type", "event_count", "is_anomaly"]

            class _Echo:
                def write(self, v):
                    return v

            def _stream():
                buf = _Echo()
                writer = csv_module.writer(buf)
                yield writer.writerow(columns)
                for row in qs.iterator(chunk_size=2000):
                    yield writer.writerow([
                        row.timestamp.isoformat(),
                        row.contract.contract_id,
                        row.contract.name,
                        row.event_type,
                        row.event_count,
                        row.is_anomaly,
                    ])

            filename = f"soroscan_analytics_{range_days}d.csv"
            resp = StreamingHttpResponse(_stream(), content_type="text/csv")
            resp["Content-Disposition"] = f'attachment; filename="{filename}"'
            return resp

        # JSON
        data = [
            {
                "timestamp": row.timestamp.isoformat(),
                "contract_id": row.contract.contract_id,
                "contract_name": row.contract.name,
                "event_type": row.event_type,
                "event_count": row.event_count,
                "is_anomaly": row.is_anomaly,
            }
            for row in qs.iterator(chunk_size=2000)
        ]
        return Response({"range_days": range_days, "data": data})


# ---------------------------------------------------------------------------
# Celery task queue status endpoint (issue #1292)
# ---------------------------------------------------------------------------

@extend_schema(
    responses=inline_serializer(
        name="CeleryStatusResponse",
        fields={
            "queues": serializers.DictField(
                child=serializers.IntegerField(),
                help_text="Pending message count per queue name.",
            ),
            "workers": serializers.DictField(
                child=serializers.CharField(),
                help_text="Per-worker status ('online' or 'offline').",
            ),
            "workers_online": serializers.IntegerField(
                help_text="Total number of workers responding to health probes.",
            ),
            "active_tasks": serializers.DictField(
                child=serializers.IntegerField(),
                help_text="Number of currently executing tasks per task name.",
            ),
            "metrics": serializers.DictField(
                help_text=(
                    "Latest Prometheus counter/gauge snapshot. "
                    "task_failure_rate is the fraction of failures over all terminal outcomes."
                ),
            ),
        },
    ),
    description=(
        "Return a snapshot of Celery queue depths, worker status, and task "
        "execution metrics.  Intended for internal dashboards and health checks.\n\n"
        "Queue depth data comes from Redis (same broker used by Celery). "
        "Worker list is retrieved via Celery inspect ping (timeout 0.5 s). "
        "Active task counts and metric snapshots come from the Prometheus "
        "``soroscan_celery_*`` metrics already exported via ``/metrics``."
    ),
)
# Dead Letter Queue — query + replay (issue #1311)
# ---------------------------------------------------------------------------


@extend_schema(
    responses=inline_serializer(
        name="DLQEntrySerializer",
        fields={
            "id": serializers.IntegerField(),
            "subscription_id": serializers.IntegerField(),
            "event_id": serializers.IntegerField(allow_null=True),
            "status_code": serializers.IntegerField(allow_null=True),
            "error": serializers.CharField(),
            "retries_exhausted": serializers.IntegerField(),
            "resolved": serializers.BooleanField(),
            "created_at": serializers.DateTimeField(),
        },
        many=True,
    ),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@throttle_classes([UserRateThrottle])
def celery_status_view(request):
    """
    GET /api/celery/status/

    Returns a snapshot of Celery queue depths, worker health, and
    task metrics.  Requires authentication.

    Response schema
    ---------------
    ``queues``        — dict of queue_name → pending message count
    ``workers``       — dict of worker_name → "online" | "offline"
    ``workers_online`` — count of online workers
    ``active_tasks``  — dict of task_name → currently executing count
    ``metrics``       — task outcome counters and failure rate
    """
    from urllib.parse import urlparse

    import logging as _logging

    _log = _logging.getLogger("soroscan.celery_status")

    # ------------------------------------------------------------------
    # 1. Queue depths via Redis
    # ------------------------------------------------------------------
    queues: dict[str, int] = {}
    monitored_queues = ("high_priority", "default", "low_priority", "backfill")
    try:
        from redis import Redis as _Redis

        parsed = urlparse(settings.CELERY_BROKER_URL)
        redis = _Redis.from_url(parsed.geturl(), socket_timeout=2)
        for q in monitored_queues:
            queues[q] = int(redis.llen(q))
    except Exception:
        _log.exception("celery_status_view: could not read queue depths")
        for q in monitored_queues:
            queues.setdefault(q, -1)

    # ------------------------------------------------------------------
    # 2. Worker status via Celery inspect
    # ------------------------------------------------------------------
    workers: dict[str, str] = {}
    workers_online = 0
    try:
        from soroscan.celery import app as _celery_app

        responses = _celery_app.control.inspect(timeout=0.5).ping() or {}
        for worker_name in responses:
            workers[worker_name] = "online"
            workers_online += 1
    except Exception:
        _log.exception("celery_status_view: could not ping workers")

    if not workers:
        workers["none"] = "offline"

    # ------------------------------------------------------------------
    # 3. Active task counts from Prometheus Gauge
    # ------------------------------------------------------------------
    active_tasks: dict[str, int] = {}
    try:
        from prometheus_client import REGISTRY as _REGISTRY

        for metric in _REGISTRY.collect():
            if metric.name == "soroscan_celery_tasks_active":
                for sample in metric.samples:
                    task_name = sample.labels.get("task_name", "unknown")
                    active_tasks[task_name] = int(sample.value)
    except Exception:
        _log.exception("celery_status_view: could not read active task metrics")

    # ------------------------------------------------------------------
    # 4. Outcome counters and failure rate
    # ------------------------------------------------------------------
    metrics: dict[str, object] = {
        "tasks_total": {},
        "task_failure_rate": None,
    }
    try:
        from prometheus_client import REGISTRY as _REGISTRY

        total_all = 0.0
        total_failure = 0.0
        tasks_total: dict[str, int] = {}

        for metric in _REGISTRY.collect():
            if metric.name == "soroscan_celery_tasks_total":
                for sample in metric.samples:
                    if sample.name.endswith("_total"):
                        task_name = sample.labels.get("task_name", "unknown")
                        s = sample.labels.get("status", "")
                        key = f"{task_name}.{s}" if s else task_name
                        tasks_total[key] = int(sample.value)
                        total_all += sample.value
                        if s == "failure":
                            total_failure += sample.value

        metrics["tasks_total"] = tasks_total
        if total_all > 0:
            metrics["task_failure_rate"] = round(total_failure / total_all, 4)
        else:
            metrics["task_failure_rate"] = 0.0
    except Exception:
        _log.exception("celery_status_view: could not collect task metrics")

    return Response(
        {
            "queues": queues,
            "workers": workers,
            "workers_online": workers_online,
            "active_tasks": active_tasks,
            "metrics": metrics,
        },
        status=status.HTTP_200_OK,
    )
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dlq_list_view(request):
    """List dead-letter queue entries (admin only)."""
    if not request.user.is_staff:
        return Response({"error": "Admin access required"}, status=status.HTTP_403_FORBIDDEN)

    from soroscan.ingest.models import WebhookDeadLetter

    qs = WebhookDeadLetter.objects.select_related("subscription", "event").all()

    resolved = request.query_params.get("resolved")
    if resolved is not None:
        qs = qs.filter(resolved=resolved.lower() in ("true", "1"))

    subscription_id = request.query_params.get("subscription_id")
    if subscription_id:
        qs = qs.filter(subscription_id=subscription_id)

    try:
        limit = max(1, min(int(request.query_params.get("limit", 50)), 500))
    except (TypeError, ValueError):
        limit = 50

    data = [
        {
            "id": entry.id,
            "subscription_id": entry.subscription_id,
            "event_id": entry.event_id,
            "status_code": entry.status_code,
            "error": entry.error,
            "retries_exhausted": entry.retries_exhausted,
            "resolved": entry.resolved,
            "created_at": entry.created_at.isoformat(),
        }
        for entry in qs[:limit]
    ]
    return Response(data)


@extend_schema(
    request=inline_serializer(
        name="DLQReplayRequest",
        fields={"entry_ids": serializers.ListField(child=serializers.IntegerField())},
    ),
    responses=inline_serializer(
        name="DLQReplayResponse",
        fields={
            "queued": serializers.IntegerField(),
            "skipped": serializers.IntegerField(),
        },
    ),
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def dlq_replay_view(request):
    """Replay selected dead-letter entries (admin only)."""
    if not request.user.is_staff:
        return Response({"error": "Admin access required"}, status=status.HTTP_403_FORBIDDEN)

    from soroscan.ingest.models import WebhookDeadLetter
    from soroscan.ingest.tasks import replay_dead_letter

    entry_ids = request.data.get("entry_ids", [])
    if not entry_ids:
        return Response({"error": "entry_ids required"}, status=status.HTTP_400_BAD_REQUEST)

    entries = WebhookDeadLetter.objects.filter(
        id__in=entry_ids, resolved=False
    ).select_related("event")

    queued = 0
    skipped = 0
    for entry in entries:
        if entry.event is None:
            skipped += 1
            continue
        replay_dead_letter.delay(entry.id)
        queued += 1

    return Response({"queued": queued, "skipped": skipped})
