from webhook_simulator.delivery import DeliveryAttempt, DeliveryResult
from webhook_simulator.display import format_dry_run, format_json, format_text, result_to_dict
from webhook_simulator.payload import SAMPLE_EVENT, canonicalize
from webhook_simulator.signing import build_delivery_headers


def _sample_result(**kwargs) -> DeliveryResult:
    defaults = dict(
        url="http://localhost:8080/webhook",
        status="success",
        http_status=200,
        reason="Delivered",
        latency_ms=12,
        acknowledged=True,
        ack_status="valid",
        success=True,
        payload=SAMPLE_EVENT,
        payload_bytes=100,
        request_headers={"X-SoroScan-Signature": "sha256=abc"},
        response_headers={"X-SoroScan-Ack": "ok"},
        response_body="ok",
        error=None,
        attempt_count=1,
        attempts=[
            DeliveryAttempt(
                attempt_number=1,
                http_status=200,
                latency_ms=12,
                acknowledged=True,
                ack_status="valid",
                response_body="ok",
                response_headers={"X-SoroScan-Ack": "ok"},
            )
        ],
    )
    defaults.update(kwargs)
    return DeliveryResult(**defaults)


def test_format_text_includes_status():
    text = format_text(_sample_result())
    assert "Delivery status:  SUCCESS" in text
    assert "HTTP status:      200" in text
    assert "HMAC signature:" in text
    assert "ok" in text


def test_format_json_round_trips_status():
    data = result_to_dict(_sample_result())
    assert data["success"] is True
    rendered = format_json(_sample_result())
    assert '"http_status": 200' in rendered


def test_format_dry_run_text_and_json():
    body = canonicalize(SAMPLE_EVENT)
    headers = build_delivery_headers(body, secret="s", timestamp="t")
    text = format_dry_run("http://localhost/wh", SAMPLE_EVENT, body, headers)
    assert "Dry run" in text
    json_out = format_dry_run(
        "http://localhost/wh", SAMPLE_EVENT, body, headers, output="json"
    )
    assert '"dry_run": true' in json_out
