"""
GraphQL trusted query whitelist utilities.
"""

from __future__ import annotations

import hashlib
import re

WHITESPACE_RE = re.compile(r"\s+")
COMMENT_RE = re.compile(r"#.*")


def normalize_graphql_query(query: str) -> str:
    """Normalize a GraphQL query string for stable hashing."""
    without_comments = COMMENT_RE.sub("", query)
    collapsed = WHITESPACE_RE.sub(" ", without_comments).strip()
    return collapsed


def hash_graphql_query(query: str) -> str:
    """Return SHA-256 hex digest for a normalized GraphQL query."""
    normalized = normalize_graphql_query(query)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
