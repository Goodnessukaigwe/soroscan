"""
Test URL configuration for SoroScan project (without GraphQL).

Excludes strawberry/GraphQL imports that crash on Linux due to a GDAL
library incompatibility in the Anaconda runtime. All non-GraphQL routes
are registered here so that tests can use reverse() normally.
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from soroscan.health import health_view, readiness_view
from soroscan.meta_views import db_pool_stats_view
from soroscan.ingest.views import (
    contract_status,
    rate_limit_analytics_view,
    webhook_batch_delivery_status_view,
)
from soroscan.dev_summary_view import dev_summary_view


def handler404_view(request, exception=None):
    return JsonResponse({"error": "Not found", "status": 404}, status=404)


def handler500_view(request):
    return JsonResponse({"error": "Internal server error", "status": 500}, status=500)


handler404 = handler404_view
handler500 = handler500_view

urlpatterns = [
    path("", include("django_prometheus.urls")),
    path("admin/", admin.site.urls),
    path("health/", health_view, name="health"),
    path("ready/", readiness_view, name="readiness"),
    path("api/contracts/status/", contract_status, name="contract-status"),
    path("api/analytics/rate-limits/", rate_limit_analytics_view, name="rate-limit-analytics"),
    path("api/meta/db-pool/", db_pool_stats_view, name="db-pool-stats"),
    path("api/dev/summary/", dev_summary_view, name="dev-summary"),
    path(
        "api/webhooks/deliveries/batch-status/",
        webhook_batch_delivery_status_view,
        name="webhook-batch-delivery-status",
    ),
    path("api/ingest/", include("soroscan.ingest.urls")),
]

handler404 = 'soroscan.error_handlers.custom_404'
handler500 = 'soroscan.error_handlers.custom_500'
