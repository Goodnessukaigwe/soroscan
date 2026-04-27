from datetime import timedelta
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from soroscan.ingest.models import ContractEvent


class Command(BaseCommand):
    help = "Delete ContractEvents older than configured retention period"

    def add_arguments(self, parser):
        parser.add_argument(
            "--retention-days",
            type=int,
            default=getattr(settings, "EVENT_RETENTION_DAYS", 30),
            help="Number of days to retain events (default: 30)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        retention_days = options["retention_days"]
        dry_run = options["dry_run"]
        
        cutoff_date = timezone.now() - timedelta(days=retention_days)
        
        # Query events older than cutoff date
        old_events = ContractEvent.objects.filter(timestamp__lt=cutoff_date)
        count = old_events.count()
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN: Would delete {count} events older than {retention_days} days "
                    f"(before {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')})"
                )
            )
        else:
            if count > 0:
                deleted_count, _ = old_events.delete()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully deleted {deleted_count} events older than {retention_days} days"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS("No events found older than retention period")
                )
