"""Validation for Prometheus alert rules and operational metrics."""

import asyncio
from pathlib import Path

import yaml
from django.http import JsonResponse
from django.test import RequestFactory
from prometheus_client import REGISTRY

from soroscan.db_pool import calculate_pool_limits
from soroscan.ingest import metrics
from soroscan.monitoring import ErrorRateMetricsMiddleware, http_responses_total

ROOT = Path(__file__).resolve().parents[4]
RULES = ROOT / "k8s" / "prometheus-rules.yaml"


def _alerts():
    document = yaml.safe_load(RULES.read_text())
    return {
        rule["alert"]: rule
        for group in document["spec"]["groups"]
        for rule in group["rules"]
    }


def test_error_rate_alerts_include_sla_thresholds_and_root_cause():
    alerts = _alerts()
    warning = alerts["SoroScanApiErrorRateHigh"]
    critical = alerts["SoroScanApiErrorRateCritical"]
    assert "> 1" in warning["expr"]
    assert "> 5" in critical["expr"]
    for alert in (warning, critical):
        assert alert["labels"]["service"] == "soroscan-backend"
        assert "error_type" in alert["annotations"]["root_cause_query"]
        assert "view" in alert["annotations"]["root_cause_query"]


def test_celery_queue_and_failure_alerts_exist():
    alerts = _alerts()
    assert "> 100" in alerts["SoroScanCeleryQueueDepthHigh"]["expr"]
    assert 'status="failure"' in alerts["SoroScanCeleryFailureRateHigh"]["expr"]


def test_pool_limits_scale_with_workers_and_obey_hard_limit():
    assert calculate_pool_limits(workers=2, connections_per_worker=4) == (2, 8)
    assert calculate_pool_limits(
        workers=20, connections_per_worker=4, hard_limit=40
    ) == (2, 40)


def test_celery_metrics_are_registered():
    registered = REGISTRY._names_to_collectors
    assert "soroscan_celery_tasks" in registered
    assert "soroscan_celery_tasks_active" in registered
    assert "soroscan_celery_task_duration_seconds" in registered
    assert metrics.celery_tasks_total is registered["soroscan_celery_tasks"]


def test_error_middleware_records_service_and_root_cause_labels():
    before = http_responses_total.labels(
        service="soroscan-backend",
        status_class="5xx",
        view="unresolved",
        error_type="http_503",
    )._value.get()

    async def get_response(request):
        return JsonResponse({"detail": "down"}, status=503)

    middleware = ErrorRateMetricsMiddleware(get_response)
    response = asyncio.run(middleware(RequestFactory().get("/health")))
    after = http_responses_total.labels(
        service="soroscan-backend",
        status_class="5xx",
        view="unresolved",
        error_type="http_503",
    )._value.get()
    assert response.status_code == 503
    assert after == before + 1
