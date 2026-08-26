"""
Management command: replay_events

Replay ContractEvent records from the database through existing webhook
delivery or event-processing logic. Events are fetched via the Django ORM
and dispatched in original-timestamp order.

Works against whichever environment Django is configured for (local .env
or remote DATABASE_URL / REDIS_URL). Use --environment to choose eager
local dispatch vs remote Celery enqueue.

Usage:
    python manage.py replay_events --contract=CA7N...
    python manage.py replay_events --contract=CA7N... --event-type=swap
    python manage.py replay_events --contract=CA7N... --from-ledger=100 --to-ledger=200
    python manage.py replay_events --contract=CA7N... --dry-run
    python manage.py replay_events --contract=CA7N... --environment=remote --target=processing
    python manage.py replay_events --contract=CA7N... --realtime --limit=10
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from soroscan.ingest.services.event_replay import (
    DEFAULT_LIMIT,
    DEFAULT_MAX_DELAY_SECONDS,
    ENV_LOCAL,
    TARGET_PROCESSING,
    TARGET_WEBHOOKS,
    VALID_ENVIRONMENTS,
    VALID_TARGETS,
    ReplayError,
    replay_events,
)


class Command(BaseCommand):
    help = (
        "Replay stored contract events through webhook delivery or event processing. "
        "Events are fetched from the database and replayed with their original timestamps. "
        "Use --environment local (eager apply) or remote (Celery delay). "
        "DATABASE_URL / REDIS_URL select the local or remote data store."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--contract",
            required=True,
            help="Contract ID to replay events for",
        )
        parser.add_argument(
            "--event-type",
            default=None,
            help="Filter by event type",
        )
        parser.add_argument(
            "--from-ledger",
            type=int,
            default=None,
            help="Include events from this ledger (inclusive)",
        )
        parser.add_argument(
            "--to-ledger",
            type=int,
            default=None,
            help="Include events up to this ledger (inclusive)",
        )
        parser.add_argument(
            "--from-date",
            default=None,
            help="Include events from this date (ISO format)",
        )
        parser.add_argument(
            "--to-date",
            default=None,
            help="Include events up to this date (ISO format)",
        )
        parser.add_argument(
            "--event-id",
            type=int,
            default=None,
            help="Replay a single ContractEvent primary key",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=DEFAULT_LIMIT,
            help="Max events to replay (default: 100, 0 = all)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview replay plan without dispatching",
        )
        parser.add_argument(
            "--webhook-id",
            type=int,
            default=None,
            help="Replay only to specific webhook subscription ID",
        )
        parser.add_argument(
            "--environment",
            choices=VALID_ENVIRONMENTS,
            default=ENV_LOCAL,
            help=(
                "local: run dispatch synchronously via Celery apply (developer machine). "
                "remote: enqueue onto the configured Celery broker (staging/production workers). "
                f"Default: {ENV_LOCAL}."
            ),
        )
        parser.add_argument(
            "--target",
            choices=VALID_TARGETS,
            default=TARGET_WEBHOOKS,
            help=(
                f"{TARGET_WEBHOOKS}: re-send via dispatch_webhook. "
                f"{TARGET_PROCESSING}: re-run process_new_event. "
                f"Default: {TARGET_WEBHOOKS}."
            ),
        )
        parser.add_argument(
            "--realtime",
            action="store_true",
            help="Sleep between events using original timestamp gaps (capped by --max-delay)",
        )
        parser.add_argument(
            "--max-delay",
            type=float,
            default=DEFAULT_MAX_DELAY_SECONDS,
            help=f"Maximum sleep in seconds when --realtime is set (default: {DEFAULT_MAX_DELAY_SECONDS})",
        )
        parser.add_argument(
            "--output-json",
            default=None,
            help="Write delivery report to a JSON file",
        )

    def handle(self, *args, **options):
        try:
            report = replay_events(
                options["contract"],
                environment=options["environment"],
                target=options["target"],
                event_type=options["event_type"],
                from_ledger=options["from_ledger"],
                to_ledger=options["to_ledger"],
                from_date=options["from_date"],
                to_date=options["to_date"],
                event_id=options["event_id"],
                limit=options["limit"],
                dry_run=options["dry_run"],
                webhook_id=options["webhook_id"],
                realtime=options["realtime"],
                max_delay_seconds=options["max_delay"],
            )
        except ReplayError as exc:
            raise CommandError(str(exc)) from exc

        db = report.database
        self.stderr.write(
            f"Found {report.summary['events_matched']} matching events, "
            f"replaying {report.summary['events_processed']} "
            f"[{report.environment}/{report.target}] "
            f"db={db.get('host')}/{db.get('name')}..."
        )

        if not report.deliveries and report.summary["events_matched"] == 0:
            self.stdout.write("No events found matching the filters.")
            return

        if (
            report.target == TARGET_WEBHOOKS
            and report.summary["webhook_dispatches"] == 0
            and report.summary["skipped"]
            and not report.deliveries
        ):
            self.stdout.write("No matching webhooks found for these events. Nothing to replay.")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Replay Summary ==="))
        self.stdout.write(f"Mode:             {'DRY RUN' if options['dry_run'] else 'LIVE'}")
        self.stdout.write(f"Environment:      {report.environment}")
        self.stdout.write(f"Target:           {report.target}")
        self.stdout.write(f"Database:         {db.get('host')}/{db.get('name')}")
        self.stdout.write(f"Events processed: {report.summary['events_processed']}")
        self.stdout.write(f"Webhook dispatches: {report.summary['webhook_dispatches']}")
        self.stdout.write(f"Successes:        {report.summary['successes']}")
        self.stdout.write(f"Failures:         {report.summary['failures']}")
        self.stdout.write(f"Queued:           {report.summary['queued']}")
        self.stdout.write(f"Skipped:          {report.summary['skipped']}")

        output_json = options["output_json"]
        if output_json:
            self._write_report(report.to_dict(), output_json)

        if report.deliveries and not output_json:
            self.stdout.write("")
            heading = (
                "Planned deliveries (last 10):"
                if options["dry_run"]
                else "Detailed delivery log (last 10):"
            )
            self.stdout.write(heading)
            for delivery in report.deliveries[-10:]:
                status = delivery.status
                status_code = delivery.status_code
                original_ts = delivery.original_timestamp or ""
                if "success" in status:
                    style = self.style.SUCCESS
                elif "fail" in status or "error" in status or (status_code and status_code >= 400):
                    style = self.style.ERROR
                else:
                    def style(text):
                        return text
                extra = f" {status_code}" if status_code else ""
                webhook_bit = (
                    f"-> Webhook {delivery.webhook_id} "
                    if delivery.webhook_id is not None
                    else ""
                )
                self.stdout.write(
                    f"  Event {delivery.event_id} ({delivery.event_type}@"
                    f"{delivery.ledger} {original_ts}) {webhook_bit}: {style(status)}{extra}".rstrip()
                )

    def _write_report(self, report: dict, path: str) -> None:
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, default=str)
        self.stdout.write(self.style.SUCCESS(f"Report written to {out_path}"))
