"""Tests for the detach_expired_event_partitions Celery task (issue #1404)."""
from datetime import datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch

from django.test import override_settings

from soroscan.ingest.tasks import detach_expired_event_partitions

NOW = datetime(2026, 10, 1, tzinfo=dt_timezone.utc)

PARTITIONS = [
    (
        "ingest_contractevent_y2026m05",
        "FOR VALUES FROM ('2026-05-01 00:00:00+00') TO ('2026-06-01 00:00:00+00')",
    ),
    (
        "ingest_contractevent_y2026m06",
        "FOR VALUES FROM ('2026-06-01 00:00:00+00') TO ('2026-07-01 00:00:00+00')",
    ),
    (
        "ingest_contractevent_y2026m07",
        "FOR VALUES FROM ('2026-07-01 00:00:00+00') TO ('2026-08-01 00:00:00+00')",
    ),
    ("ingest_contractevent_default", "DEFAULT"),
]


def _mock_connection(vendor="postgresql", partitions=PARTITIONS):
    cursor = MagicMock()
    cursor.fetchall.return_value = partitions
    connection = MagicMock()
    connection.vendor = vendor
    connection.ops.quote_name = lambda name: f'"{name}"'
    connection.cursor.return_value.__enter__.return_value = cursor
    return connection, cursor


def _executed_sql(cursor):
    return [c.args[0] for c in cursor.execute.call_args_list]


@override_settings(SOROSCAN_EVENT_RETENTION_DAYS=90)
@patch("soroscan.ingest.tasks.timezone.now", return_value=NOW)
def test_detaches_only_partitions_before_cutoff(_now):
    # cutoff = 2026-07-03 → only the May and June partitions are fully expired.
    connection, cursor = _mock_connection()
    with patch("django.db.connection", connection):
        detached = detach_expired_event_partitions()

    assert detached == [
        "ingest_contractevent_y2026m05",
        "ingest_contractevent_y2026m06",
    ]
    assert _executed_sql(cursor)[1:] == [
        'ALTER TABLE "ingest_contractevent" DETACH PARTITION "ingest_contractevent_y2026m05"',
        'ALTER TABLE "ingest_contractevent" DETACH PARTITION "ingest_contractevent_y2026m06"',
    ]


@override_settings(SOROSCAN_EVENT_RETENTION_DAYS=30)
@patch("soroscan.ingest.tasks.timezone.now", return_value=NOW)
def test_retention_setting_controls_cutoff(_now):
    # cutoff = 2026-09-01 → July partition is now expired too; DEFAULT never is.
    connection, _ = _mock_connection()
    with patch("django.db.connection", connection):
        detached = detach_expired_event_partitions()

    assert "ingest_contractevent_y2026m07" in detached
    assert "ingest_contractevent_default" not in detached


@override_settings(SOROSCAN_EVENT_RETENTION_DAYS=90)
@patch("soroscan.ingest.tasks.timezone.now", return_value=NOW)
def test_logs_detached_partition_names(_now, caplog):
    connection, _ = _mock_connection()
    with patch("django.db.connection", connection), caplog.at_level("INFO"):
        detach_expired_event_partitions()

    assert "ingest_contractevent_y2026m05" in caplog.text
    assert "ingest_contractevent_y2026m06" in caplog.text


@override_settings(SOROSCAN_EVENT_RETENTION_DAYS=90)
@patch("soroscan.ingest.tasks.timezone.now", return_value=NOW)
def test_failed_detach_is_skipped(_now):
    connection, cursor = _mock_connection()

    def execute(sql, params=None):
        if "y2026m05" in sql:
            raise RuntimeError("lock timeout")

    cursor.execute.side_effect = execute
    with patch("django.db.connection", connection):
        detached = detach_expired_event_partitions()

    assert detached == ["ingest_contractevent_y2026m06"]


def test_noop_on_non_postgres():
    connection, cursor = _mock_connection(vendor="sqlite")
    with patch("django.db.connection", connection):
        assert detach_expired_event_partitions() == []
    cursor.execute.assert_not_called()
