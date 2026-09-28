"""
URL configuration for SoroScan project.
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from soroscan.graphql_views import ThrottledGraphQLView
from soroscan.health import health_view, ping_view, readiness_view, worker_health_view
from soroscan.meta_views import db_pool_stats_view
from soroscan.pact_provider import provider_states
from soroscan.ingest.views import (
    DLQDeliveryLogViewSet,
    audit_trail_view,
    cache_stats_view,
    celery_status_view,
    contract_status,
    db_explain_view,
    rate_limit_analytics_view,
    all_contracts_health_view,
    webhook_batch_delivery_status_view,
    webhook_delivery_metrics_view,
    schema_versions_view,
)
from soroscan.ingest.schema import schema
from soroscan.dev_summary_view import dev_summary_view


import os

from .error_handlers import custom_404 as handler404_view, custom_500 as handler500_view

handler404 = handler404_view
handler500 = handler500_view

raw_admin_path = os.getenv("ADMIN_URL_PATH", "").strip("/")
admin_url_path = f"{raw_admin_path}/" if raw_admin_path else "admin/"

urlpatterns = [
    # Prometheus metrics — must be unauthenticated; placed before any auth middleware
    # that would intercept requests.  django_prometheus.urls exposes GET /metrics.
    path("", include("django_prometheus.urls")),

    path("health/", health_view, name="health"),
    path("ready/", readiness_view, name="readiness"),
    path("api/health/ping/", ping_view, name="health-ping"),
    path("api/health/workers/", worker_health_view, name="worker-health"),

    path(admin_url_path, admin.site.urls),
    path("api/audit-trail/", audit_trail_view, name="audit-trail"),
    path("api/contracts/status/", contract_status, name="contract-status"),
    path("api/analytics/rate-limits/", rate_limit_analytics_view, name="rate-limit-analytics"),
    path("api/analytics/contracts/health/", all_contracts_health_view, name="all-contracts-health"),
    path("api/meta/db-pool/", db_pool_stats_view, name="db-pool-stats"),
    path("api/schema/versions/", schema_versions_view, name="schema-versions"),
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
    path(
        "api/v1/webhooks/dlq/",
        DLQDeliveryLogViewSet.as_view({"get": "list"}),
        name="webhook-dlq-list",
    ),
    path("api/ingest/", include("soroscan.ingest.urls")),
    path("v1/", include("soroscan.v1.urls")),
    path("_pact/provider-states", provider_states, name="pact-provider-states"),
    path("graphql/", ThrottledGraphQLView.as_view(schema=schema)),
    # JWT Authentication
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # OpenAPI Schema & Docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

# Silk profiling UI — available only when ENABLE_SILK is set
if getattr(settings, "ENABLE_SILK", False):
    urlpatterns += [path("silk/", include("silk.urls", namespace="silk"))]

