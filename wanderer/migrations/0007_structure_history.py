import django.db.models.deletion
from django.db import migrations, models


def backfill_structures(apps, schema_editor):
    """
    Populate the new deduplicated Structure table from whatever MapStructure data
    already exists, so the systems list isn't empty until the next hourly sync.
    """
    from wanderer.structures import reconcile_structures

    reconcile_structures()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('eve_sde', '0001_initial'),
        ('wanderer', '0006_structurefilterpreset'),
    ]

    operations = [
        migrations.AddField(
            model_name='mapstructure',
            name='structure_updated_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text=(
                    "The 'updated_at' timestamp reported by Wanderer for this "
                    "structure, used to decide which source map has the freshest "
                    "data for a structure seen on more than one map."
                ),
            ),
        ),
        migrations.CreateModel(
            name='Structure',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('structure_type', models.CharField(blank=True, max_length=100)),
                ('structure_type_id', models.CharField(blank=True, max_length=50)),
                ('owner_name', models.CharField(blank=True, max_length=255)),
                ('owner_ticker', models.CharField(blank=True, max_length=10)),
                ('owner_id', models.CharField(blank=True, max_length=50)),
                ('alliance_name', models.CharField(blank=True, max_length=255)),
                ('alliance_ticker', models.CharField(blank=True, max_length=10)),
                ('alliance_id', models.CharField(blank=True, max_length=50)),
                ('status', models.CharField(blank=True, max_length=50)),
                ('end_time', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('first_seen_at', models.DateTimeField(auto_now_add=True)),
                ('last_seen_at', models.DateTimeField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('removed_at', models.DateTimeField(blank=True, null=True)),
                ('solar_system', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='eve_sde.solarsystem')),
                ('last_source_map', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to='wanderer.wanderermanagedmap',
                    help_text=(
                        "Map that most recently supplied this structure's data. Kept "
                        "for admin/debugging only - not shown to end users, who "
                        "shouldn't need to care which map a structure was seen on."
                    ),
                )),
            ],
            options={
                'ordering': ['solar_system__name', 'name'],
            },
        ),
        migrations.AddConstraint(
            model_name='structure',
            constraint=models.UniqueConstraint(
                fields=('solar_system', 'name', 'structure_type_id'),
                name='functional_pk_structure_identity',
            ),
        ),
        migrations.CreateModel(
            name='StructureHistory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('recorded_at', models.DateTimeField(auto_now_add=True)),
                ('change_type', models.CharField(choices=[
                    ('created', 'Created'),
                    ('updated', 'Updated'),
                    ('removed', 'Removed'),
                    ('reappeared', 'Reappeared'),
                ], max_length=20)),
                ('changed_fields', models.JSONField(blank=True, default=list)),
                ('name', models.CharField(blank=True, max_length=255)),
                ('structure_type', models.CharField(blank=True, max_length=100)),
                ('structure_type_id', models.CharField(blank=True, max_length=50)),
                ('owner_name', models.CharField(blank=True, max_length=255)),
                ('owner_ticker', models.CharField(blank=True, max_length=10)),
                ('owner_id', models.CharField(blank=True, max_length=50)),
                ('alliance_name', models.CharField(blank=True, max_length=255)),
                ('alliance_ticker', models.CharField(blank=True, max_length=10)),
                ('alliance_id', models.CharField(blank=True, max_length=50)),
                ('status', models.CharField(blank=True, max_length=50)),
                ('end_time', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('structure', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='history', to='wanderer.structure')),
            ],
            options={
                'ordering': ['-recorded_at'],
                'verbose_name_plural': 'structure histories',
            },
        ),
        migrations.RunPython(backfill_structures, noop),
    ]
