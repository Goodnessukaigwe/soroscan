"""Tests for the local event replay utility (issue #1325)."""

import json
from datetime import datetime, timezone as dt_timezone
from io import StringIO
from types import SimpleNamespace

import pytest
import responses
from django.core.management import call_command
from django.core.management.base import CommandError

from soroscan.ingest.models import WebhookDeliveryLog, WebhookSubscription
from soroscan.ingest.services.event_replay import (
    ENV_LOCAL,
    ENV_REMOTE,
    ReplayDelivery,
    ReplayError,
    describe_database_target,
    event_to_replay_payload,
    fetch_events_for_replay,
    matching_webhooks,
    original_timestamp_iso,
    parse_iso_datetime,
    replay_events,
)
from soroscan.ingest.tasks import dispatch_webhook
from soroscan.ingest.tests.factories import (
    ContractEventFactory,
    TrackedContractFactory,
    WebhookSubscriptionFactory,
)


def _aware(year, month, day, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=dt_timezone.utc)


@pytest.fixture
def contract():
    return TrackedContractFactory()


@pytest.fixture
def webhook(contract):
    return WebhookSubscriptionFactory(
        contract=contract,
        event_type="swap",
        target_url="https://example.com/webhook",
        is_active=True,
        status=WebhookSubscription.STATUS_ACTIVE,
    )


@pytest.fixture
def events(contract):
    older = ContractEventFactory(
        contract=contract,
        event_type="swap",
        ledger=100,
        event_index=0,
        timestamp=_aware(2026, 1, 1, 10, 0, 0),
        payload={"amount": 10},
    )
    newer = ContractEventFactory(
        contract=contract,
        event_type="swap",
        ledger=200,
        event_index=1,
        timestamp=_aware(2026, 1, 1, 10, 5, 0),
        payload={"amount": 20},
    )
    other_type = ContractEventFactory(
        contract=contract,
        event_type="transfer",
        ledger=150,
        event_index=0,
        timestamp=_aware(2026, 1, 1, 10, 2, 0),
        payload={"amount": 5},
    )
    return older, newer, other_type


@pytest.mark.django_db
class TestFetchEventsForReplay:
    def test_orders_by_original_timestamp(self, contract, events):
        older, newer, other_type = events
        fetched = list(fetch_events_for_replay(contract.contract_id, limit=0))
        assert [e.id for e in fetched] == [older.id, other_type.id, newer.id]
        assert [original_timestamp_iso(e) for e in fetched] == [
            older.timestamp.isoformat(),
            other_type.timestamp.isoformat(),
            newer.timestamp.isoformat(),
        ]

    def test_filters_by_event_type_and_ledger(self, contract, events):
        older, newer, _ = events
        fetched = list(
            fetch_events_for_replay(
                contract.contract_id,
                event_type="swap",
                from_ledger=150,
                to_ledger=250,
                limit=0,
            )
        )
        assert [e.id for e in fetched] == [newer.id]
        assert older.id not in {e.id for e in fetched}

    def test_filters_by_original_date_range(self, contract, events):
        older, _, other_type = events
        fetched = list(
            fetch_events_for_replay(
                contract.contract_id,
                from_date="2026-01-01T10:00:00+00:00",
                to_date="2026-01-01T10:03:00+00:00",
                limit=0,
            )
        )
        assert [e.id for e in fetched] == [older.id, other_type.id]

    def test_unknown_contract_raises(self):
        with pytest.raises(ReplayError, match="No TrackedContract"):
            fetch_events_for_replay("C" + "A" * 55)

    def test_invalid_from_date_raises(self, contract):
        with pytest.raises(ReplayError, match="Invalid --from-date"):
            list(fetch_events_for_replay(contract.contract_id, from_date="not-a-date"))

    def test_payload_includes_original_timestamp(self, events):
        older, _, _ = events
        payload = event_to_replay_payload(older)
        assert payload["timestamp"] == older.timestamp.isoformat()
        assert payload["ledger"] == older.ledger
        assert payload["contract_id"] == older.contract.contract_id


@pytest.mark.django_db
class TestMatchingWebhooks:
    def test_skips_event_type_mismatch(self, contract, webhook, events):
        _, _, transfer = events
        assert matching_webhooks(contract.contract_id, transfer) == []

    def test_matches_blank_event_type(self, contract, events):
        older, _, _ = events
        catch_all = WebhookSubscriptionFactory(
            contract=contract,
            event_type="",
            target_url="https://example.com/all",
        )
        matches = matching_webhooks(contract.contract_id, older)
        assert catch_all in matches

    def test_applies_filter_condition(self, contract, events):
        older, newer, _ = events
        webhook = WebhookSubscriptionFactory(
            contract=contract,
            event_type="swap",
            target_url="https://example.com/filtered",
            filter_condition={"op": "gt", "field": "payload.amount", "value": 15},
        )
        assert matching_webhooks(contract.contract_id, older) == []
        assert matching_webhooks(contract.contract_id, newer) == [webhook]


@pytest.mark.django_db
class TestReplayEventsService:
    def test_dry_run_does_not_dispatch(self, contract, webhook, events, mocker):
        apply_mock = mocker.patch("soroscan.ingest.tasks.dispatch_webhook.apply")
        delay_mock = mocker.patch("soroscan.ingest.tasks.dispatch_webhook.delay")

        report = replay_events(
            contract.contract_id,
            dry_run=True,
            event_type="swap",
            limit=0,
        )

        apply_mock.assert_not_called()
        delay_mock.assert_not_called()
        assert report.mode == "dry-run"
        assert report.environment == ENV_LOCAL
        assert report.summary["webhook_dispatches"] == 2
        timestamps = [d.original_timestamp for d in report.deliveries]
        older, newer, _ = events
        assert timestamps == [older.timestamp.isoformat(), newer.timestamp.isoformat()]

    def test_local_environment_uses_apply_with_replay_flag(self, contract, webhook, events, mocker):
        result = SimpleNamespace(successful=lambda: True, result=True)
        apply_mock = mocker.patch(
            "soroscan.ingest.tasks.dispatch_webhook.apply",
            return_value=result,
        )
        delay_mock = mocker.patch("soroscan.ingest.tasks.dispatch_webhook.delay")

        report = replay_events(
            contract.contract_id,
            environment=ENV_LOCAL,
            event_type="swap",
            limit=0,
        )

        delay_mock.assert_not_called()
        assert apply_mock.call_count == 2
        for call in apply_mock.call_args_list:
            args = call.kwargs.get("args") or call.args[0]
            assert args[0] == webhook.id
            assert args[2] is True
        assert report.summary["successes"] == 2
        assert report.summary["failures"] == 0
        older, newer, _ = events
        assert [d.original_timestamp for d in report.deliveries] == [
            older.timestamp.isoformat(),
            newer.timestamp.isoformat(),
        ]

    def test_remote_environment_enqueues_tasks(self, contract, webhook, events, mocker):
        delay_mock = mocker.patch(
            "soroscan.ingest.tasks.dispatch_webhook.delay",
            return_value=SimpleNamespace(id="task-123"),
        )
        apply_mock = mocker.patch("soroscan.ingest.tasks.dispatch_webhook.apply")

        report = replay_events(
            contract.contract_id,
            environment=ENV_REMOTE,
            event_type="swap",
            limit=1,
        )

        apply_mock.assert_not_called()
        delay_mock.assert_called_once()
        args, _kwargs = delay_mock.call_args
        assert args[2] is True
        assert report.summary["queued"] == 1
        assert report.deliveries[0].status == "queued"
        assert report.deliveries[0].task_id == "task-123"

    def test_processing_target_reuses_process_new_event(self, contract, events, mocker):
        older, _, _ = events
        apply_mock = mocker.patch(
            "soroscan.ingest.tasks.process_new_event.apply",
            return_value=SimpleNamespace(successful=lambda: True, result=None),
        )

        report = replay_events(
            contract.contract_id,
            target="processing",
            event_id=older.id,
            limit=0,
        )

        apply_mock.assert_called_once()
        event_data = apply_mock.call_args.kwargs["args"][0]
        assert event_data["timestamp"] == older.timestamp.isoformat()
        assert event_data["ledger"] == older.ledger
        assert report.summary["successes"] == 1

    def test_processing_remote_enqueues(self, contract, events, mocker):
        delay_mock = mocker.patch(
            "soroscan.ingest.tasks.process_new_event.delay",
            return_value=SimpleNamespace(id="proc-1"),
        )
        report = replay_events(
            contract.contract_id,
            environment=ENV_REMOTE,
            target="processing",
            limit=1,
        )
        delay_mock.assert_called_once()
        assert report.deliveries[0].queued is True
        assert delay_mock.call_args.args[0]["timestamp"] is not None

    def test_tracks_failed_delivery_status(self, contract, webhook, events, mocker):
        apply_mock = mocker.patch(
            "soroscan.ingest.tasks.dispatch_webhook.apply",
            return_value=SimpleNamespace(successful=lambda: False, result="boom"),
        )
        report = replay_events(contract.contract_id, event_type="swap", limit=1)
        apply_mock.assert_called_once()
        assert report.summary["failures"] == 1
        assert report.deliveries[0].success is False
        assert "boom" in report.deliveries[0].error

    def test_webhook_id_filters_to_one_subscription(self, contract, webhook, events, mocker):
        WebhookSubscriptionFactory(
            contract=contract,
            event_type="swap",
            target_url="https://example.com/other",
        )
        mocker.patch(
            "soroscan.ingest.tasks.dispatch_webhook.apply",
            return_value=SimpleNamespace(successful=lambda: True, result=True),
        )
        report = replay_events(
            contract.contract_id,
            webhook_id=webhook.id,
            event_type="swap",
            limit=1,
        )
        assert report.summary["webhook_dispatches"] == 1
        assert report.deliveries[0].webhook_id == webhook.id
        other = WebhookSubscriptionFactory(event_type="swap")
        with pytest.raises(ReplayError, match="does not belong"):
            replay_events(contract.contract_id, webhook_id=other.id)

    def test_rejects_unknown_environment(self, contract):
        with pytest.raises(ReplayError, match="environment must be"):
            replay_events(contract.contract_id, environment="staging")

    def test_rejects_unknown_target(self, contract):
        with pytest.raises(ReplayError, match="target must be"):
            replay_events(contract.contract_id, target="alerts")

    def test_rejects_negative_max_delay(self, contract):
        with pytest.raises(ReplayError, match="--max-delay"):
            replay_events(contract.contract_id, max_delay_seconds=-1)

    def test_unknown_webhook_id_raises(self, contract):
        with pytest.raises(ReplayError, match="No WebhookSubscription"):
            replay_events(contract.contract_id, webhook_id=99999)

    def test_processing_dry_run_preserves_original_timestamp(self, contract, events):
        older, _, _ = events
        report = replay_events(
            contract.contract_id,
            target="processing",
            event_id=older.id,
            dry_run=True,
        )
        assert report.mode == "dry-run"
        assert report.deliveries[0].original_timestamp == older.timestamp.isoformat()
        assert report.deliveries[0].status == "dry-run"

    def test_skips_when_no_matching_webhooks(self, contract, events):
        report = replay_events(contract.contract_id, event_type="swap", limit=1)
        assert report.summary["skipped"] >= 1
        assert report.summary["webhook_dispatches"] == 0

    def test_local_dispatch_exception_is_reported(self, contract, webhook, events, mocker):
        mocker.patch(
            "soroscan.ingest.tasks.dispatch_webhook.apply",
            side_effect=RuntimeError("worker down"),
        )
        report = replay_events(contract.contract_id, event_type="swap", limit=1)
        assert report.summary["failures"] == 1
        assert report.deliveries[0].status == "error"
        assert "worker down" in report.deliveries[0].error

    def test_processing_failure_and_exception(self, contract, events, mocker):
        older, _, _ = events
        mocker.patch(
            "soroscan.ingest.tasks.process_new_event.apply",
            return_value=SimpleNamespace(successful=lambda: False, result="decode failed"),
        )
        report = replay_events(
            contract.contract_id, target="processing", event_id=older.id
        )
        assert report.deliveries[0].status == "failed"
        assert "decode failed" in report.deliveries[0].error

        mocker.patch(
            "soroscan.ingest.tasks.process_new_event.apply",
            side_effect=RuntimeError("broker"),
        )
        report = replay_events(
            contract.contract_id, target="processing", event_id=older.id
        )
        assert report.deliveries[0].status == "error"
        assert "broker" in report.deliveries[0].error

    def test_parse_naive_date_and_none_timestamp(self, contract, events):
        parsed = parse_iso_datetime("2026-01-01T10:00:00", "--from-date")
        assert parsed.tzinfo is not None
        older, _, _ = events
        older.timestamp = None
        assert original_timestamp_iso(older) is None
        older.timestamp = datetime(2026, 1, 1, 12, 0, 0)
        iso = original_timestamp_iso(older)
        assert iso is not None
        assert "+00:00" in iso or iso.endswith("Z") or "2026-01-01" in iso

    def test_delivery_to_dict_and_no_realtime_sleep_for_equal_timestamps(
        self, contract, webhook, events, mocker
    ):
        mocker.patch(
            "soroscan.ingest.tasks.dispatch_webhook.apply",
            return_value=SimpleNamespace(successful=lambda: True, result=True),
        )
        sleep_mock = mocker.patch("soroscan.ingest.services.event_replay.time.sleep")
        older, newer, _ = events
        newer.timestamp = older.timestamp
        newer.save(update_fields=["timestamp"])
        replay_events(contract.contract_id, event_type="swap", realtime=True, limit=0)
        sleep_mock.assert_not_called()
        delivery = ReplayDelivery(
            event_id=older.id,
            event_type="swap",
            ledger=100,
            event_index=0,
            original_timestamp=older.timestamp.isoformat(),
            status="success",
            success=True,
        )
        assert delivery.to_dict()["event_id"] == older.id

    def test_realtime_sleeps_original_gaps(self, contract, webhook, events, mocker):
        mocker.patch(
            "soroscan.ingest.tasks.dispatch_webhook.apply",
            return_value=SimpleNamespace(successful=lambda: True, result=True),
        )
        sleep_mock = mocker.patch("soroscan.ingest.services.event_replay.time.sleep")
        replay_events(
            contract.contract_id,
            event_type="swap",
            realtime=True,
            max_delay_seconds=600,
            limit=0,
        )
        sleep_mock.assert_called_once_with(300.0)

    def test_realtime_caps_delay(self, contract, webhook, events, mocker):
        mocker.patch(
            "soroscan.ingest.tasks.dispatch_webhook.apply",
            return_value=SimpleNamespace(successful=lambda: True, result=True),
        )
        sleep_mock = mocker.patch("soroscan.ingest.services.event_replay.time.sleep")
        replay_events(
            contract.contract_id,
            event_type="swap",
            realtime=True,
            max_delay_seconds=2,
            limit=0,
        )
        sleep_mock.assert_called_once_with(2)

    def test_describe_database_target_has_no_secrets(self):
        snapshot = describe_database_target()
        assert "password" not in json.dumps(snapshot).lower()
        assert "host" in snapshot
        assert "name" in snapshot


@pytest.mark.django_db
class TestReplayEventsCommand:
    def _call(self, *args, **kwargs):
        out = StringIO()
        err = StringIO()
        call_command("replay_events", *args, stdout=out, stderr=err, **kwargs)
        return out.getvalue(), err.getvalue()

    def test_dry_run_prints_original_timestamps(self, contract, webhook, events):
        older, _, _ = events
        out, err = self._call(
            f"--contract={contract.contract_id}",
            "--dry-run",
            "--event-type=swap",
            "--limit=1",
        )
        assert "DRY RUN" in out
        assert "Events processed: 1" in out
        assert "local" in out
        assert older.timestamp.isoformat() in out
        assert "replaying 1" in err

    def test_unknown_contract_raises_command_error(self):
        with pytest.raises(CommandError, match="No TrackedContract"):
            call_command("replay_events", "--contract=" + ("C" + "A" * 55))

    def test_invalid_date_raises_command_error(self, contract):
        with pytest.raises(CommandError, match="Invalid --from-date"):
            call_command(
                "replay_events",
                f"--contract={contract.contract_id}",
                "--from-date=nope",
            )

    def test_writes_json_report(self, contract, webhook, events, tmp_path, mocker):
        mocker.patch(
            "soroscan.ingest.tasks.dispatch_webhook.apply",
            return_value=SimpleNamespace(successful=lambda: True, result=True),
        )
        report_path = tmp_path / "replay.json"
        call_command(
            "replay_events",
            f"--contract={contract.contract_id}",
            "--event-type=swap",
            "--limit=1",
            f"--output-json={report_path}",
        )
        data = json.loads(report_path.read_text())
        assert data["contract_id"] == contract.contract_id
        assert data["environment"] == "local"
        assert data["deliveries"][0]["original_timestamp"]
        assert data["summary"]["successes"] == 1

    def test_remote_flag_passed_through(self, contract, webhook, events, mocker):
        delay_mock = mocker.patch(
            "soroscan.ingest.tasks.dispatch_webhook.delay",
            return_value=SimpleNamespace(id="abc"),
        )
        out, _err = self._call(
            f"--contract={contract.contract_id}",
            "--environment=remote",
            "--event-type=swap",
            "--limit=1",
        )
        delay_mock.assert_called_once()
        assert "Environment:      remote" in out
        assert "Queued:" in out

    def test_no_events_message(self, contract, webhook):
        out, _err = self._call(f"--contract={contract.contract_id}", "--dry-run")
        assert "No events found matching the filters." in out

    def test_no_matching_webhooks_message(self, contract, events):
        out, _err = self._call(
            f"--contract={contract.contract_id}",
            "--dry-run",
            "--event-type=swap",
        )
        assert "No matching webhooks found" in out

    def test_live_summary_styles_success_and_failure(self, contract, webhook, events, mocker):
        mocker.patch(
            "soroscan.ingest.tasks.dispatch_webhook.apply",
            return_value=SimpleNamespace(successful=lambda: True, result=True),
        )
        out, _err = self._call(
            f"--contract={contract.contract_id}",
            "--event-type=swap",
            "--limit=1",
        )
        assert "LIVE" in out
        assert "success" in out

        mocker.patch(
            "soroscan.ingest.tasks.dispatch_webhook.apply",
            return_value=SimpleNamespace(successful=lambda: False, result="nope"),
        )
        out, _err = self._call(
            f"--contract={contract.contract_id}",
            "--event-type=swap",
            "--limit=1",
        )
        assert "failed" in out


@pytest.mark.django_db
class TestDispatchWebhookReplayMode:
    @responses.activate
    def test_replay_includes_original_timestamp_and_skips_dedup(self, webhook):
        event = ContractEventFactory(
            contract=webhook.contract,
            event_type="swap",
            timestamp=_aware(2026, 3, 15, 8, 30, 0),
        )
        responses.add(
            responses.POST,
            webhook.target_url,
            status=200,
            headers={"X-SoroScan-Ack": "ok"},
        )
        responses.add(
            responses.POST,
            webhook.target_url,
            status=200,
            headers={"X-SoroScan-Ack": "ok"},
        )

        first = dispatch_webhook.apply(args=[webhook.id, event.id, True])
        second = dispatch_webhook.apply(args=[webhook.id, event.id, True])

        assert first.result is True
        assert second.result is True
        assert len(responses.calls) == 2

        body = json.loads(responses.calls[0].request.body)
        assert body["timestamp"] == event.timestamp.isoformat()
        assert body["replay"] is True
        headers = responses.calls[0].request.headers
        assert headers["X-SoroScan-Replay"] == "true"
        assert headers["X-SoroScan-Original-Timestamp"] == event.timestamp.isoformat()

        assert WebhookDeliveryLog.objects.filter(subscription=webhook, event=event).count() == 2
