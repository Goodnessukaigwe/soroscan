import base64
import hashlib
import hmac

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from webhook_simulator.payload import SAMPLE_EVENT, canonicalize
from webhook_simulator.signing import (
    build_delivery_headers,
    ed25519_public_key_base64,
    ed25519_signature_header,
    hmac_signature_header,
)


def test_hmac_sha256_matches_django_dispatch_algorithm():
    body = canonicalize(SAMPLE_EVENT)
    secret = "secret_0"
    header = hmac_signature_header(body, secret, algorithm="sha256")
    expected = hmac.new(secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256).hexdigest()
    assert header == f"sha256={expected}"


def test_hmac_sha1_prefix():
    body = b'{"hello": "world"}'
    header = hmac_signature_header(body, "abc", algorithm="sha1")
    expected = hmac.new(b"abc", msg=body, digestmod=hashlib.sha1).hexdigest()
    assert header == f"sha1={expected}"


def test_hmac_rejects_unknown_algorithm():
    with pytest.raises(ValueError, match="Unsupported HMAC"):
        hmac_signature_header(b"x", "s", algorithm="md5")


def test_ed25519_signature_verifies():
    seed = "11" * 32
    body = canonicalize(SAMPLE_EVENT)
    header = ed25519_signature_header(body, seed)
    assert header.startswith("ed25519=")
    signature = header.split("=", 1)[1]

    public_b64 = ed25519_public_key_base64(seed)
    public = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_b64))
    public.verify(base64.b64decode(signature), body)


def test_ed25519_seed_must_be_32_bytes():
    with pytest.raises(ValueError, match="32 bytes"):
        ed25519_signature_header(b"x", "abcd")


def test_build_delivery_headers_includes_production_names():
    body = canonicalize(SAMPLE_EVENT)
    headers = build_delivery_headers(
        body,
        secret="whsec",
        timestamp="2026-08-26T00:00:00+00:00",
        ed25519_seed="22" * 32,
        event_name=None,
    )
    assert headers["Content-Type"] == "application/json"
    assert headers["X-SoroScan-Timestamp"] == "2026-08-26T00:00:00+00:00"
    assert headers["X-SoroScan-Signature"].startswith("sha256=")
    assert headers["X-Signature"].startswith("ed25519=")
    assert "X-SoroScan-Event" not in headers


def test_ping_sets_event_header():
    headers = build_delivery_headers(
        b"{}",
        timestamp="t",
        event_name="ping",
    )
    assert headers["X-SoroScan-Event"] == "ping"
    assert "X-SoroScan-Signature" not in headers
