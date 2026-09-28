"""
Tests for automated ContractEvent partition creation (issue #1403).
"""
import importlib
from datetime import date, datetime, timezone as dt_timezone

import pytest

from soroscan.ingest.tasks import (
    PARTITION_MONTHS_AHEAD,
    create_upcoming_event_partitions,
    event_partition_windows,
)


class TestEventPartitionWindows:
    """Partition month windows are computed deterministically from a date."""

    def test_covers_current_month_and_next_two(self):
        windows = event_partition_windows(today=date(2026, 9, 25))

        assert len(windows) == PARTITION_MONTHS_AHEAD + 1 == 3
        assert [table for table, _, _ in windows] == [
            "contract_events_y2026m09",
            "contract_events_y2026m10",
            "contract_events_y2026m11",
        ]

    def test_ranges_cover_full_months_and_are_contiguous(self):
        windows = event_partition_windows(today=date(2026, 9, 25))

        starts = [start for _, start, _ in windows]
        ends = [end for _, _, end in windows]
        assert starts[0] == "2026-09-01"
        assert ends[0] == "2026-10-01"
        assert ends[0] == starts[1]
        assert ends[1] == starts[2]
        assert ends[2] == "2026-12-01"

    def test_year_boundary_rollover(self):
        windows = event_partition_windows(today=date(2026, 12, 31))

        assert [table for table, _, _ in windows] == [
            "contract_events_y2026m12",
            "contract_events_y2027m01",
            "contract_events_y2027m02",
        ]

    def test_parent_table_name_used_as_prefix(self):
        windows = event_partition_windows(
            parent="ingest_contractevent", today=date(2026, 1, 1)
        )

        assert [table for table, _, _ in windows] == [
            "ingest_contractevent_y2026m01",
            "ingest_contractevent_y2026m02",
            "ingest_contractevent_y2026m03",
        ]


class TestCreateUpcomingEventPartitions:
    """The Celery task is idempotent and never raises (issue #1403)."""

    def test_task_is_scheduled_in_celery_beat(self):
        # Test settings disable CELERY_BEAT_SCHEDULE, so load production settings.
        prod = importlib.import_module("soroscan.settings")
        schedule = getattr(prod, "CELERY_BEAT_SCHEDULE", {})
        task_names = [entry.get("task", "") for entry in schedule.values()]
        assert any("create_upcoming_event_partitions" in name for name in task_names)

    def test_task_runs_without_raising(self):
        # On SQLite (the test backend) the PostgreSQL-only statements are
        # recorded as errors — the task itself must never fail.
        result = create_upcoming_event_partitions()

        assert set(result) == {"parent", "partitions", "created", "errors"}
        assert len(result["partitions"]) == 3
        assert result["partitions"] == [
            table for table, _, _ in event_partition_windows(result["parent"])
        ]

    def test_task_targets_current_month_partition(self):
        now = datetime.now(dt_timezone.utc)

        result = create_upcoming_event_partitions()

        expected = f"{result['parent']}_y{now.year}m{now.month:02d}"
        assert result["partitions"][0] == expected

    def test_sql_statements_created_for_three_months(self):
        """CREATE TABLE IF NOT EXISTS ... PARTITION OF for each target month."""
        from django.db import connection

        executed: list[str] = []

        class _FakeResult:
            def fetchall(self):
                return []

            def fetchone(self):
                return None

        class _RecordingCursor:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, sql, params=None):
                executed.append(sql)
                return _FakeResult()

        # Restore the real cursor before Django's fixture teardown runs.
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(connection, "cursor", lambda: _RecordingCursor())
            result = create_upcoming_event_partitions()

        assert len(executed) == 3
        for sql in executed:
            assert sql.startswith("CREATE TABLE IF NOT EXISTS ")
            assert " PARTITION OF " in sql
            assert " FOR VALUES FROM (" in sql
        assert result["created"] == result["partitions"]
        assert result["errors"] == []
