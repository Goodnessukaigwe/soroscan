"""Webhook signature helpers matching production delivery conventions.

HMAC-SHA256/SHA1  → ``X-SoroScan-Signature: sha256=<hex>``
Ed25519           → ``X-Signature: ed25519=<base64>``

See ``django-backend/soroscan/ingest/tasks.py`` (``_build_webhook_signature_header``)
and ``django-backend/soroscan/webhook_signing.py``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

HMAC_SHA256 = "sha256"
HMAC_SHA1 = "sha1"
_ED25519_PREFIX = "ed25519="


def hmac_signature_header(
    payload_bytes: bytes,
    secret: str,
    algorithm: str = HMAC_SHA256,
) -> str:
    """
    Build ``X-SoroScan-Signature`` using the same HMAC algorithm as Celery dispatch.

    ``algorithm`` is ``sha256`` (default) or ``sha1``.
    """
    normalized = (algorithm or HMAC_SHA256).lower()
    if normalized == HMAC_SHA1:
        digestmod = hashlib.sha1
        prefix = HMAC_SHA1
    elif normalized == HMAC_SHA256:
        digestmod = hashlib.sha256
        prefix = HMAC_SHA256
    else:
        raise ValueError(f"Unsupported HMAC algorithm: {algorithm!r} (use sha256 or sha1)")

    sig_hex = hmac.new(
        secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=digestmod,
    ).hexdigest()
    return f"{prefix}={sig_hex}"


def ed25519_signature_header(payload_bytes: bytes, seed_hex: str) -> str:
    """
    Build ``X-Signature: ed25519=<base64>`` from a 32-byte hex seed.

    Matches ``WEBHOOK_ED25519_SIGNING_SEED`` used by the Django backend.
    """
    seed = _seed_bytes(seed_hex)
    signature = Ed25519PrivateKey.from_private_bytes(seed).sign(payload_bytes)
    encoded = base64.b64encode(signature).decode("ascii")
    return f"{_ED25519_PREFIX}{encoded}"


def ed25519_public_key_base64(seed_hex: str) -> str:
    """Return the base64-encoded raw public key for the given seed."""
    seed = _seed_bytes(seed_hex)
    public = Ed25519PrivateKey.from_private_bytes(seed).public_key()
    raw = public.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def _seed_bytes(seed_hex: str) -> bytes:
    value = (seed_hex or "").strip()
    if not value:
        raise ValueError("Ed25519 signing seed is empty")
    try:
        seed = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError("Ed25519 signing seed must be hex-encoded") from exc
    if len(seed) != 32:
        raise ValueError("Ed25519 signing seed must be 32 bytes (64 hex characters)")
    return seed


def build_delivery_headers(
    payload_bytes: bytes,
    *,
    secret: str | None = None,
    algorithm: str = HMAC_SHA256,
    timestamp: str,
    ed25519_seed: str | None = None,
    extra_headers: Mapping[str, str] | None = None,
    event_name: str | None = None,
) -> dict[str, str]:
    """Assemble outbound headers for a simulated delivery."""
    headers = {
        "Content-Type": "application/json",
        "X-SoroScan-Timestamp": timestamp,
        "User-Agent": "SoroScan-Webhook-Simulator/0.1.0",
    }
    if event_name:
        headers["X-SoroScan-Event"] = event_name
    if secret:
        headers["X-SoroScan-Signature"] = hmac_signature_header(
            payload_bytes, secret, algorithm=algorithm
        )
    if ed25519_seed:
        headers["X-Signature"] = ed25519_signature_header(payload_bytes, ed25519_seed)
    if extra_headers:
        headers.update(extra_headers)
    return headers
