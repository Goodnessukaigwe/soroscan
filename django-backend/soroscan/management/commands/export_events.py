"""
Management command: export_events

Exports ContractEvent records to CSV or JSON format.

Usage:
    python manage.py export_events --contract=CA7N... --format=csv --output=events.csv
    python manage.py export_events --contract=CA7N... --format=json --output=events.json
    python manage.py export_events --contract=CA7N... --format=json --from-ledger=100 --to-ledger=1000
    python manage.py export_events --contract=CA7N... --format=csv  # writes to stdout
"""
import csv
import json
import sys

from django.core.management.base import BaseCommand, CommandError

from soroscan.ingest.models import ContractEvent, TrackedContract


class Command(BaseCommand):
    help = "Export contract events to CSV or JSON."

    def add_arguments(self, parser):
        parser.add_argument(
            "--contract",
            required=True,
            help="Contract ID to export events for",
        )
        parser.add_argument(
            "--format",
            choices=["csv", "json"],
            default="csv",
            help="Output format (default: csv)",
        )
        parser.add_argument(
            "--output",
            help="Output file path (writes to stdout if not provided)",
        )
        parser.add_argument(
            "--from-ledger",
            type=int,
            default=None,
            help="Export events from this ledger (inclusive)",
        )
        parser.add_argument(
            "--to-ledger",
            type=int,
            default=None,
            help="Export events up to this ledger (inclusive)",
        )

    def handle(self, *args, **options):
        contract_id = options["contract"]
        fmt = options["format"]
        output = options["output"]
        from_ledger = options["from_ledger"]
        to_ledger = options["to_ledger"]

        # Validate contract exists
        if not TrackedContract.objects.filter(contract_id=contract_id).exists():
            raise CommandError(f"No TrackedContract found with contract_id={contract_id!r}")

        # Validate ledger range
        if from_ledger is not None and to_ledger is not None and from_ledger > to_ledger:
            raise CommandError("--from-ledger must be <= --to-ledger")

        # Build queryset
        qs = (
            ContractEvent.objects.filter(contract__contract_id=contract_id)
            .select_related("contract")
            .order_by("ledger", "event_index")
        )

        if from_ledger is not None:
            qs = qs.filter(ledger__gte=from_ledger)
        if to_ledger is not None:
            qs = qs.filter(ledger__lte=to_ledger)

        count = qs.count()
        self.stderr.write(f"Exporting {count} events from contract {contract_id} as {fmt}")

        # Determine output
        out_file = None
        if output:
            out_file = open(output, "w", encoding="utf-8", newline="")
            file_handle = out_file
        else:
            file_handle = sys.stdout

        try:
            if fmt == "json":
                self._export_json(qs, file_handle)
            else:
                self._export_csv(qs, file_handle)
        finally:
            if out_file:
                out_file.close()

        if output:
            self.stdout.write(self.style.SUCCESS(f"Exported {count} events to {output}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Exported {count} events to stdout"))

    def _export_json(self, qs, out):
        """Export events as a JSON array."""
        out.write("[\n")
        events_list = []
        for event in qs:
            events_list.append(self._event_to_dict(event))
        json.dump(events_list, out, indent=2, default=str)
        out.write("\n]")

    def _export_csv(self, qs, out):
        """Export events as CSV."""
        writer = csv.writer(out)
        # Write header
        writer.writerow([
            "contract_id",
            "event_type",
            "schema_version",
            "validation_status",
            "payload",
            "payload_hash",
            "ledger",
            "event_index",
            "timestamp",
            "tx_hash",
            "raw_xdr",
            "decoded_payload",
            "decoding_status",
            "signature_status",
        ])
        # Write rows
        for event in qs:
            writer.writerow([
                event.contract.contract_id,
                event.event_type,
                event.schema_version,
                event.validation_status,
                json.dumps(event.payload),
                event.payload_hash,
                event.ledger,
                event.event_index,
                event.timestamp.isoformat() if event.timestamp else "",
                event.tx_hash,
                event.raw_xdr,
                json.dumps(event.decoded_payload) if event.decoded_payload else "",
                event.decoding_status,
                event.signature_status,
            ])

    def _event_to_dict(self, event: ContractEvent) -> dict:
        return {
            "contract_id": event.contract.contract_id,
            "event_type": event.event_type,
            "schema_version": event.schema_version,
            "validation_status": event.validation_status,
            "payload": event.payload,
            "payload_hash": event.payload_hash,
            "ledger": event.ledger,
            "event_index": event.event_index,
            "timestamp": event.timestamp.isoformat() if event.timestamp else None,
            "tx_hash": event.tx_hash,
            "raw_xdr": event.raw_xdr,
            "decoded_payload": event.decoded_payload,
            "decoding_status": event.decoding_status,
            "signature_status": event.signature_status,
        }