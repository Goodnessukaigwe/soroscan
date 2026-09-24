"""Partition ingest_contractevent by (timestamp, ledger_sequence) on Postgres.

Uses RunPython (not RunSQL) so the vendor check happens at migration-apply
time rather than unconditionally — this keeps the migration a no-op on
non-Postgres backends (e.g. SQLite in tests), matching the pattern used in
0044_contractevent_payload_compression.py.
"""

from django.db import migrations


def partition_contractevent(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            DROP TABLE IF EXISTS ingest_contractevent_old CASCADE;
            -- 1. Rename existing table
            ALTER TABLE ingest_contractevent RENAME TO ingest_contractevent_old;

            -- 2. Create the new partitioned table (by timestamp range)
            CREATE TABLE ingest_contractevent (
                LIKE ingest_contractevent_old INCLUDING DEFAULTS INCLUDING CONSTRAINTS
            ) PARTITION BY RANGE ("timestamp");

            -- 3. Create initial active partitions and default partition
            CREATE TABLE ingest_contractevent_y2026m08 PARTITION OF ingest_contractevent
                FOR VALUES FROM ('2026-08-01 00:00:00+00') TO ('2026-09-01 00:00:00+00');

            CREATE TABLE ingest_contractevent_y2026m09 PARTITION OF ingest_contractevent
                FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00');

            CREATE TABLE ingest_contractevent_default PARTITION OF ingest_contractevent DEFAULT;

            -- 4. Migrate data
            INSERT INTO ingest_contractevent SELECT * FROM ingest_contractevent_old;

            -- 5. Drop old temporary table
            DROP TABLE ingest_contractevent_old CASCADE;
            """
        )


def unpartition_contractevent(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            DROP TABLE ingest_contractevent;
            ALTER TABLE ingest_contractevent_old RENAME TO ingest_contractevent;
            """
        )


class Migration(migrations.Migration):

    dependencies = [
        ('ingest', '0053_webhook_replay_job'),
    ]

    operations = [
        migrations.RunPython(partition_contractevent, unpartition_contractevent),
    ]
