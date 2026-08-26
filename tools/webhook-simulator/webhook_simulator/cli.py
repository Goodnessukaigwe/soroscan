"""Command-line interface for the SoroScan webhook simulator."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from webhook_simulator import __version__
from webhook_simulator.delivery import (
    BACKOFF_EXPONENTIAL,
    BACKOFF_FIXED,
    BACKOFF_LINEAR,
    DEFAULT_ACK_HEADER,
    DEFAULT_ACK_VALUE,
    DEFAULT_TIMEOUT_SECONDS,
    deliver,
)
from webhook_simulator.display import format_dry_run, format_json, format_text
from webhook_simulator.payload import (
    build_ping_payload,
    canonicalize,
    load_event_json,
    normalize_event,
    utc_now_iso,
)
from webhook_simulator.signing import HMAC_SHA1, HMAC_SHA256, build_delivery_headers

_EPILOG = """examples:
  webhook-simulator --url http://localhost:8080/webhook --sample --secret test-secret
  webhook-simulator --url http://localhost:8080/webhook --event-file event.json
  webhook-simulator --url http://localhost:8080/webhook --ping
  cat event.json | webhook-simulator --url http://localhost:8080/webhook --event -
  webhook-simulator --dry-run --sample --secret test-secret --url http://localhost:8080/webhook

Docker:
  docker compose -f tools/webhook-simulator/docker-compose.yml run --rm webhook-simulator \\
    --url http://host.docker.internal:8080/webhook --sample --secret test-secret
"""


def _read_event_source(source: str) -> dict:
    if source == "-":
        text = sys.stdin.read()
        return load_event_json(text)
    stripped = source.strip()
    if stripped.startswith("{"):
        return load_event_json(stripped)
    path = Path(source)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read event file {source!r}: {exc}") from exc
    return load_event_json(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="webhook-simulator",
        description=(
            "Simulate SoroScan webhook deliveries against a local endpoint "
            "without running the Django backend, Celery, Redis, or PostgreSQL. "
            "Payloads, HMAC signatures, and headers match production dispatch."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--url",
        "-u",
        default=os.getenv("SOROSCAN_WEBHOOK_URL"),
        help="Target webhook URL (or SOROSCAN_WEBHOOK_URL)",
    )
    event_group = parser.add_mutually_exclusive_group()
    event_group.add_argument(
        "--event",
        "-e",
        help="Event JSON object, file path, or '-' for stdin",
    )
    event_group.add_argument(
        "--event-file",
        help="Path to a JSON file containing event data",
    )
    event_group.add_argument(
        "--sample",
        action="store_true",
        help="Deliver a built-in sample transfer event",
    )
    event_group.add_argument(
        "--ping",
        action="store_true",
        help="Send the production ping payload instead of an event",
    )
    parser.add_argument("--contract-id", help="Override contract_id")
    parser.add_argument("--event-type", help="Override event_type")
    parser.add_argument("--ledger", type=int, help="Override ledger")
    parser.add_argument("--event-index", type=int, help="Override event_index")
    parser.add_argument("--tx-hash", help="Override tx_hash")
    parser.add_argument(
        "--payload",
        help="JSON object used as the event payload field",
    )
    parser.add_argument(
        "--secret",
        "-s",
        default=os.getenv("SOROSCAN_WEBHOOK_SECRET"),
        help="HMAC secret (or SOROSCAN_WEBHOOK_SECRET)",
    )
    parser.add_argument(
        "--algorithm",
        choices=[HMAC_SHA256, HMAC_SHA1],
        default=HMAC_SHA256,
        help="HMAC algorithm for X-SoroScan-Signature (default: sha256)",
    )
    parser.add_argument(
        "--unsigned",
        action="store_true",
        help="Skip HMAC signing even if a secret is available",
    )
    parser.add_argument(
        "--ed25519-seed",
        default=os.getenv("WEBHOOK_ED25519_SIGNING_SEED"),
        help="32-byte hex seed for X-Signature Ed25519 (or WEBHOOK_ED25519_SIGNING_SEED)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=0,
        help="Additional retry attempts after the first (production uses 5)",
    )
    parser.add_argument(
        "--backoff",
        choices=[BACKOFF_EXPONENTIAL, BACKOFF_LINEAR, BACKOFF_FIXED],
        default=BACKOFF_EXPONENTIAL,
        help="Retry backoff strategy (default: exponential)",
    )
    parser.add_argument(
        "--backoff-base",
        type=int,
        default=2,
        help="Base delay in seconds for retry backoff (default: 2)",
    )
    parser.add_argument(
        "--ack-header",
        default=DEFAULT_ACK_HEADER,
        help=f"Acknowledgement response header (default: {DEFAULT_ACK_HEADER})",
    )
    parser.add_argument(
        "--ack-value",
        default=DEFAULT_ACK_VALUE,
        help=f"Expected acknowledgement header value (default: {DEFAULT_ACK_VALUE})",
    )
    parser.add_argument(
        "--require-ack",
        action="store_true",
        help="Treat missing/invalid ack headers as delivery failure (production SLA)",
    )
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        metavar="NAME:VALUE",
        help="Extra request header (repeatable)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the signed request without sending it",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    return parser


def _parse_extra_headers(values: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for item in values:
        if ":" not in item:
            raise ValueError(f"Invalid --header {item!r}; expected NAME:VALUE")
        name, value = item.split(":", 1)
        name = name.strip()
        if not name:
            raise ValueError(f"Invalid --header {item!r}; header name is empty")
        headers[name] = value.strip()
    return headers


def _collect_overrides(args: argparse.Namespace) -> dict:
    overrides: dict = {}
    if args.contract_id:
        overrides["contract_id"] = args.contract_id
    if args.event_type:
        overrides["event_type"] = args.event_type
    if args.ledger is not None:
        overrides["ledger"] = args.ledger
    if args.event_index is not None:
        overrides["event_index"] = args.event_index
    if args.tx_hash:
        overrides["tx_hash"] = args.tx_hash
    if args.payload:
        payload = load_event_json(args.payload)
        overrides["payload"] = payload
    return overrides


def run(args: argparse.Namespace) -> int:
    if not args.url and not args.dry_run:
        print("Error: --url is required unless --dry-run is set.", file=sys.stderr)
        return 2
    url = args.url or "http://localhost:8080/webhook"

    extra_headers = _parse_extra_headers(args.header)
    overrides = _collect_overrides(args)
    timestamp = utc_now_iso()

    if args.ping:
        payload = build_ping_payload(timestamp=timestamp)
        event_name = "ping"
    else:
        event_name = None
        source: dict = {}
        if args.event_file:
            source = _read_event_source(args.event_file)
        elif args.event:
            source = _read_event_source(args.event)
        elif not args.sample and not overrides:
            print(
                "Error: provide --event, --event-file, --sample, --ping, or field overrides.",
                file=sys.stderr,
            )
            return 2
        payload = normalize_event(source, overrides=overrides)

    payload_bytes = canonicalize(payload)
    secret = None if args.unsigned else args.secret
    if not args.ping and secret is None and not args.unsigned:
        print(
            "Warning: no HMAC secret provided; request will be unsigned. "
            "Pass --secret or set SOROSCAN_WEBHOOK_SECRET (or --unsigned to silence this).",
            file=sys.stderr,
        )

    headers = build_delivery_headers(
        payload_bytes,
        secret=secret,
        algorithm=args.algorithm,
        timestamp=timestamp,
        ed25519_seed=args.ed25519_seed,
        extra_headers=extra_headers,
        event_name=event_name,
    )

    if args.dry_run:
        print(
            format_dry_run(
                url, payload, payload_bytes, headers, output=args.output
            )
        )
        return 0

    if args.retries < 0:
        print("Error: --retries cannot be negative.", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("Error: --timeout must be positive.", file=sys.stderr)
        return 2

    result = deliver(
        url,
        payload_bytes,
        headers,
        payload=payload,
        timeout=args.timeout,
        retries=args.retries,
        backoff_strategy=args.backoff,
        backoff_base=args.backoff_base,
        ack_header=args.ack_header,
        ack_value=args.ack_value,
        require_ack=args.require_ack,
    )
    rendered = format_json(result) if args.output == "json" else format_text(result)
    print(rendered)
    return 0 if result.success else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
