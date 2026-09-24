from django.db import migrations
import soroscan.ingest.fields

class Migration(migrations.Migration):

    dependencies = [
        ('ingest', '0053_webhook_replay_job'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DROP INDEX IF EXISTS ingest_contractevent_payload_gin;
            ALTER TABLE ingest_contractevent ALTER COLUMN payload TYPE bytea USING convert_to(payload::text, 'UTF8');
            """,
            reverse_sql="""
            ALTER TABLE ingest_contractevent ALTER COLUMN payload TYPE jsonb USING payload::text::jsonb;
            CREATE INDEX IF NOT EXISTS ingest_contractevent_payload_gin ON ingest_contractevent USING gin (payload);
            """,
        ),
        migrations.AlterField(
            model_name='contractevent',
            name='payload',
            field=soroscan.ingest.fields.CompressedJSONField(help_text='Decoded event payload'),
        ),
    ]

