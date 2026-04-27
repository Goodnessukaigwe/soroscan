from datetime import timedelta
from io import StringIO
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from soroscan.ingest.tests.factories import ContractEventFactory, TrackedContractFactory


class TestPruneEventsCommand(TestCase):
    def setUp(self):
        self.contract = TrackedContractFactory()
        
    def test_prune_old_events(self):
        """Test that events older than retention period are deleted."""
        # Create old events (40 days ago)
        old_timestamp = timezone.now() - timedelta(days=40)
        for _ in range(3):
            ContractEventFactory(contract=self.contract, timestamp=old_timestamp)
        
        # Create recent events (10 days ago)
        recent_timestamp = timezone.now() - timedelta(days=10)
        recent_events = [
            ContractEventFactory(contract=self.contract, timestamp=recent_timestamp)
            for _ in range(2)
        ]
        
        # Run command with 30-day retention
        out = StringIO()
        call_command("prune_events", "--retention-days=30", stdout=out)
        
        # Verify old events are deleted, recent events remain
        from soroscan.ingest.models import ContractEvent
        remaining_events = ContractEvent.objects.all()
        self.assertEqual(remaining_events.count(), 2)
        
        # Verify the remaining events are the recent ones
        remaining_ids = set(remaining_events.values_list("id", flat=True))
        expected_ids = {event.id for event in recent_events}
        self.assertEqual(remaining_ids, expected_ids)
        
        # Check output message
        output = out.getvalue()
        self.assertIn("Successfully deleted 3 events", output)
        
    def test_dry_run_mode(self):
        """Test that dry-run mode doesn't delete events."""
        # Create old events
        old_timestamp = timezone.now() - timedelta(days=40)
        for _ in range(2):
            ContractEventFactory(contract=self.contract, timestamp=old_timestamp)
        
        # Run dry-run command
        out = StringIO()
        call_command("prune_events", "--retention-days=30", "--dry-run", stdout=out)
        
        # Verify no events were deleted
        from soroscan.ingest.models import ContractEvent
        self.assertEqual(ContractEvent.objects.count(), 2)
        
        # Check output message
        output = out.getvalue()
        self.assertIn("DRY RUN: Would delete 2 events", output)
        
    def test_no_old_events(self):
        """Test command when no events are older than retention period."""
        # Create only recent events
        recent_timestamp = timezone.now() - timedelta(days=10)
        ContractEventFactory(contract=self.contract, timestamp=recent_timestamp)
        
        # Run command
        out = StringIO()
        call_command("prune_events", "--retention-days=30", stdout=out)
        
        # Verify no events were deleted
        from soroscan.ingest.models import ContractEvent
        self.assertEqual(ContractEvent.objects.count(), 1)
        
        # Check output message
        output = out.getvalue()
        self.assertIn("No events found older than retention period", output)
        
    @override_settings(EVENT_RETENTION_DAYS=60)
    def test_uses_settings_default(self):
        """Test that command uses EVENT_RETENTION_DAYS setting as default."""
        # Create events 50 days old (should not be deleted with 60-day retention)
        old_timestamp = timezone.now() - timedelta(days=50)
        ContractEventFactory(contract=self.contract, timestamp=old_timestamp)
        
        # Run command without specifying retention-days
        out = StringIO()
        call_command("prune_events", stdout=out)
        
        # Verify event was not deleted (50 < 60 days)
        from soroscan.ingest.models import ContractEvent
        self.assertEqual(ContractEvent.objects.count(), 1)
        
    def test_custom_retention_days(self):
        """Test command with custom retention days parameter."""
        # Create events 20 days old
        old_timestamp = timezone.now() - timedelta(days=20)
        ContractEventFactory(contract=self.contract, timestamp=old_timestamp)
        
        # Run command with 15-day retention
        out = StringIO()
        call_command("prune_events", "--retention-days=15", stdout=out)
        
        # Verify event was deleted (20 > 15 days)
        from soroscan.ingest.models import ContractEvent
        self.assertEqual(ContractEvent.objects.count(), 0)
        
        # Check output message
        output = out.getvalue()
        self.assertIn("Successfully deleted 1 events", output)
