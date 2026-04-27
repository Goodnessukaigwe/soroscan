"""
Test URL configuration for SoroScan project (without GraphQL).

Excludes strawberry/GraphQL imports that crash on Linux due to a GDAL
library incompatibility in the Anaconda runtime. All non-GraphQL routes
are registered here so that tests can use reverse() normally.
"""
from django.contrib import admin
from django.urls import include, path

from soroscan.health import health_view, readiness_view
from soroscan.meta_views import db_pool_stats_view
from soroscan.ingest.views import contract_status, rate_limit_analytics_view

urlpatterns = [
    path("", include("django_prometheus.urls")),
    path("admin/", admin.site.urls),
    path("health/", health_view, name="health"),
    path("ready/", readiness_view, name="readiness"),
    path("api/contracts/status/", contract_status, name="contract-status"),
    path("api/analytics/rate-limits/", rate_limit_analytics_view, name="rate-limit-analytics"),
    path("api/meta/db-pool/", db_pool_stats_view, name="db-pool-stats"),
    path("api/ingest/", include("soroscan.ingest.urls")),
]
