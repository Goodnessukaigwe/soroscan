#!/usr/bin/env python3
"""Minimal local webhook receiver for simulator testing."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length)
        print("--- webhook received ---")
        print(f"path: {self.path}")
        for key, value in self.headers.items():
            print(f"{key}: {value}")
        print("body:")
        try:
            print(json.dumps(json.loads(body.decode("utf-8")), indent=2))
        except (UnicodeDecodeError, json.JSONDecodeError):
            print(body)
        print("------------------------")

        response = b"ok"
        self.send_response(200)
        self.send_header("X-SoroScan-Ack", "ok")
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        print(format % args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Print incoming SoroScan webhook deliveries.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), WebhookHandler)
    print(f"Listening on http://{args.host}:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
