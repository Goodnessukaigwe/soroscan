from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingest", "0022_trackedcontract_event_filter"),
    ]

    operations = [
        migrations.AddField(
            model_name="webhookdeliverylog",
            name="payload_bytes",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Size of the webhook payload in bytes",
                null=True,
            ),
        ),
    ]