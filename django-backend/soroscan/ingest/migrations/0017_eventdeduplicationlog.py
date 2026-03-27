# Generated migration for EventDeduplicationLog

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingest", "0015_merge_notification_and_teams"),
    ]

    operations = [
        migrations.CreateModel(
            name="EventDeduplicationLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "ledger",
                    models.PositiveBigIntegerField(
                        db_index=True,
                        help_text="Ledger sequence number",
                    ),
                ),
                (
                    "event_index",
                    models.PositiveIntegerField(
                        help_text="0-based event index within the ledger",
                    ),
                ),
                (
                    "tx_hash",
                    models.CharField(
                        help_text="Transaction hash",
                        max_length=64,
                    ),
                ),
                (
                    "event_type",
                    models.CharField(
                        help_text="Event type that was checked",
                        max_length=100,
                    ),
                ),
                (
                    "duplicate_detected",
                    models.BooleanField(
                        default=False,
                        help_text="True if a duplicate was detected",
                    ),
                ),
                (
                    "reason",
                    models.CharField(
                        blank=True,
                        help_text="Reason for the deduplication decision",
                        max_length=255,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        help_text="UTC timestamp of this deduplication check",
                    ),
                ),
                (
                    "contract",
                    models.ForeignKey(
                        help_text="Contract the event belongs to",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dedup_logs",
                        to="ingest.trackedcontract",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="eventdeduplicationlog",
            index=models.Index(
                fields=["contract", "created_at"],
                name="ingest_even_contract_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="eventdeduplicationlog",
            index=models.Index(
                fields=["contract", "ledger", "event_index"],
                name="ingest_even_contract_ledger_idx",
            ),
        ),
    ]
