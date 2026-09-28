"""Tests for Celery task queue monitoring (issue #1292).

Covers:
- Prometheus metrics are registered and properly labelled
- celery_tasks_total increments on task completion
- celery_tasks_active tracks running tasks
- celery_task_duration_seconds records durations
- /api/celery/status/ endpoint returns expected structure
- Prometheus alerting rules for queue depth and failure rate exist
- OperationalHealthCollector exposes queue depth and worker metrics
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import yaml
from django.test import TestCase
from prometheus_client import REGISTRY

REPO_ROOT = Path(__file__).resolve().parents[4]
RULES_PATH = REPO_ROOT / "k8s" / "prometheus-rules.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_value(metric_name: str, labels: dict[str, str]) -> float | None:
    """Return the current value of a Prometheus sample, or None if not found."""
    return REGISTRY.get_sample_value(metric_name, labels)


# ---------------------------------------------------------------------------
# Prometheus metrics registration
# ---------------------------------------------------------------------------

class CeleryMetricsRegisteredTests(TestCase):
    """The metrics module must export the expected Celery counters/gauges."""

    def test_celery_tasks_total_is_registered(self):
        from soroscan.ingest.metrics import celery_tasks_total

        self.assertIsNotNone(celery_tasks_total)

    def test_celery_tasks_active_is_registered(self):
        from soroscan.ingest.metrics import celery_tasks_active

        self.assertIsNotNone(celery_tasks_active)

    def test_celery_task_duration_seconds_is_registered(self):
        from soroscan.ingest.metrics import celery_task_duration_seconds

        self.assertIsNotNone(celery_task_duration_seconds)

    def test_no_duplicate_registration_on_reimport(self):
        """Importing metrics.py a second time must not raise ValueError."""
        import importlib
        import soroscan.ingest.metrics as metrics_module

        try:
            importlib.reload(metrics_module)
        except ValueError as exc:
            self.fail(f"Re-importing metrics.py raised ValueError: {exc}")


# ---------------------------------------------------------------------------
# Signal handler: task completion
# ---------------------------------------------------------------------------

class CelerySignalHandlerTests(TestCase):
    """Celery signal handlers increment/decrement metrics correctly."""

    def _get_tasks_total(self, task_name: str, status: str, error_type: str = "") -> float:
        value = REGISTRY.get_sample_value(
            "soroscan_celery_tasks_total",
            {"task_name": task_name, "status": status, "error_type": error_type},
        )
        return value or 0.0

    def _get_tasks_active(self, task_name: str) -> float:
        value = REGISTRY.get_sample_value(
            "soroscan_celery_tasks_active",
            {"task_name": task_name},
        )
        return value or 0.0

    def test_task_completion_increments_total(self):
        """record_celery_task_completion should inc celery_tasks_total."""
        from soroscan.celery import record_celery_task_completion

        task_name = "soroscan.test.dummy_task_completion"
        before = self._get_tasks_total(task_name, "success")

        sender = MagicMock()
        sender.name = task_name

        # Prime the started_at so duration can be recorded
        from soroscan.celery import _task_started_at
        import time

        task_id = "test-task-id-completion"
        _task_started_at[task_id] = time.monotonic() - 0.1

        record_celery_task_completion(
            sender=sender, task_id=task_id, state="SUCCESS"
        )

        after = self._get_tasks_total(task_name, "success")
        self.assertGreater(after, before)

    def test_task_completion_decrements_active(self):
        """record_celery_task_completion should dec celery_tasks_active."""
        from soroscan.ingest.metrics import celery_tasks_active
        from soroscan.celery import record_celery_task_completion

        task_name = "soroscan.test.dummy_task_active"
        celery_tasks_active.labels(task_name=task_name).inc()

        before = self._get_tasks_active(task_name)

        sender = MagicMock()
        sender.name = task_name

        from soroscan.celery import _task_started_at
        import time

        task_id = "test-task-id-active"
        _task_started_at[task_id] = time.monotonic() - 0.05

        record_celery_task_completion(
            sender=sender, task_id=task_id, state="SUCCESS"
        )

        after = self._get_tasks_active(task_name)
        self.assertLess(after, before)

    def test_task_failure_increments_total_with_error_type(self):
        """record_celery_task_failure should record failure + error_type label."""
        from soroscan.celery import record_celery_task_failure

        task_name = "soroscan.test.dummy_task_failure"
        before = self._get_tasks_total(task_name, "failure", "ValueError")

        sender = MagicMock()
        sender.name = task_name
        exception = ValueError("test error")

        record_celery_task_failure(sender=sender, exception=exception)

        after = self._get_tasks_total(task_name, "failure", "ValueError")
        self.assertGreater(after, before)

    def test_task_prerun_increments_active(self):
        """set_celery_task_context should inc celery_tasks_active."""
        from soroscan.celery import set_celery_task_context

        task_name = "soroscan.test.dummy_task_prerun"
        before = self._get_tasks_active(task_name)

        sender = MagicMock()
        sender.name = task_name

        with patch("soroscan.log_context.set_task_id"):
            set_celery_task_context(sender=sender, task_id="task-123")

        after = self._get_tasks_active(task_name)
        self.assertGreater(after, before)


# ---------------------------------------------------------------------------
# Duration histogram
# ---------------------------------------------------------------------------

class CeleryDurationTests(TestCase):
    def test_task_duration_recorded(self):
        """record_celery_task_completion should observe into duration histogram."""
        import time

        from soroscan.celery import _task_started_at, record_celery_task_completion

        task_name = "soroscan.test.duration_recording"
        task_id = "duration-test-id"
        _task_started_at[task_id] = time.monotonic() - 0.2

        sender = MagicMock()
        sender.name = task_name

        before_count = REGISTRY.get_sample_value(
            "soroscan_celery_task_duration_seconds_count",
            {"task_name": task_name},
        ) or 0.0

        record_celery_task_completion(sender=sender, task_id=task_id, state="SUCCESS")

        after_count = REGISTRY.get_sample_value(
            "soroscan_celery_task_duration_seconds_count",
            {"task_name": task_name},
        ) or 0.0

        self.assertGreater(after_count, before_count)

    def test_duration_not_recorded_for_missing_task_id(self):
        """If task_id is not in _task_started_at, no histogram observation."""
        from soroscan.celery import _task_started_at, record_celery_task_completion

        task_name = "soroscan.test.no_start_time"
        task_id = "non-existent-id-xyz"

        # Ensure it's not in the dict
        _task_started_at.pop(task_id, None)

        sender = MagicMock()
        sender.name = task_name

        before_count = REGISTRY.get_sample_value(
            "soroscan_celery_task_duration_seconds_count",
            {"task_name": task_name},
        ) or 0.0

        record_celery_task_completion(sender=sender, task_id=task_id, state="SUCCESS")

        after_count = REGISTRY.get_sample_value(
            "soroscan_celery_task_duration_seconds_count",
            {"task_name": task_name},
        ) or 0.0

        # Count should not have increased since the task was never pre-run
        self.assertEqual(before_count, after_count)


# ---------------------------------------------------------------------------
# /api/celery/status/ endpoint
# ---------------------------------------------------------------------------

class CeleryStatusViewTests(TestCase):
    def _get(self, url: str, user: Any = None):
        from rest_framework.test import APIClient

        client = APIClient()
        if user:
            client.force_authenticate(user=user)
        return client.get(url)

    def test_endpoint_requires_authentication(self):
        response = self._get("/api/celery/status/")
        # 401 Unauthorized or 403 Forbidden without auth
        self.assertIn(response.status_code, [401, 403])

    def test_endpoint_returns_200_for_authenticated_user(self):
        from django.contrib.auth.models import User

        user = User.objects.create_user("testuser_celery", password="pass")

        with patch("redis.Redis") as mock_redis_cls:
            mock_redis = MagicMock()
            mock_redis.llen.return_value = 0
            mock_redis_cls.from_url.return_value = mock_redis

            with patch("soroscan.celery.app.control") as mock_control:
                mock_control.inspect.return_value.ping.return_value = {}

                response = self._get("/api/celery/status/", user=user)
                self.assertEqual(response.status_code, 200)

    def test_response_has_required_top_level_keys(self):
        from django.contrib.auth.models import User

        user = User.objects.create_user("testuser_celery2", password="pass")

        with patch("redis.Redis") as mock_redis_cls:
            mock_redis = MagicMock()
            mock_redis.llen.return_value = 5
            mock_redis_cls.from_url.return_value = mock_redis

            with patch("soroscan.celery.app.control") as mock_control:
                mock_control.inspect.side_effect = Exception("no broker")

                response = self._get("/api/celery/status/", user=user)
                self.assertEqual(response.status_code, 200)
                data = response.json()
                for key in ("queues", "workers", "workers_online", "active_tasks", "metrics"):
                    self.assertIn(key, data, f"Key '{key}' missing from response")

    def test_response_queues_contains_monitored_queues(self):
        from django.contrib.auth.models import User

        user = User.objects.create_user("testuser_celery3", password="pass")

        with patch("redis.Redis") as mock_redis_cls:
            mock_redis = MagicMock()
            mock_redis.llen.return_value = 3
            mock_redis_cls.from_url.return_value = mock_redis

            with patch("soroscan.celery.app.control") as mock_control:
                mock_control.inspect.side_effect = Exception("no broker")

                response = self._get("/api/celery/status/", user=user)
                data = response.json()
                queues = data["queues"]
                for queue in ("high_priority", "default", "low_priority", "backfill"):
                    self.assertIn(queue, queues)

    def test_response_reflects_queue_depths_from_redis(self):
        from django.contrib.auth.models import User

        user = User.objects.create_user("testuser_celery4", password="pass")

        with patch("redis.Redis") as mock_redis_cls:
            mock_redis = MagicMock()
            mock_redis.llen.return_value = 42
            mock_redis_cls.from_url.return_value = mock_redis

            with patch("soroscan.celery.app.control") as mock_control:
                mock_control.inspect.side_effect = Exception("no broker")

                response = self._get("/api/celery/status/", user=user)
                data = response.json()
                for depth in data["queues"].values():
                    self.assertEqual(depth, 42)

    def test_response_workers_online_reflects_ping(self):
        from django.contrib.auth.models import User

        user = User.objects.create_user("testuser_celery5", password="pass")

        with patch("redis.Redis") as mock_redis_cls:
            mock_redis = MagicMock()
            mock_redis.llen.return_value = 0
            mock_redis_cls.from_url.return_value = mock_redis

            with patch("soroscan.celery.app.control") as mock_control:
                mock_control.inspect.return_value.ping.return_value = {
                    "celery@worker1": {"ok": "pong"},
                    "celery@worker2": {"ok": "pong"},
                }
                response = self._get("/api/celery/status/", user=user)
                data = response.json()
                self.assertEqual(data["workers_online"], 2)
                self.assertIn("celery@worker1", data["workers"])
                self.assertEqual(data["workers"]["celery@worker1"], "online")

    def test_response_metrics_has_failure_rate(self):
        from django.contrib.auth.models import User

        user = User.objects.create_user("testuser_celery6", password="pass")

        with patch("redis.Redis") as mock_redis_cls:
            mock_redis = MagicMock()
            mock_redis.llen.return_value = 0
            mock_redis_cls.from_url.return_value = mock_redis

            with patch("soroscan.celery.app.control") as mock_control:
                mock_control.inspect.side_effect = Exception("no broker")

                response = self._get("/api/celery/status/", user=user)
                data = response.json()
                self.assertIn("task_failure_rate", data["metrics"])

    def test_redis_failure_does_not_crash_endpoint(self):
        from django.contrib.auth.models import User

        user = User.objects.create_user("testuser_celery7", password="pass")

        with patch("redis.Redis") as mock_redis_cls:
            mock_redis_cls.from_url.side_effect = ConnectionError("Redis down")

            with patch("soroscan.celery.app.control") as mock_control:
                mock_control.inspect.side_effect = Exception("no broker")

                response = self._get("/api/celery/status/", user=user)
                # Should still return 200 with fallback -1 values for queues
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertIn("queues", data)


# ---------------------------------------------------------------------------
# Prometheus alert rules
# ---------------------------------------------------------------------------

class CeleryAlertRulesTests(TestCase):
    """The k8s prometheus-rules.yaml must define the required Celery alerts."""

    def _load_rules(self):
        self.assertTrue(
            RULES_PATH.exists(),
            f"prometheus-rules.yaml not found at {RULES_PATH}",
        )
        with open(RULES_PATH) as fh:
            return yaml.safe_load(fh)

    def _collect_alerts(self, rules: dict) -> dict:
        alerts: dict[str, dict] = {}
        for group in rules["spec"]["groups"]:
            for rule in group["rules"]:
                if "alert" in rule:
                    alerts[rule["alert"]] = rule
        return alerts

    def test_celery_queue_depth_high_alert_exists(self):
        alerts = self._collect_alerts(self._load_rules())
        self.assertIn("SoroScanCeleryQueueDepthHigh", alerts)

    def test_celery_failure_rate_high_alert_exists(self):
        alerts = self._collect_alerts(self._load_rules())
        self.assertIn("SoroScanCeleryFailureRateHigh", alerts)

    def test_queue_depth_alert_uses_correct_metric(self):
        alerts = self._collect_alerts(self._load_rules())
        expr = alerts["SoroScanCeleryQueueDepthHigh"]["expr"]
        self.assertIn("soroscan_celery_queue_depth", expr)

    def test_queue_depth_alert_has_threshold_100(self):
        alerts = self._collect_alerts(self._load_rules())
        expr = alerts["SoroScanCeleryQueueDepthHigh"]["expr"]
        self.assertIn("> 100", expr)

    def test_failure_rate_alert_uses_correct_metric(self):
        alerts = self._collect_alerts(self._load_rules())
        expr = alerts["SoroScanCeleryFailureRateHigh"]["expr"]
        self.assertIn("soroscan_celery_tasks_total", expr)

    def test_failure_rate_alert_threshold_is_5_percent(self):
        alerts = self._collect_alerts(self._load_rules())
        expr = alerts["SoroScanCeleryFailureRateHigh"]["expr"]
        self.assertIn("> 5", expr)

    def test_queue_depth_alert_has_severity_warning(self):
        alerts = self._collect_alerts(self._load_rules())
        labels = alerts["SoroScanCeleryQueueDepthHigh"]["labels"]
        self.assertEqual(labels["severity"], "warning")

    def test_failure_rate_alert_has_severity_critical(self):
        alerts = self._collect_alerts(self._load_rules())
        labels = alerts["SoroScanCeleryFailureRateHigh"]["labels"]
        self.assertEqual(labels["severity"], "critical")

    def test_failure_rate_alert_has_root_cause_query_annotation(self):
        alerts = self._collect_alerts(self._load_rules())
        annotations = alerts["SoroScanCeleryFailureRateHigh"].get("annotations", {})
        self.assertIn("root_cause_query", annotations)


# ---------------------------------------------------------------------------
# OperationalHealthCollector queue depth and worker metrics
# ---------------------------------------------------------------------------

class OperationalHealthCollectorCeleryTests(TestCase):
    def test_collector_yields_queue_depth_metric(self):
        from soroscan.operational_metrics import OperationalHealthCollector

        collector = OperationalHealthCollector()
        descriptions = list(collector.describe())
        names = [d.name for d in descriptions]
        self.assertIn("soroscan_celery_queue_depth", names)

    def test_collector_yields_workers_online_metric(self):
        from soroscan.operational_metrics import OperationalHealthCollector

        collector = OperationalHealthCollector()
        descriptions = list(collector.describe())
        names = [d.name for d in descriptions]
        self.assertIn("soroscan_celery_workers_online", names)

    def test_collect_queue_depth_handles_redis_error_gracefully(self):
        """If Redis is down, collect() should not raise — it yields an empty metric."""
        from soroscan.operational_metrics import OperationalHealthCollector

        collector = OperationalHealthCollector()
        with patch("soroscan.operational_metrics.Redis") as mock_redis_cls:
            mock_redis_cls.from_url.side_effect = ConnectionError("Redis down")
            try:
                metrics = list(collector.collect())
            except Exception as exc:
                self.fail(f"collect() raised {exc!r} on Redis failure")
            # The depth metric should still be yielded (with no samples)
            depth_metrics = [m for m in metrics if m.name == "soroscan_celery_queue_depth"]
            self.assertTrue(len(depth_metrics) >= 1)

    def test_collect_workers_online_handles_celery_error_gracefully(self):
        """If Celery inspect fails, collect() should not raise."""
        from soroscan.operational_metrics import OperationalHealthCollector

        collector = OperationalHealthCollector()
        with patch("soroscan.operational_metrics.Redis") as mock_redis_cls:
            mock_redis = MagicMock()
            mock_redis.llen.return_value = 0
            mock_redis_cls.from_url.return_value = mock_redis

            with patch("soroscan.celery.app.control") as mock_control:
                mock_control.inspect.side_effect = Exception("worker error")
                try:
                    metrics = list(collector.collect())
                except Exception as exc:
                    self.fail(f"collect() raised {exc!r} on Celery failure")

                worker_metrics = [
                    m for m in metrics if m.name == "soroscan_celery_workers_online"
                ]
                self.assertTrue(len(worker_metrics) >= 1)
