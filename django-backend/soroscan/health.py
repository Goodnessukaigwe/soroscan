"""
Health check endpoints for Kubernetes liveness/readiness probes.
"""
import time
import requests
import redis as redis_lib

from django.db import connection
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.conf import settings

from celery.exceptions import TimeoutError
from soroscan.celery import app

WORKER_HEALTH_TIMEOUT_SECONDS = 2
PROCESS_START_TIME = time.monotonic()


def format_uptime(seconds: int) -> str:
    """Format uptime seconds as DH:M:S."""
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    return f"{days}D:{hours:02d}:{minutes:02d}:{seconds:02d}"


def get_uptime_payload() -> dict:
    """Return machine-readable and human-readable uptime values."""
    uptime_seconds = max(0, int(time.monotonic() - PROCESS_START_TIME))

    return {
        "uptime_seconds": uptime_seconds,
        "uptime": format_uptime(uptime_seconds),
    }


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([])
def health_view(request):
    """Liveness probe - app is running."""
    return Response(
        {
            "status": "ok",
            **get_uptime_payload(),
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([])
def ping_view(request):
    """Lightweight ping for load balancers / Docker healthchecks (issue #1436).

    Responds instantly without querying PostgreSQL or Redis.
    """
    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([])
def readiness_view(request):
    """Readiness probe - DB, Redis, and Soroban RPC are connected."""
    components = {
        "database": "healthy",
        "redis": "healthy",
        "soroban_rpc": "healthy"
    }
    overall_status = "healthy"
    
    db_pool_active = 0
    db_pool_max = 0
    redis_latency_ms = 0
    celery_workers_online = 0

    # 1. Database Check
    try:
        from soroscan.db_pool import calculate_pool_limits
        _, max_conn = calculate_pool_limits()
        db_pool_max = max(int(max_conn or 0), 1)

        if connection.vendor == "postgresql":
            from soroscan.meta_views import _collect_postgres_pool_stats
            stats = _collect_postgres_pool_stats(connection)
        else:
            from soroscan.meta_views import _collect_fallback_pool_stats
            stats = _collect_fallback_pool_stats(connection)
        
        db_pool_active = int(stats.get("active") or 0)

        if db_pool_active >= db_pool_max:
            components["database"] = "degraded: connection pool exhausted"
            overall_status = "degraded"
        else:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
    except Exception as e:
        components["database"] = f"degraded: {str(e)}"
        overall_status = "degraded"

    # 2. Redis Check — direct PING via redis-py with Latency check
    redis_url = getattr(settings, "REDIS_URL", None)
    if redis_url:
        try:
            start_time = time.perf_counter()
            r = redis_lib.Redis.from_url(redis_url, socket_timeout=2)
            r.ping()
            r.close()
            redis_latency_ms = int((time.perf_counter() - start_time) * 1000)
            
            if redis_latency_ms > 2000:
                components["redis"] = f"degraded: high latency ({redis_latency_ms}ms > 2000ms)"
                overall_status = "degraded"
        except redis_lib.ConnectionError as e:
            components["redis"] = f"degraded: connection refused: {e}"
            overall_status = "degraded"
        except redis_lib.TimeoutError as e:
            components["redis"] = f"degraded: timeout: {e}"
            overall_status = "degraded"
        except Exception as e:
            components["redis"] = f"degraded: {e}"
            overall_status = "degraded"
    else:
        components["redis"] = "degraded: REDIS_URL not configured"
        overall_status = "degraded"

    # 3. Soroban RPC Check
    try:
        rpc_url = getattr(settings, "SOROBAN_RPC_URL", "")
        if rpc_url:
            # Send a lightweight getHealth JSON-RPC ping to Soroban
            res = requests.post(
                rpc_url, 
                json={"jsonrpc": "2.0", "id": 1, "method": "getHealth"}, 
                timeout=3
            )
            res.raise_for_status()
            data = res.json()
            if "error" in data:
                components["soroban_rpc"] = f"degraded: {data['error']}"
                overall_status = "degraded"
        else:
            components["soroban_rpc"] = "degraded: SOROBAN_RPC_URL not configured"
            overall_status = "degraded"
    except Exception as e:
        components["soroban_rpc"] = f"degraded: {str(e)}"
        overall_status = "degraded"

    # 4. Celery Workers Status Check
    try:
        inspector = app.control.inspect(timeout=1.0)
        worker_status = inspector.ping()
        if worker_status:
            celery_workers_online = len(worker_status)
    except Exception:
        celery_workers_online = 0

    status_code = 200 if overall_status == "healthy" else 503

    return Response({
        "status": overall_status,
        "components": components,
        "db_pool_active": db_pool_active,
        "db_pool_max": db_pool_max,
        "redis_latency_ms": redis_latency_ms,
        "celery_workers_online": celery_workers_online,
    }, status=status_code)


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([])
def worker_health_view(request):
    """Worker health probe - checks Celery workers are responding."""
    try:
        inspector = app.control.inspect(timeout=WORKER_HEALTH_TIMEOUT_SECONDS)
        worker_status = inspector.ping()

        if not worker_status:
            raise Exception("no worker responded")

        return Response({"status": "healthy", "workers": worker_status})
    except TimeoutError:
        return Response(
            {"status": "unhealthy", "error": "worker ping timeout"},
            status=503,
        )
    except Exception as exc:
        return Response(
            {"status": "unhealthy", "error": str(exc)},
            status=503,
        )