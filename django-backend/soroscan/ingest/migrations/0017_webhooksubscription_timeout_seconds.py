# Generated migration for webhook subscription timeout

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingest", "0015_merge_notification_and_teams"),
    ]

    operations = [
        migrations.AddField(
            model_name="webhooksubscription",
            name="timeout_seconds",
            field=models.IntegerField(
                default=10,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(60),
                ],
                help_text="Timeout for webhook dispatch in seconds (1-60, default: 10)",
            ),
        ),
    ]
