"""
Tests for Celery task timeout monitoring.
"""

import logging
from unittest.mock import MagicMock, patch

from soroscan.ingest.tasks import (
    _log_timeout_warning,
    _start_timeout_monitor,
    _stop_timeout_monitor,
    _task_timeout_timers,
)


def test_timeout_monitor_lifecycle():
    """Ensure timer starts at 80% and cancels on completion."""
    task_mock = MagicMock()
    task_mock.name = "test.slow_task"
    task_mock.soft_time_limit = 100
    task_mock.time_limit = None
    task_mock.request.soft_time_limit = None
    task_mock.request.time_limit = None

    with patch("soroscan.ingest.tasks.threading.Timer") as mock_timer_class:
        mock_timer_instance = MagicMock()
        mock_timer_class.return_value = mock_timer_instance

        # Simulate task start
        _start_timeout_monitor(task_id="task-123", task=task_mock)

        # Timer should be set for 80 seconds (80% of 100s) with 20s remaining
        mock_timer_class.assert_called_once_with(
            80.0, _log_timeout_warning, args=("test.slow_task", 20.0)
        )
        mock_timer_instance.start.assert_called_once()
        assert "task-123" in _task_timeout_timers

        # Simulate task finish
        _stop_timeout_monitor(task_id="task-123", task=task_mock)

        mock_timer_instance.cancel.assert_called_once()
        assert "task-123" not in _task_timeout_timers


def test_timeout_monitor_no_timeout():
    """Ensure no timer is created if task has no timeout."""
    task_mock = MagicMock()
    task_mock.name = "test.fast_task"
    task_mock.soft_time_limit = None
    task_mock.time_limit = None
    task_mock.request.soft_time_limit = None
    task_mock.request.time_limit = None

    with patch("soroscan.ingest.tasks.threading.Timer") as mock_timer_class:
        _start_timeout_monitor(task_id="task-456", task=task_mock)
        mock_timer_class.assert_not_called()
        assert "task-456" not in _task_timeout_timers


def test_log_timeout_warning(caplog):
    """Verify the warning log contains task name and remaining time."""
    with caplog.at_level(logging.WARNING):
        _log_timeout_warning("test.slow_task", 15.5)

    assert "Task test.slow_task is approaching timeout" in caplog.text
    assert "15.5 seconds remaining" in caplog.text
