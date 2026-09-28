"""Tests validating the Prometheus error-rate alerting rules (issue #1294)."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
RULES_PATH = REPO_ROOT / "k8s" / "prometheus-rules.yaml"


def _load_rules():
    assert RULES_PATH.exists(), f"prometheus rules not found at {RULES_PATH}"
    with open(RULES_PATH) as handle:
        return yaml.safe_load(handle)


def _collect_alerts(rules):
    alerts = {}
    for group in rules["spec"]["groups"]:
        for rule in group["rules"]:
            if "alert" in rule:
                alerts[rule["alert"]] = rule
    return alerts


def test_rules_file_is_valid_prometheusrule():
    rules = _load_rules()
    assert rules["kind"] == "PrometheusRule"
    assert rules["spec"]["groups"]


def test_error_rate_alerts_present_with_sla_thresholds():
    alerts = _collect_alerts(_load_rules())
    assert "SoroScanApiErrorRateHigh" in alerts
    assert "SoroScanApiErrorRateCritical" in alerts

    high = alerts["SoroScanApiErrorRateHigh"]
    critical = alerts["SoroScanApiErrorRateCritical"]

    # SLA-based thresholds: warn > 1%, critical > 5%.
    assert "> 1" in high["expr"]
    assert "> 5" in critical["expr"]

    # Both must carry a severity and a root-cause oriented query.
    assert high["labels"]["severity"] == "warning"
    assert critical["labels"]["severity"] == "critical"
    assert "root_cause_query" in high["annotations"]
    assert "root_cause_query" in critical["annotations"]


def test_error_rate_alerts_group_by_service():
    alerts = _collect_alerts(_load_rules())
    expr = alerts["SoroScanApiErrorRateHigh"]["expr"]
    # Per-service grouping so the alert fires with a service dimension.
    assert "sum by (service)" in expr
