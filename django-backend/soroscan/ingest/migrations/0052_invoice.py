import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingest", "0051_remove_eventaggregation_unique_contract_event_type_timestamp_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="Invoice",
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
                    "invoice_number",
                    models.CharField(db_index=True, max_length=64, unique=True),
                ),
                (
                    "billing_period",
                    models.DateField(
                        help_text="Month bucket represented by first day of the month (UTC)."
                    ),
                ),
                (
                    "amount_usd",
                    models.DecimalField(decimal_places=4, default=0, max_digits=14),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("issued", "Issued"),
                            ("paid", "Paid"),
                            ("void", "Void"),
                        ],
                        default="issued",
                        max_length=16,
                    ),
                ),
                (
                    "line_items",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Invoice line items derived from cost snapshot breakdown.",
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("issued_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "cost_snapshot",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="invoices",
                        to="ingest.organizationcostsnapshot",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invoices",
                        to="ingest.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["-billing_period", "-created_at"],
                "unique_together": {("organization", "billing_period")},
            },
        ),
        migrations.AddIndex(
            model_name="invoice",
            index=models.Index(
                fields=["organization", "billing_period"],
                name="ingest_invoice_org_period_idx",
            ),
        ),
    ]
