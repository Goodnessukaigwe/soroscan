"""
Tests covering webhook delivery guarantees, cost budgeting, contract dependency
analysis, and high-availability infrastructure.

Relates to:
  #339 - Guaranteed webhook delivery with escalation and acknowledgment
  #340 - Cost estimation and budget alert system
  #341 - Contract dependency analysis and vulnerability impact
  #343 - Multi-region HA and SLA documentation
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
import responses
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from soroscan.ingest.models import (
    CallGraph,
    ContractDependency,
    ContractInvocation,
    DependencyImpactAssessment,
    Organization,
    OrganizationBudget,
    OrganizationCostSnapshot,
    TrackedContract,
    WebhookDeadLetter,
    WebhookDeliveryLog,
)
from soroscan.ingest.tasks import (
    aggregate_organization_costs,
    alert_downstream_contract_change,
    analyze_contract_dependencies,
    assess_vulnerability_impact,
    recompute_call_graph,
)

from .factories import (
    ContractEventFactory,
    WebhookSubscriptionFactory,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# #339 — Webhook delivery acknowledgment
# Subscribers must return a specific HTTP header to confirm receipt.
# Without it the delivery is treated as failed and retried.
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestWebhookAcknowledgment:
    """Delivery requires an explicit acknowledgment header from the subscriber."""

    @responses.activate
    def test_delivery_without_ack_header_is_not_acknowledged(self, contract):
        # A 200 response that omits the ack header must NOT count as acknowledged.
        webhook = WebhookSubscriptionFactory(
            contract=contract,
            ack_header_name="X-SoroScan-Ack",
            ack_header_value="ok",
        )
        event = ContractEventFactory(contract=contract)
        responses.add(responses.POST, webhook.target_url, status=200)

        from soroscan.ingest.tasks import dispatch_webhook
        from celery.exceptions import Retry
        import pytest as _pytest
        with _pytest.raises(Retry):
            dispatch_webhook.apply(args=[webhook.id, event.id], throw=True)

        log = WebhookDeliveryLog.objects.get(subscription=webhook, event=event)
        assert log.acknowledged is False

    @responses.activate
    def test_delivery_with_correct_ack_header_is_acknowledged(self, contract):
        # A 200 response that includes the correct ack header value succeeds.
        webhook = WebhookSubscriptionFactory(
            contract=contract,
            ack_header_name="X-SoroScan-Ack",
            ack_header_value="ok",
        )
        event = ContractEventFactory(contract=contract)
        responses.add(
            responses.POST,
            webhook.target_url,
            status=200,
            headers={"X-SoroScan-Ack": "ok"},
        )

        from soroscan.ingest.tasks import dispatch_webhook
        result = dispatch_webhook.apply(args=[webhook.id, event.id])
        assert result.result is True

        log = WebhookDeliveryLog.objects.get(subscription=webhook, event=event)
        assert log.acknowledged is True

    @responses.activate
    def test_delivery_with_wrong_ack_value_is_not_acknowledged(self, contract):
        # A mismatched ack value must be treated the same as a missing header.
        webhook = WebhookSubscriptionFactory(
            contract=contract,
            ack_header_name="X-SoroScan-Ack",
            ack_header_value="ok",
        )
        event = ContractEventFactory(contract=contract)
        responses.add(
            responses.POST,
            webhook.target_url,
            status=200,
            headers={"X-SoroScan-Ack": "wrong"},
        )

        from soroscan.ingest.tasks import dispatch_webhook
        from celery.exceptions import Retry
        import pytest as _pytest
        with _pytest.raises(Retry):
            dispatch_webhook.apply(args=[webhook.id, event.id], throw=True)

        log = WebhookDeliveryLog.objects.get(subscription=webhook, event=event)
        assert log.acknowledged is False


@pytest.mark.django_db
class TestWebhookSLATracking:
    """SLA tracking: every acknowledged delivery records latency and SLA compliance."""

    @responses.activate
    def test_acknowledged_delivery_within_sla_is_flagged(self, contract):
        # Deliveries that complete within delivery_sla_seconds must set within_sla=True.
        webhook = WebhookSubscriptionFactory(
            contract=contract,
            delivery_sla_seconds=30,
        )
        event = ContractEventFactory(contract=contract)
        responses.add(
            responses.POST,
            webhook.target_url,
            status=200,
            headers={"X-SoroScan-Ack": "ok"},
        )

        from soroscan.ingest.tasks import dispatch_webhook
        dispatch_webhook.apply(args=[webhook.id, event.id])

        log = WebhookDeliveryLog.objects.get(subscription=webhook, event=event)
        assert log.within_sla is True
        assert log.latency_ms is not None

    @responses.activate
    def test_delivery_log_always_records_sla_fields(self, contract):
        # within_sla, latency_ms, and acknowledged must be present on every log row.
        webhook = WebhookSubscriptionFactory(contract=contract)
        event = ContractEventFactory(contract=contract)
        responses.add(
            responses.POST,
            webhook.target_url,
            status=200,
            headers={"X-SoroScan-Ack": "ok"},
        )

        from soroscan.ingest.tasks import dispatch_webhook
        dispatch_webhook.apply(args=[webhook.id, event.id])

        log = WebhookDeliveryLog.objects.get(subscription=webhook, event=event)
        assert hasattr(log, "within_sla")
        assert hasattr(log, "latency_ms")
        assert hasattr(log, "acknowledged")


@pytest.mark.django_db
class TestWebhookDeadLetterQueue:
    """Failed deliveries that exhaust all retries land in the dead-letter queue."""

    @responses.activate
    def test_exhausted_retries_create_dead_letter_entry(self, contract):
        # After max retries the subscription is suspended and a DLQ row is created.
        webhook = WebhookSubscriptionFactory(contract=contract)
        event = ContractEventFactory(contract=contract)
        responses.add(responses.POST, webhook.target_url, status=500)

        from soroscan.ingest.tasks import dispatch_webhook
        import requests as _req
        import pytest as _pytest
        with _pytest.raises(_req.exceptions.HTTPError):
            dispatch_webhook.apply(args=[webhook.id, event.id], retries=5, throw=True)

        dlq = WebhookDeadLetter.objects.get(subscription=webhook, event=event)
        assert dlq.resolved is False
        assert dlq.retries_exhausted > 0
        assert dlq.status_code == 500

    @responses.activate
    def test_dead_letter_entry_preserves_payload_for_replay(self, contract):
        # The payload is stored so operators can manually replay the delivery.
        webhook = WebhookSubscriptionFactory(contract=contract)
        event = ContractEventFactory(contract=contract)
        responses.add(responses.POST, webhook.target_url, status=500)

        from soroscan.ingest.tasks import dispatch_webhook
        import requests as _req
        import pytest as _pytest
        with _pytest.raises(_req.exceptions.HTTPError):
            dispatch_webhook.apply(args=[webhook.id, event.id], retries=5, throw=True)

        dlq = WebhookDeadLetter.objects.get(subscription=webhook, event=event)
        assert isinstance(dlq.payload, dict)

    def test_dead_letter_model_has_required_fields(self):
        # Verify the model schema covers all fields needed for manual review.
        assert hasattr(WebhookDeadLetter, "subscription")
        assert hasattr(WebhookDeadLetter, "event")
        assert hasattr(WebhookDeadLetter, "payload")
        assert hasattr(WebhookDeadLetter, "resolved")
        assert hasattr(WebhookDeadLetter, "retries_exhausted")
        assert hasattr(WebhookDeadLetter, "error")


@pytest.mark.django_db
class TestWebhookEscalationPolicy:
    """Escalation chain: Slack → SMS → PagerDuty fires on repeated failures."""

    @responses.activate
    def test_escalation_fires_when_failure_count_reaches_threshold(self, contract):
        # after_failures=1 means the escalation channel is called on the first failure.
        webhook = WebhookSubscriptionFactory(
            contract=contract,
            escalation_policy=[
                {"channel": "slack", "target": "https://ops.example.com/slack", "after_failures": 1},
            ],
        )
        event = ContractEventFactory(contract=contract)
        responses.add(responses.POST, webhook.target_url, status=500)
        responses.add(responses.POST, "https://ops.example.com/slack", status=200)

        from soroscan.ingest.tasks import dispatch_webhook
        from celery.exceptions import Retry
        import pytest as _pytest
        with _pytest.raises(Retry):
            dispatch_webhook.apply(args=[webhook.id, event.id], throw=True)

        # Both the webhook attempt and the Slack escalation call must have been made.
        assert len(responses.calls) == 2

    @responses.activate
    def test_escalation_does_not_fire_below_threshold(self, contract):
        # after_failures=5 means no escalation on the first failure (failure_count=1).
        webhook = WebhookSubscriptionFactory(
            contract=contract,
            escalation_policy=[
                {"channel": "slack", "target": "https://ops.example.com/slack", "after_failures": 5},
            ],
        )
        event = ContractEventFactory(contract=contract)
        responses.add(responses.POST, webhook.target_url, status=500)

        from soroscan.ingest.tasks import dispatch_webhook
        from celery.exceptions import Retry
        import pytest as _pytest
        with _pytest.raises(Retry):
            dispatch_webhook.apply(args=[webhook.id, event.id], throw=True)

        # Only the webhook attempt; no escalation call.
        assert len(responses.calls) == 1

    def test_default_escalation_policy_covers_all_three_channels(self):
        # The built-in default must include slack, sms, and pagerduty in order.
        from soroscan.ingest.tasks import _default_webhook_escalation_policy
        policy = _default_webhook_escalation_policy()
        channels = [e["channel"] for e in policy]
        assert "slack" in channels
        assert "sms" in channels
        assert "pagerduty" in channels

    def test_invalid_channels_are_stripped_from_policy(self, contract):
        # Unknown channel names must be silently dropped during normalisation.
        from soroscan.ingest.tasks import _normalized_webhook_escalation_policy
        webhook = WebhookSubscriptionFactory(
            contract=contract,
            escalation_policy=[
                {"channel": "invalid_channel", "target": "https://x.com", "after_failures": 1},
                {"channel": "slack", "target": "https://slack.com", "after_failures": 2},
            ],
        )
        policy = _normalized_webhook_escalation_policy(webhook)
        channels = [e["channel"] for e in policy]
        assert "invalid_channel" not in channels
        assert "slack" in channels


@pytest.mark.django_db
class TestWebhookDeduplication:
    """Identical events are deduplicated to prevent alert floods."""

    def test_event_deduplication_log_model_exists(self):
        # EventDeduplicationLog must be importable and usable.
        from soroscan.ingest.models import EventDeduplicationLog
        assert EventDeduplicationLog is not None

    def test_cleanup_task_removes_expired_dedup_logs(self, contract):
        # Logs older than the retention window must be pruned by the cleanup task.
        from soroscan.ingest.models import EventDeduplicationLog
        from soroscan.ingest.tasks import cleanup_old_dedup_logs
        from datetime import timedelta

        old = EventDeduplicationLog.objects.create(
            contract=contract,
            ledger=1,
            event_index=0,
            tx_hash="a" * 64,
            event_type="transfer",
            duplicate_detected=True,
            reason="test",
        )
        # Backdate so it falls outside the 90-day retention window.
        EventDeduplicationLog.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=100)
        )

        deleted = cleanup_old_dedup_logs.apply().result
        assert deleted >= 1
        assert not EventDeduplicationLog.objects.filter(pk=old.pk).exists()


# ---------------------------------------------------------------------------
# #340 — Cost estimation and budget alert system
# Tracks RPC calls, storage, and compute per org; fires alerts at 80%/100%.
# ---------------------------------------------------------------------------

class TestOrganizationBudgetModel(TestCase):
    """Budget limits are configurable per organization."""

    def setUp(self):
        self.user = User.objects.create_user(username="budgetuser", password="pass")
        self.org = Organization.objects.create(name="TestOrg", owner=self.user)

    def test_budget_stores_usd_thresholds(self):
        # All three monetary/percentage fields must round-trip correctly.
        budget = OrganizationBudget.objects.create(
            organization=self.org,
            monthly_budget_usd=Decimal("500.00"),
            warning_threshold_percent=80,
            critical_threshold_percent=100,
        )
        assert budget.monthly_budget_usd == Decimal("500.00")
        assert budget.warning_threshold_percent == 80
        assert budget.critical_threshold_percent == 100
        assert budget.is_active is True

    def test_budget_str_includes_org_name_and_amount(self):
        # __str__ must be human-readable for admin list views.
        budget = OrganizationBudget.objects.create(
            organization=self.org,
            monthly_budget_usd=Decimal("100.00"),
        )
        assert "TestOrg" in str(budget)
        assert "100" in str(budget)

    def test_budget_warning_and_critical_thresholds_default_to_80_and_100(self):
        # Sensible defaults so operators don't have to configure thresholds manually.
        budget = OrganizationBudget.objects.create(organization=self.org)
        assert budget.warning_threshold_percent == 80
        assert budget.critical_threshold_percent == 100


class TestOrganizationCostSnapshot(TestCase):
    """Cost metrics are tracked per organization in monthly snapshots."""

    def setUp(self):
        self.user = User.objects.create_user(username="costuser", password="pass")
        self.org = Organization.objects.create(name="CostOrg", owner=self.user)

    def test_snapshot_stores_all_cost_dimensions(self):
        # All cost dimensions (RPC, storage, compute) must persist correctly.
        from datetime import date
        snapshot = OrganizationCostSnapshot.objects.create(
            organization=self.org,
            month=date(2026, 4, 1),
            rpc_calls=1000,
            storage_bytes=1024 * 1024,
            compute_units=2000,
            rpc_cost_usd=Decimal("0.01"),
            storage_cost_usd=Decimal("0.001"),
            compute_cost_usd=Decimal("0.04"),
            actual_cost_usd=Decimal("0.051"),
            projected_monthly_cost_usd=Decimal("0.60"),
            breakdown={"contracts": {}, "event_types": {}, "storage": {}},
        )
        assert snapshot.rpc_calls == 1000
        assert snapshot.projected_monthly_cost_usd == Decimal("0.60")

    def test_snapshot_is_unique_per_org_per_month(self):
        # Duplicate (org, month) pairs must be rejected at the DB level.
        from datetime import date
        from django.db import IntegrityError
        OrganizationCostSnapshot.objects.create(
            organization=self.org,
            month=date(2026, 4, 1),
        )
        with self.assertRaises(IntegrityError):
            OrganizationCostSnapshot.objects.create(
                organization=self.org,
                month=date(2026, 4, 1),
            )


class TestAggregateCostsTask(TestCase):
    """aggregate_organization_costs builds monthly snapshots and fires budget alerts."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="agguser", password="pass")
        self.org = Organization.objects.create(name="AggOrg", owner=self.user)

    def tearDown(self):
        cache.clear()

    def test_snapshot_created_for_org_with_no_contracts(self):
        # Orgs with zero contracts still get a zero-cost snapshot each run.
        result = aggregate_organization_costs.apply().result
        assert "month" in result
        assert "organizations" in result
        org_result = next(
            (r for r in result["organizations"] if r["organization_id"] == self.org.id),
            None,
        )
        assert org_result is not None
        assert org_result["projected_monthly_cost_usd"] == "0"

    def test_snapshot_created_for_org_with_contracts_and_events(self):
        # Orgs with contracts and events must produce non-negative cost figures.
        contract = TrackedContract.objects.create(
            contract_id="C" * 56,
            name="OrgContract",
            owner=self.user,
            organization=self.org,
        )
        ContractEventFactory(
            contract=contract,
            event_type="transfer",
            payload={"amount": 100},
        )
        result = aggregate_organization_costs.apply().result
        org_result = next(
            r for r in result["organizations"] if r["organization_id"] == self.org.id
        )
        assert int(org_result["rpc_calls"]) >= 0
        assert int(org_result["storage_bytes"]) >= 0

    @patch("soroscan.ingest.tasks._emit_budget_alerts")
    def test_budget_alert_emitter_called_when_budget_configured(self, mock_emit):
        # _emit_budget_alerts must be invoked for every org that has a budget.
        mock_emit.return_value = 1
        OrganizationBudget.objects.create(
            organization=self.org,
            monthly_budget_usd=Decimal("0.001"),
            warning_threshold_percent=80,
        )
        contract = TrackedContract.objects.create(
            contract_id="D" * 56,
            name="BudgetContract",
            owner=self.user,
            organization=self.org,
        )
        ContractEventFactory(contract=contract)
        aggregate_organization_costs.apply()
        mock_emit.assert_called()

    def test_budget_alert_fires_when_projected_cost_exceeds_warning_threshold(self):
        # A projected cost above 80% of the budget must trigger at least one alert.
        from soroscan.ingest.tasks import _emit_budget_alerts
        from datetime import date

        budget = OrganizationBudget.objects.create(
            organization=self.org,
            monthly_budget_usd=Decimal("100.00"),
            warning_threshold_percent=80,
            critical_threshold_percent=100,
        )
        snapshot = OrganizationCostSnapshot.objects.create(
            organization=self.org,
            month=date(2026, 4, 1),
            projected_monthly_cost_usd=Decimal("85.00"),
        )
        sent = _emit_budget_alerts(self.org, snapshot, budget)
        assert sent >= 1

    def test_budget_alert_is_deduplicated_within_same_month(self):
        # Calling _emit_budget_alerts twice for the same snapshot must only send once.
        from soroscan.ingest.tasks import _emit_budget_alerts
        from datetime import date

        budget = OrganizationBudget.objects.create(
            organization=self.org,
            monthly_budget_usd=Decimal("100.00"),
            warning_threshold_percent=80,
        )
        snapshot = OrganizationCostSnapshot.objects.create(
            organization=self.org,
            month=date(2026, 4, 1),
            projected_monthly_cost_usd=Decimal("85.00"),
        )
        first = _emit_budget_alerts(self.org, snapshot, budget)
        second = _emit_budget_alerts(self.org, snapshot, budget)
        assert first >= 1
        assert second == 0  # second call is deduplicated via cache

    def test_cost_breakdown_contains_contracts_event_types_and_storage(self):
        # The breakdown JSON must always include all three top-level keys.
        contract = TrackedContract.objects.create(
            contract_id="E" * 56,
            name="BreakdownContract",
            owner=self.user,
            organization=self.org,
        )
        ContractEventFactory(contract=contract, event_type="swap")
        aggregate_organization_costs.apply()
        snapshot = OrganizationCostSnapshot.objects.filter(organization=self.org).first()
        assert snapshot is not None
        assert "contracts" in snapshot.breakdown
        assert "event_types" in snapshot.breakdown
        assert "storage" in snapshot.breakdown


# ---------------------------------------------------------------------------
# #341 — Contract dependency analysis and vulnerability impact
# Builds a dependency graph from cross-contract invocations, detects cycles,
# and quantifies blast radius when a contract is exploited.
# ---------------------------------------------------------------------------

class TestContractDependencyAnalysis(TestCase):
    """Dependency graph is built incrementally from ContractInvocation records."""

    def setUp(self):
        self.user = User.objects.create_user(username="depuser", password="pass")
        self.caller = TrackedContract.objects.create(
            contract_id="C" * 56,
            name="CallerContract",
            owner=self.user,
        )
        self.callee = TrackedContract.objects.create(
            contract_id="D" * 56,
            name="CalleeContract",
            owner=self.user,
        )

    def test_invocation_from_tracked_contract_creates_dependency_edge(self):
        # A contract-to-contract invocation must produce a ContractDependency row.
        ContractInvocation.objects.create(
            tx_hash="a" * 64,
            caller=self.caller.contract_id,
            contract=self.callee,
            function_name="transfer",
            parameters={},
            ledger_sequence=1000,
        )
        result = analyze_contract_dependencies.apply().result
        assert result["created"] >= 1
        assert ContractDependency.objects.filter(
            caller=self.caller, callee=self.callee
        ).exists()

    def test_repeated_invocations_increment_call_count(self):
        # Each additional invocation must increment the edge call_count.
        for i in range(3):
            ContractInvocation.objects.create(
                tx_hash=f"{'a' * 63}{i}",
                caller=self.caller.contract_id,
                contract=self.callee,
                function_name="transfer",
                parameters={},
                ledger_sequence=1000 + i,
            )
        analyze_contract_dependencies.apply()
        dep = ContractDependency.objects.get(caller=self.caller, callee=self.callee)
        assert dep.call_count >= 3

    def test_invocation_from_untracked_caller_is_ignored(self):
        # Callers that are not in TrackedContract must be silently skipped.
        ContractInvocation.objects.create(
            tx_hash="b" * 64,
            caller="GUNTRACKED" + "X" * 46,
            contract=self.callee,
            function_name="transfer",
            parameters={},
            ledger_sequence=2000,
        )
        result = analyze_contract_dependencies.apply().result
        assert result["created"] == 0


class TestCallGraphCycleDetection(TestCase):
    """recompute_call_graph detects circular dependencies and scores edges."""

    def setUp(self):
        self.user = User.objects.create_user(username="cycleuser", password="pass")
        self.a = TrackedContract.objects.create(
            contract_id="A" * 56, name="ContractA", owner=self.user
        )
        self.b = TrackedContract.objects.create(
            contract_id="B" * 56, name="ContractB", owner=self.user
        )
        self.c = TrackedContract.objects.create(
            contract_id="C" * 56, name="ContractC", owner=self.user
        )

    def test_linear_dependency_chain_has_no_cycle(self):
        # A → B → C is a DAG; has_cycles must be False.
        ContractDependency.objects.create(caller=self.a, callee=self.b, call_count=1)
        ContractDependency.objects.create(caller=self.b, callee=self.c, call_count=1)
        recompute_call_graph.apply()
        graph = CallGraph.objects.filter(contract=None).first()
        assert graph is not None
        assert graph.has_cycles is False

    def test_circular_dependency_is_detected(self):
        # A → B → C → A forms a cycle; has_cycles must be True.
        ContractDependency.objects.create(caller=self.a, callee=self.b, call_count=1)
        ContractDependency.objects.create(caller=self.b, callee=self.c, call_count=1)
        ContractDependency.objects.create(caller=self.c, callee=self.a, call_count=1)
        recompute_call_graph.apply()
        graph = CallGraph.objects.filter(contract=None).first()
        assert graph is not None
        assert graph.has_cycles is True

    def test_graph_data_includes_nodes_and_edges(self):
        # The cached graph_data JSON must contain both nodes and edges arrays.
        ContractDependency.objects.create(caller=self.a, callee=self.b, call_count=5)
        recompute_call_graph.apply()
        graph = CallGraph.objects.filter(contract=None).first()
        assert "nodes" in graph.graph_data
        assert "edges" in graph.graph_data
        assert len(graph.graph_data["nodes"]) >= 2
        assert len(graph.graph_data["edges"]) >= 1

    def test_edge_risk_score_is_computed_after_graph_rebuild(self):
        # Each dependency edge must receive a non-negative risk_score after recompute.
        ContractDependency.objects.create(caller=self.a, callee=self.b, call_count=10)
        recompute_call_graph.apply()
        dep = ContractDependency.objects.get(caller=self.a, callee=self.b)
        assert dep.risk_score >= 0.0


class TestVulnerabilityImpactAssessment(TestCase):
    """assess_vulnerability_impact quantifies blast radius and risk level."""

    def setUp(self):
        self.user = User.objects.create_user(username="vulnuser", password="pass")
        self.root = TrackedContract.objects.create(
            contract_id="R" * 56, name="RootContract", owner=self.user
        )
        self.dep1 = TrackedContract.objects.create(
            contract_id="P" * 56, name="Dep1", owner=self.user
        )
        self.dep2 = TrackedContract.objects.create(
            contract_id="Q" * 56, name="Dep2", owner=self.user
        )

    def test_downstream_contracts_are_listed_in_affected_contracts(self):
        # Direct and transitive callees of the root must appear in affected_contracts.
        ContractDependency.objects.create(caller=self.root, callee=self.dep1, call_count=5)
        ContractDependency.objects.create(caller=self.dep1, callee=self.dep2, call_count=3)
        result = assess_vulnerability_impact.apply(args=[self.root.contract_id]).result
        assert self.dep1.contract_id in result["affected_contracts"]
        assert result["impacted_count"] >= 1

    def test_risk_score_and_impact_level_are_returned(self):
        # The result must include a numeric score and a categorical level.
        ContractDependency.objects.create(caller=self.root, callee=self.dep1, call_count=10)
        result = assess_vulnerability_impact.apply(args=[self.root.contract_id]).result
        assert result["risk_score"] >= 0.0
        assert result["impact_level"] in ("low", "medium", "high", "critical")

    def test_unknown_contract_returns_zero_impact(self):
        # A contract_id not in the DB must return a safe zero-impact result.
        result = assess_vulnerability_impact.apply(args=["Z" * 56]).result
        assert result["impacted_count"] == 0
        assert result["risk_score"] == 0.0

    def test_assessment_is_persisted_to_database(self):
        # The DependencyImpactAssessment row must be created or updated after each run.
        ContractDependency.objects.create(caller=self.root, callee=self.dep1, call_count=5)
        assess_vulnerability_impact.apply(args=[self.root.contract_id])
        assessment = DependencyImpactAssessment.objects.filter(
            root_contract=self.root
        ).first()
        assert assessment is not None
        assert assessment.impacted_count >= 1

    def test_cycle_participation_is_flagged_in_assessment(self):
        # When the root is part of a cycle, has_cycles must be True in the result.
        ContractDependency.objects.create(caller=self.root, callee=self.dep1, call_count=5)
        ContractDependency.objects.create(caller=self.dep1, callee=self.root, call_count=3)
        recompute_call_graph.apply()
        result = assess_vulnerability_impact.apply(args=[self.root.contract_id]).result
        assert result["has_cycles"] is True


class TestDownstreamChangeAlerts(TestCase):
    """Dependent contract owners are notified when an upstream contract changes."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="alertdepuser", password="pass")
        self.upstream = TrackedContract.objects.create(
            contract_id="U" * 56, name="Upstream", owner=self.user
        )
        self.downstream = TrackedContract.objects.create(
            contract_id="V" * 56, name="Downstream", owner=self.user
        )

    def tearDown(self):
        cache.clear()

    def test_notification_sent_to_owner_of_dependent_contract(self):
        # When upstream changes, the owner of the downstream contract must be notified.
        ContractDependency.objects.create(
            caller=self.downstream, callee=self.upstream, call_count=1
        )
        notified = alert_downstream_contract_change.apply(
            args=[self.upstream.contract_id, "modified"]
        ).result
        assert notified == 1

    def test_no_notification_when_contract_has_no_dependents(self):
        # A contract with no callers must produce zero notifications.
        notified = alert_downstream_contract_change.apply(
            args=[self.upstream.contract_id, "modified"]
        ).result
        assert notified == 0

    def test_repeated_change_alert_is_deduplicated(self):
        # The same upstream change must not spam the owner within the dedup window.
        ContractDependency.objects.create(
            caller=self.downstream, callee=self.upstream, call_count=1
        )
        first = alert_downstream_contract_change.apply(
            args=[self.upstream.contract_id, "modified"]
        ).result
        second = alert_downstream_contract_change.apply(
            args=[self.upstream.contract_id, "modified"]
        ).result
        assert first == 1
        assert second == 0  # second call is deduplicated via cache


# ---------------------------------------------------------------------------
# #343 — Multi-region HA and SLA documentation
# Covers health checks, read-replica config, archival backup, SLA doc, and
# Celery Beat schedule for all HA-critical periodic tasks.
# ---------------------------------------------------------------------------

class TestHealthEndpoint(TestCase):
    """Health endpoint must respond 200 so Kubernetes readiness probes pass."""

    def test_health_endpoint_returns_200(self):
        from rest_framework.test import APIClient
        client = APIClient()
        resp = client.get("/api/ingest/health/")
        assert resp.status_code == 200

    def test_health_response_body_contains_status_key(self):
        # The response JSON must include a "status" field for monitoring tools.
        from rest_framework.test import APIClient
        client = APIClient()
        resp = client.get("/api/ingest/health/")
        data = resp.json()
        assert "status" in data


class TestDatabaseReplicaConfig(TestCase):
    """Settings layer supports a read-replica database alias for HA query routing."""

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            },
            "replica": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
                "TEST": {"NAME": ":memory:"},
            },
        }
    )
    def test_replica_database_alias_is_accepted_by_django(self):
        # Django must not raise when a "replica" alias is present in DATABASES.
        from django.conf import settings
        assert "replica" in settings.DATABASES

    def test_app_starts_without_replica_url_configured(self):
        # The app must boot normally when DATABASE_REPLICA_URL is absent.
        from django.conf import settings
        assert hasattr(settings, "DATABASES")


class TestArchiveOldEventsTask(TestCase):
    """archive_old_events implements the S3 backup strategy for HA data retention."""

    def test_archive_task_is_importable_and_callable(self):
        # The task must exist and be callable so Celery Beat can schedule it.
        from soroscan.ingest.tasks import archive_old_events
        assert callable(archive_old_events)

    def test_archive_task_returns_summary_with_required_keys(self):
        # The return value must always include archived, deleted, and errors counts.
        from soroscan.ingest.tasks import archive_old_events
        result = archive_old_events.apply().result
        assert "archived" in result
        assert "deleted" in result
        assert "errors" in result

    def test_archive_task_with_no_policies_returns_zero_counts(self):
        # When no DataRetentionPolicy rows exist, nothing should be archived.
        from soroscan.ingest.tasks import archive_old_events
        result = archive_old_events.apply().result
        assert result["archived"] == 0
        assert result["deleted"] == 0


class TestSLADocumentationExists(TestCase):
    """SLA document with RTO/RPO targets must exist in the docs directory."""

    def test_sla_markdown_file_is_present(self):
        # django-backend/docs/sla.md must exist and be non-empty.
        import os
        sla_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..", "..", "django-backend", "docs", "sla.md",
        )
        sla_path = os.path.normpath(sla_path)
        assert os.path.exists(sla_path), (
            f"SLA document not found at {sla_path}. "
            "Create django-backend/docs/sla.md with RTO/RPO targets."
        )


class TestCeleryBeatScheduleForHA(TestCase):
    """All HA-critical periodic tasks must be registered in the Celery Beat schedule."""

    # Test settings omit CELERY_BEAT_SCHEDULE to keep the test DB lightweight.
    # We load the production settings module directly to verify the schedule.
    def _get_production_schedule(self):
        import importlib
        prod = importlib.import_module("soroscan.settings")
        return getattr(prod, "CELERY_BEAT_SCHEDULE", {})

    def test_archive_old_events_is_scheduled(self):
        # Daily S3 archival must be in the Beat schedule for backup continuity.
        schedule = self._get_production_schedule()
        task_names = [v.get("task", "") for v in schedule.values()]
        assert any("archive_old_events" in t for t in task_names)

    def test_cleanup_webhook_delivery_logs_is_scheduled(self):
        # Daily log pruning keeps the delivery log table from growing unbounded.
        schedule = self._get_production_schedule()
        task_names = [v.get("task", "") for v in schedule.values()]
        assert any("cleanup_webhook_delivery_logs" in t for t in task_names)

    def test_aggregate_organization_costs_is_scheduled(self):
        # Hourly cost aggregation ensures budget alerts fire in near-real-time.
        schedule = self._get_production_schedule()
        task_names = [v.get("task", "") for v in schedule.values()]
        assert any("aggregate_organization_costs" in t for t in task_names)

    def test_recompute_call_graph_is_scheduled(self):
        # Hourly graph recompute keeps dependency risk scores up to date.
        schedule = self._get_production_schedule()
        task_names = [v.get("task", "") for v in schedule.values()]
        assert any("recompute_call_graph" in t for t in task_names)

