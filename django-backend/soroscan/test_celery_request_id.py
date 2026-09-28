"""
Tests for Celery request correlation ID propagation (issue #1006).

Verifies that:
1. ContextPropagatingTask injects request_id into task headers.
2. task_prerun restores the request_id from headers into the log context.
3. The get_request_id() helper returns the propagated value.
"""
from unittest.mock import MagicMock, patch

from soroscan.log_context import (
    get_request_id,
    log_context_var,
    set_request_id,
)


class TestGetRequestId:
    def setup_method(self):
        log_context_var.set({})

    def test_returns_empty_string_when_not_set(self):
        assert get_request_id() == ""

    def test_returns_set_value(self):
        set_request_id("abc-123")
        assert get_request_id() == "abc-123"


class TestContextPropagatingTask:
    """Test that ContextPropagatingTask.injects the request_id header."""

    def setup_method(self):
        log_context_var.set({})

    def test_apply_async_injects_request_id(self):
        from soroscan.celery import ContextPropagatingTask

        set_request_id("req-42")
        task = ContextPropagatingTask()
        # Mock super().apply_async to avoid needing a broker
        with patch(
            "celery.Task.apply_async", return_value=MagicMock()
        ) as mock_parent:
            task.apply_async(args=("x",), kwargs={})
            # Verify headers were injected
            call_kwargs = mock_parent.call_args[1]
            headers = call_kwargs.get("headers", {})
            assert headers.get("X-Request-ID") == "req-42"

    def test_apply_async_does_not_overwrite_existing_header(self):
        from soroscan.celery import ContextPropagatingTask

        set_request_id("req-new")
        task = ContextPropagatingTask()
        with patch("celery.Task.apply_async", return_value=MagicMock()) as mock_parent:
            # Pass headers as a top-level keyword (Celery convention)
            task.apply_async(args=(), kwargs={}, headers={"X-Request-ID": "req-existing"})
            call_kwargs = mock_parent.call_args[1]
            headers = call_kwargs.get("headers", {})
            assert headers["X-Request-ID"] == "req-existing"

    def test_apply_async_noop_when_no_request_id(self):
        from soroscan.celery import ContextPropagatingTask

        log_context_var.set({})
        task = ContextPropagatingTask()
        with patch("celery.Task.apply_async", return_value=MagicMock()) as mock_parent:
            task.apply_async(args=(), kwargs={})
            call_kwargs = mock_parent.call_args[1]
            headers = call_kwargs.get("headers", {})
            assert "X-Request-ID" not in headers


class TestTaskPrerunRestoresRequestId:
    """Test that the task_prerun signal restores request_id from task headers."""

    def setup_method(self):
        log_context_var.set({})

    def test_restores_request_id_from_headers(self):
        from soroscan.celery import set_celery_task_context

        # Simulate a Celery Request object with headers
        mock_request = MagicMock()
        mock_request.headers = {"X-Request-ID": "from-task-header"}

        set_celery_task_context(
            sender=MagicMock(name="test_task"),
            task_id="task-999",
            request=mock_request,
        )
        assert get_request_id() == "from-task-header"

    def test_no_request_id_when_no_headers(self):
        from soroscan.celery import set_celery_task_context

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.delivery_info = {}

        set_celery_task_context(
            sender=MagicMock(name="test_task"),
            task_id="task-100",
            request=mock_request,
        )
        assert get_request_id() == ""

    def test_no_request_id_when_request_is_none(self):
        from soroscan.celery import set_celery_task_context

        set_celery_task_context(
            sender=MagicMock(name="test_task"),
            task_id="task-101",
            request=None,
        )
        assert get_request_id() == ""
