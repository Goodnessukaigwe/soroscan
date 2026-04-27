"""
Administrative meta endpoints for SoroScan.

Exposes internal operational statistics — database connection pool metrics —
behind admin-level authentication so operators can monitor DB health and
detect connection leaks without exposing sensitive credentials.
"""
import logging

from django.db import connections
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def _collect_postgres_pool_stats(conn_wrapper):
    """Collect live connection metrics from PostgreSQL system views."""
    with conn_wrapper.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE datname = current_database()) AS total,
                COUNT(*) FILTER (
                    WHERE datname = current_database() AND state = 'active'
                ) AS active,
                COUNT(*) FILTER (
                    WHERE datname = current_database() AND state = 'idle'
                ) AS idle,
                COUNT(*) FILTER (
                    WHERE datname = current_database()
                    AND wait_event_type IS NOT NULL
                ) AS wait_queue
            FROM pg_stat_activity
            """
        )
        total, active, idle, wait_queue = cursor.fetchone()

    return {
        "total": int(total or 0),
        "active": int(active or 0),
        "idle": int(idle or 0),
        "wait_queue": int(wait_queue or 0),
    }


def _collect_fallback_pool_stats(conn_wrapper):
    """Fallback for non-PostgreSQL test/dev databases without pool metadata."""
    conn_wrapper.ensure_connection()
    is_usable = conn_wrapper.is_usable()
    return {
        "total": 1,
        "active": 0 if is_usable else 1,
        "idle": 1 if is_usable else 0,
        "wait_queue": 0,
    }


@extend_schema(
    responses=inline_serializer(
        name="DbPoolStatsResponse",
        fields={
            "total": serializers.IntegerField(
                help_text="Total live connections for the current database."
            ),
            "active": serializers.IntegerField(
                help_text="Live connections currently executing queries."
            ),
            "idle": serializers.IntegerField(
                help_text="Live connections currently idle."
            ),
            "wait_queue": serializers.IntegerField(
                help_text="Live connections waiting on a database wait event."
            ),
        },
    ),
    description=(
        "Return real-time database connection pool statistics for the default "
        "database alias.  Useful for detecting connection leaks or pool "
        "exhaustion.  **Admin access required.**"
    ),
    tags=["meta"],
    auth=["jwtAuth"],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def db_pool_stats_view(request):
    """
    Return real-time DB connection-pool stats for the ``default`` alias.

    The caller must be an active staff/superuser (Django ``is_staff=True``).
    Regular authenticated users receive a 403 Forbidden.

    Response keys
    -------------
    total      – total live DB connections for the current database
    active     – live connections currently executing queries
    idle       – live connections currently idle
    wait_queue – live connections waiting on a DB wait event
    """
    if not request.user.is_staff:
        return Response(
            {"detail": "Admin access required."},
            status=status.HTTP_403_FORBIDDEN,
        )

    alias = "default"
    conn_wrapper = connections[alias]

    try:
        if conn_wrapper.vendor == "postgresql":
            stats = _collect_postgres_pool_stats(conn_wrapper)
        else:
            stats = _collect_fallback_pool_stats(conn_wrapper)

    except Exception:  # pragma: no cover — only fires on genuine DB outage
        logger.exception("Failed to retrieve DB pool stats for alias '%s'", alias)
        return Response(
            {"detail": "Could not retrieve database connection pool statistics."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(
        stats
    )
