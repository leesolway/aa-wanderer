import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eve_sde', '0001_initial'),
        ('wanderer', '0003_mapstructure_owner_alliance_inserted_at'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='mapstructure',
            name='solar_system_id',
        ),
        migrations.RemoveField(
            model_name='mapstructure',
            name='solar_system_name',
        ),
        migrations.AddField(
            model_name='mapstructure',
            name='solar_system',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='eve_sde.solarsystem',
            ),
        ),
    ]
