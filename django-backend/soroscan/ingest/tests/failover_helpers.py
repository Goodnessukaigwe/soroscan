"""Reusable failure-injection helpers at the health-check abstraction boundary.

These patch the same surfaces `soroscan.health` uses (DB cursor, cache, RPC
HTTP, Celery inspect) so failover tests stay aligned with production probes.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import requests
from celery.exceptions import TimeoutError as CeleryTimeoutError
from django.core.cache import cache
from django.db import connection


@contextmanager
def database_unavailable(message: str = "DB connection refused"):
    def _fail():
        raise Exception(message)

    with patch.object(connection, "cursor", side_effect=_fail):
        yield


@contextmanager
def redis_unavailable(message: str = "Redis down"):
    with patch("soroscan.health.redis_lib.Redis.from_url", side_effect=Exception(message)):
        yield


@contextmanager
def rpc_timeout(message: str = "RPC timed out"):
    with patch("soroscan.health.requests.post", side_effect=requests.exceptions.Timeout(message)):
        yield


@contextmanager
def rpc_healthy():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"result": {"status": "healthy"}}

    mock_redis = MagicMock()
    mock_redis.ping.return_value = True

    with patch("soroscan.health.requests.post", return_value=mock_response), \
         patch("soroscan.health.redis_lib.Redis.from_url", return_value=mock_redis):
        yield


@contextmanager
def workers_unresponsive(mode: str = "empty"):
    if mode == "timeout":

        def raise_timeout(timeout=None):
            raise CeleryTimeoutError("worker ping timeout")

        with patch("soroscan.health.app.control.inspect", side_effect=raise_timeout):
            yield
        return

    class EmptyInspect:
        def ping(self):
            return {}

    with patch(
        "soroscan.health.app.control.inspect",
        lambda timeout=None: EmptyInspect(),
    ):
        yield


@contextmanager
def workers_healthy(worker_status=None):
    status = worker_status or {
        "worker1@host-a": {"ok": "pong"},
        "worker2@host-b": {"ok": "pong"},
    }

    class HealthyInspect:
        def ping(self):
            return status

    with patch(
        "soroscan.health.app.control.inspect",
        lambda timeout=None: HealthyInspect(),
    ):
        yield
