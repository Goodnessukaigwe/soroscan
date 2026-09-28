"""Tests for the GraphQL query depth limit (issue #1408)."""
from __future__ import annotations

import strawberry

from soroscan.graphql_extensions import MaxQueryDepthExtension
from soroscan.ingest.schema import schema as soroscan_schema

resolver_calls = []


@strawberry.type
class Node:
    @strawberry.field
    def child(self) -> Node:
        resolver_calls.append("child")
        return Node()

    @strawberry.field
    def value(self) -> int:
        return 1


@strawberry.type
class Query:
    @strawberry.field
    def root(self) -> Node:
        resolver_calls.append("root")
        return Node()


depth_schema = strawberry.Schema(query=Query, extensions=[MaxQueryDepthExtension()])


def _nested_query(depth: int) -> str:
    """Build a query whose deepest field sits at ``depth`` (root field = 0)."""
    selection = "value"
    for _ in range(depth - 1):
        selection = f"child {{ {selection} }}"
    return f"{{ root {{ {selection} }} }}"


def setup_function():
    resolver_calls.clear()


def test_query_at_max_depth_executes():
    result = depth_schema.execute_sync(_nested_query(7))

    assert result.errors is None
    assert resolver_calls


def test_query_exceeding_max_depth_is_rejected_before_resolvers_run():
    result = depth_schema.execute_sync(_nested_query(8))

    assert result.data is None
    assert len(result.errors) == 1
    assert "exceeds maximum operation depth of 7" in result.errors[0].message
    assert resolver_calls == []


def test_soroscan_schema_uses_depth_limit():
    assert any(
        isinstance(ext, MaxQueryDepthExtension) and ext.max_depth == 7
        for ext in soroscan_schema.extensions
    )
