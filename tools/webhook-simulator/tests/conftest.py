from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest


def header_value(headers: dict[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


class RecordingHandler(BaseHTTPRequestHandler):
    """Test HTTP handler that records POSTs and returns a configurable response."""

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length)
        record = {
            "path": self.path,
            "headers": {k: v for k, v in self.headers.items()},
            "body": body,
        }
        self.server.requests.append(record)  # type: ignore[attr-defined]

        status = int(getattr(self.server, "status_code", 200))
        fail_first = int(getattr(self.server, "fail_first", 0))
        if fail_first > 0 and len(self.server.requests) <= fail_first:  # type: ignore[attr-defined]
            status = int(getattr(self.server, "fail_status", 500))

        ack_value = getattr(self.server, "ack_value", "ok")
        body_out: bytes = getattr(self.server, "response_body", b"ok")
        extra_headers: dict[str, str] = getattr(self.server, "extra_headers", {})

        self.send_response(status)
        if ack_value is not None:
            self.send_header("X-SoroScan-Ack", ack_value)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body_out)))
        for key, value in extra_headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body_out)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return


@pytest.fixture
def webhook_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingHandler)
    server.requests = []  # type: ignore[attr-defined]
    server.status_code = 200  # type: ignore[attr-defined]
    server.ack_value = "ok"  # type: ignore[attr-defined]
    server.response_body = b"ok"  # type: ignore[attr-defined]
    server.fail_first = 0  # type: ignore[attr-defined]
    server.fail_status = 500  # type: ignore[attr-defined]
    server.extra_headers = {}  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    server.base_url = f"http://{host}:{port}/webhook"  # type: ignore[attr-defined]
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
