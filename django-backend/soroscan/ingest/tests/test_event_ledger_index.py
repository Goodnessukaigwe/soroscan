"""Issue #1407 - composite index for ContractEvent ledger-window lookups.

Ledger range queries filtered by ``contract_id`` and ordered by recency
previously fell back to scanning large index ranges, because the existing
``(contract, ledger, event_index)`` unique index cannot serve the trailing
``timestamp`` ordering. These tests pin the new composite index in place and
exercise the query shape it is meant to accelerate.

The suite runs against SQLite (see ``settings_test``), so the PostgreSQL query
plan itself cannot be asserted here; the test instead verifies the index is
declared, migrated, present in the live schema, and that the ledger-window
query it supports returns the correct rows.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.loader import MigrationLoader

from soroscan.ingest.models import ContractEvent

from .factories import ContractEventFactory, TrackedContractFactory

INDEX_NAME = "idx_event_contract_ledger_ts"
INDEX_FIELDS = ["contract", "ledger", "timestamp"]


@pytest.mark.django_db
def test_composite_index_is_declared_on_the_model():
    """`ContractEvent.Meta.indexes` advertises the composite index."""
    declared = {index.name: index for index in ContractEvent._meta.indexes}

    assert INDEX_NAME in declared, (
        f"Expected ContractEvent to declare {INDEX_NAME}; got {sorted(declared)}"
    )
    assert list(declared[INDEX_NAME].fields) == INDEX_FIELDS


@pytest.mark.django_db
def test_composite_index_exists_in_the_live_schema():
    """The index survives migrations and is visible to the database."""
    with connection.cursor() as cursor:
        tables = connection.introspection.table_names(cursor)
        if ContractEvent._meta.db_table not in tables:
            pytest.skip("ContractEvent table not created in this test database")
        constraints = connection.introspection.get_constraints(
            cursor, ContractEvent._meta.db_table
        )

    assert INDEX_NAME in constraints, (
        f"Expected {INDEX_NAME} on {ContractEvent._meta.db_table}; "
        f"got {sorted(constraints)}"
    )
    indexed_columns = [constraints[INDEX_NAME]["columns"]]
    assert any(list(columns) == INDEX_FIELDS for columns in indexed_columns), (
        f"Expected {INDEX_FIELDS} columns, got {indexed_columns}"
    )


def test_index_migration_is_a_single_leaf():
    """The new migration keeps the ingest migration graph single-leafed."""
    loader = MigrationLoader(None, ignore_no_migrations=True)
    leaf_nodes = loader.graph.leaf_nodes(app="ingest")

    assert len(leaf_nodes) == 1, f"Expected one ingest leaf node, got {leaf_nodes}"
    assert leaf_nodes[0][1].startswith("0056_"), (
        f"Expected the 0056_ index migration to be the leaf, got {leaf_nodes[0][1]}"
    )


@pytest.mark.django_db
def test_ledger_window_query_returns_events_in_range():
    """The contract + ledger-range + recency query returns the window only."""
    contract = TrackedContractFactory()
    other_contract = TrackedContractFactory()

    for ledger in range(1_000, 1_010):
        ContractEventFactory(contract=contract, ledger=ledger, event_index=0)
    # Outside the requested window and a different contract, both excluded.
    ContractEventFactory(contract=contract, ledger=1_020, event_index=0)
    ContractEventFactory(contract=other_contract, ledger=1_004, event_index=0)

    window = ContractEvent.objects.filter(
        contract=contract,
        ledger__gte=1_002,
        ledger__lte=1_005,
    ).order_by("-ledger")

    assert list(window.values_list("ledger", flat=True)) == [1_005, 1_004, 1_003, 1_002]
