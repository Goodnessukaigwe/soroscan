# Generated migration for issue #20 - database query optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingest", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="contractevent",
            index=models.Index(fields=["contract", "-timestamp"], name="ingest_cont_contrac_idx_timestamp"),
        ),
        migrations.AddIndex(
            model_name="contractevent",
            index=models.Index(fields=["contract", "event_type"], name="ingest_cont_contrac_idx_event_type"),
        ),
        migrations.AddIndex(
            model_name="contractevent",
            index=models.Index(fields=["-timestamp"], name="ingest_cont_timestamp_idx"),
        ),
    ]
