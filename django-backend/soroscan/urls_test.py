"""
Test URL configuration for SoroScan project (without GraphQL).
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/ingest/", include("soroscan.ingest.urls")),
]
