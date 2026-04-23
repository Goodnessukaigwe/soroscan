# Generated merge migration to resolve conflicting branches

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("ingest", "0018_merge_deprecation_and_eventdedup"),
        ("ingest", "0018_merge_webhook_timeout_and_eventdedup"),
        ("ingest", "0019_merge_20260327_1621"),
        ("ingest", "0022_trackedcontract_event_filter"),
    ]

    operations = []
