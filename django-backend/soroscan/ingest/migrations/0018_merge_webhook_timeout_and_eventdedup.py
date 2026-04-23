from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("ingest", "0017_webhooksubscription_timeout_seconds"),
        ("ingest", "0017_eventdeduplicationlog"),
    ]

    operations = []
