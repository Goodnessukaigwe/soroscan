"""
Test URL configuration for SoroScan project (without GraphQL).

Excludes strawberry/GraphQL imports that crash on Linux due to a GDAL
library incompatibility in the Anaconda runtime. All non-GraphQL routes
are registered here so that tests can use reverse() normally.
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from soroscan.health import health_view, readiness_view, worker_health_view
from soroscan.meta_views import db_pool_stats_view
from soroscan.pact_provider import provider_states
from soroscan.ingest.views import (
    all_contracts_health_view,
    audit_trail_view,
    cache_stats_view,
    celery_status_view,
    contract_status,
    db_explain_view,
    rate_limit_analytics_view,
    schema_versions_view,
    webhook_batch_delivery_status_view,
    webhook_delivery_metrics_view,
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
    path("api/audit-trail/", audit_trail_view, name="audit-trail"),
    path("api/contracts/status/", contract_status, name="contract-status"),
    path("api/analytics/rate-limits/", rate_limit_analytics_view, name="rate-limit-analytics"),
    path("api/analytics/contracts/health/", all_contracts_health_view, name="all-contracts-health"),
    path("api/meta/db-pool/", db_pool_stats_view, name="db-pool-stats"),
    path("api/schema/versions/", schema_versions_view, name="schema-versions"),
    path("api/health/workers/", worker_health_view, name="worker-health"),
    path("api/dev/summary/", dev_summary_view, name="dev-summary"),
    path("api/admin/db/explain/", db_explain_view, name="admin-db-explain"),
    path("api/cache/stats/", cache_stats_view, name="cache-stats"),
    path("api/celery/status/", celery_status_view, name="celery-status"),
    path(
        "api/webhooks/deliveries/batch-status/",
        webhook_batch_delivery_status_view,
        name="webhook-batch-delivery-status",
    ),
    path(
        "api/webhooks/deliveries/metrics/",
        webhook_delivery_metrics_view,
        name="webhook-delivery-metrics",
    ),
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/ingest/", include("soroscan.ingest.urls")),
    path("v1/", include("soroscan.v1.urls")),
    path("_pact/provider-states", provider_states, name="pact-provider-states"),
]

handler404 = 'soroscan.error_handlers.custom_404'
handler500 = 'soroscan.error_handlers.custom_500'
