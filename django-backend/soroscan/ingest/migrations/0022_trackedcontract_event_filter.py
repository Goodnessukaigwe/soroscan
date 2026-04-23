from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ingest', '0021_trackedcontract_alias'),
    ]

    operations = [
        migrations.AddField(
            model_name='trackedcontract',
            name='event_filter_type',
            field=models.CharField(
                max_length=16,
                choices=[
                    ('none', 'No Filter'),
                    ('whitelist', 'Whitelist'),
                    ('blacklist', 'Blacklist'),
                ],
                default='none',
                help_text=(
                    'Ingest filter mode: none = store all events; '
                    'whitelist = only store listed event types; '
                    'blacklist = drop listed event types.'
                ),
            ),
        ),
        migrations.AddField(
            model_name='trackedcontract',
            name='event_filter_list',
            field=models.JSONField(
                default=list,
                blank=True,
                help_text='List of event type names used by the whitelist/blacklist filter.',
            ),
        ),
        migrations.AddIndex(
            model_name='trackedcontract',
            index=models.Index(
                fields=['event_filter_type'],
                name='ingest_trac_evt_filter_type_idx',
            ),
        ),
    ]
