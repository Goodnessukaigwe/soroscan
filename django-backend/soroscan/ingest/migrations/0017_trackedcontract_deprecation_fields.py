from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingest", "0015_merge_notification_and_teams"),
    ]

    operations = [
        migrations.AddField(
            model_name="trackedcontract",
            name="deprecation_reason",
            field=models.TextField(
                blank=True,
                help_text="Optional reason shown to users when contract is deprecated/suspended",
            ),
        ),
        migrations.AddField(
            model_name="trackedcontract",
            name="deprecation_status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("deprecated", "Deprecated"),
                    ("suspended", "Suspended"),
                ],
                db_index=True,
                default="active",
                help_text="Manual lifecycle/deprecation state for warning users",
                max_length=16,
            ),
        ),
    ]
