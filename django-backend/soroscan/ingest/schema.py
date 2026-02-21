"""
GraphQL schema for SoroScan API using Strawberry.
"""
from datetime import datetime
from typing import Optional

import strawberry, strawberry_django
from strawberry import auto
from strawberry.types import Info

from .models import ContractEvent, TrackedContract, EventSchema


@strawberry_django.type(TrackedContract)
class ContractType:
    id: auto
    contract_id: auto
    name: auto
    description: auto
    is_active: auto
    created_at: auto

    @strawberry.field
    def event_count(self) -> int:
        return self.events.count()


@strawberry_django.type(ContractEvent)
class EventType:
    id: auto
    event_type: auto
    payload: strawberry.scalars.JSON
    payload_hash: auto
    ledger: auto
    timestamp: auto
    tx_hash: auto

    @strawberry.field
    def contract_id(self) -> str:
        return self.contract.contract_id

    @strawberry.field
    def contract_name(self) -> str:
        return self.contract.name


@strawberry.type
class ContractStats:
    contract_id: str
    name: str
    total_events: int
    unique_event_types: int
    last_activity: Optional[datetime]


@strawberry.type
class Query:
    @strawberry.field
    def contracts(self, is_active: Optional[bool] = None) -> list[ContractType]:
        """Get all tracked contracts."""
        qs = TrackedContract.objects.all()
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        return qs

    @strawberry.field
    def contract(self, contract_id: str) -> Optional[ContractType]:
        """Get a specific contract by ID."""
        try:
            return TrackedContract.objects.get(contract_id=contract_id)
        except TrackedContract.DoesNotExist:
            return None

    @strawberry.field
    def events(
        self,
        contract_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> list[EventType]:
        """
        Query events with flexible filtering.

        Args:
            contract_id: Filter by contract address
            event_type: Filter by event type
            limit: Maximum results (default 50, max 1000)
            offset: Pagination offset
            since: Filter events after this timestamp
            until: Filter events before this timestamp
        """
        qs = ContractEvent.objects.all()

        if contract_id:
            qs = qs.filter(contract__contract_id=contract_id)
        if event_type:
            qs = qs.filter(event_type=event_type)
        if since:
            qs = qs.filter(timestamp__gte=since)
        if until:
            qs = qs.filter(timestamp__lte=until)

        # Enforce max limit
        limit = min(limit, 1000)

        return qs[offset : offset + limit]

    @strawberry.field
    def event(self, id: int) -> Optional[EventType]:
        """Get a specific event by ID."""
        try:
            return ContractEvent.objects.get(id=id)
        except ContractEvent.DoesNotExist:
            return None

    @strawberry.field
    def contract_stats(self, contract_id: str) -> Optional[ContractStats]:
        """Get aggregate statistics for a contract."""
        try:
            contract = TrackedContract.objects.get(contract_id=contract_id)
        except TrackedContract.DoesNotExist:
            return None

        from django.db.models import Count, Max

        stats = contract.events.aggregate(
            total=Count("id"),
            unique_types=Count("event_type", distinct=True),
            last=Max("timestamp"),
        )

        return ContractStats(
            contract_id=contract.contract_id,
            name=contract.name,
            total_events=stats["total"] or 0,
            unique_event_types=stats["unique_types"] or 0,
            last_activity=stats["last"],
        )

    @strawberry.field
    def event_types(self, contract_id: str) -> list[str]:
        """Get all unique event types for a contract."""
        return list(
            ContractEvent.objects.filter(contract__contract_id=contract_id)
            .values_list("event_type", flat=True)
            .distinct()
        )


@strawberry.type
class Mutation:
    @strawberry.mutation
    def register_contract(
        self,
        info: Info,
        contract_id: str,
        name: str,
        description: str = "",
    ) -> ContractType:
        """Register a new contract for indexing."""
        # TODO: Add proper authentication
        contract = TrackedContract.objects.create(
            contract_id=contract_id,
            name=name,
            description=description,
            owner_id=1,  # Placeholder - should use authenticated user
        )
        return contract

    @strawberry.mutation
    def update_contract(
        self,
        info: Info,
        contract_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[ContractType]:
        """Update a tracked contract."""
        try:
            contract = TrackedContract.objects.get(contract_id=contract_id)
        except TrackedContract.DoesNotExist:
            return None

        if name is not None:
            contract.name = name
        if description is not None:
            contract.description = description
        if is_active is not None:
            contract.is_active = is_active

        contract.save()
        return contract


schema = strawberry.Schema(query=Query, mutation=Mutation)
