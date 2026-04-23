# Generated migration for webhook backoff strategy configurability

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "ingest",
            "0029_contractmetadata",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="webhooksubscription",
            name="retry_backoff_seconds",
            field=models.PositiveIntegerField(
                default=60,
                help_text="Base seconds for backoff calculation (1-3600, default: 60)",
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(3600),
                ],
            ),
        ),
        migrations.AddField(
            model_name="webhooksubscription",
            name="retry_backoff_strategy",
            field=models.CharField(
                choices=[
                    ("exponential", "Exponential (base * 2^attempt)"),
                    ("linear", "Linear (base * attempt)"),
                    ("fixed", "Fixed (base seconds)"),
                ],
                default="exponential",
                help_text="Strategy for calculating retry delays",
                max_length=16,
            ),
        ),
    ]
