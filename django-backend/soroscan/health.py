"""
Health check endpoints for Kubernetes liveness/readiness probes.
"""
from django.core.cache import cache
from django.db import connection
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health_view(request):
    """Liveness probe - app is running."""
    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([AllowAny])
def readiness_view(request):
    """Readiness probe - DB and Redis are connected."""
    errors = []

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception as e:
        errors.append(f"db: {str(e)}")

    try:
        cache.set("health_check", "1", timeout=10)
        if cache.get("health_check") != "1":
            errors.append("redis: failed to read value")
    except Exception as e:
        errors.append(f"redis: {str(e)}")

    if errors:
        return Response({"status": "not_ready", "errors": errors}, status=503)

    return Response({"status": "ready"})