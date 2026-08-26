from tests.conftest import header_value
from webhook_simulator.delivery import calculate_backoff, deliver, validate_ack
from webhook_simulator.payload import SAMPLE_EVENT, canonicalize
from webhook_simulator.signing import build_delivery_headers, hmac_signature_header


def test_calculate_backoff_matches_celery_helpers():
    assert calculate_backoff(0, "exponential", 2) == 2
    assert calculate_backoff(1, "exponential", 2) == 4
    assert calculate_backoff(2, "exponential", 2) == 8
    assert calculate_backoff(0, "linear", 2) == 2
    assert calculate_backoff(1, "linear", 2) == 4
    assert calculate_backoff(0, "fixed", 5) == 5
    assert calculate_backoff(3, "fixed", 5) == 5


def test_validate_ack_case_insensitive():
    assert validate_ack({"X-SoroScan-Ack": "ok"}) == (True, "valid")
    assert validate_ack({"x-soroscan-ack": "OK"}) == (True, "valid")
    assert validate_ack({}) == (False, "missing")
    assert validate_ack({"X-SoroScan-Ack": "nope"}) == (False, "invalid")


def test_deliver_success_records_status_and_body(webhook_server):
    webhook_server.response_body = b"accepted"
    body = canonicalize(SAMPLE_EVENT)
    headers = build_delivery_headers(body, secret="s", timestamp="t")
    result = deliver(webhook_server.base_url, body, headers, payload=SAMPLE_EVENT)
    assert result.success is True
    assert result.status == "success"
    assert result.http_status == 200
    assert result.response_body == "accepted"
    assert result.ack_status == "valid"
    assert result.acknowledged is True
    assert len(webhook_server.requests) == 1
    sent = webhook_server.requests[0]
    assert sent["body"] == body
    assert header_value(sent["headers"], "X-SoroScan-Signature") == hmac_signature_header(
        body, "s"
    )


def test_deliver_http_failure(webhook_server):
    webhook_server.status_code = 500
    webhook_server.response_body = b"boom"
    body = canonicalize(SAMPLE_EVENT)
    result = deliver(
        webhook_server.base_url,
        body,
        {"Content-Type": "application/json"},
        payload=SAMPLE_EVENT,
    )
    assert result.success is False
    assert result.status == "failed"
    assert result.http_status == 500
    assert result.response_body == "boom"
    assert "HTTP 500" in (result.error or "")


def test_deliver_retries_until_success(webhook_server):
    webhook_server.fail_first = 2
    webhook_server.fail_status = 503
    sleeps: list[float] = []
    body = canonicalize(SAMPLE_EVENT)
    result = deliver(
        webhook_server.base_url,
        body,
        {"Content-Type": "application/json"},
        payload=SAMPLE_EVENT,
        retries=5,
        backoff_base=1,
        sleep=sleeps.append,
    )
    assert result.success is True
    assert result.attempt_count == 3
    assert sleeps == [1, 2]


def test_require_ack_treats_missing_header_as_failure(webhook_server):
    webhook_server.ack_value = None
    body = canonicalize(SAMPLE_EVENT)
    result = deliver(
        webhook_server.base_url,
        body,
        {"Content-Type": "application/json"},
        payload=SAMPLE_EVENT,
        require_ack=True,
    )
    assert result.success is False
    assert result.ack_status == "missing"


def test_connection_error_is_reported():
    body = canonicalize(SAMPLE_EVENT)
    result = deliver(
        "http://127.0.0.1:1/webhook",
        body,
        {"Content-Type": "application/json"},
        payload=SAMPLE_EVENT,
        timeout=0.5,
    )
    assert result.success is False
    assert result.status == "error"
    assert result.http_status is None
    assert result.error


def test_rejects_non_http_url():
    try:
        deliver("ftp://example.com", b"{}", {}, payload={})
    except ValueError as exc:
        assert "http://" in str(exc)
    else:
        raise AssertionError("expected ValueError")
