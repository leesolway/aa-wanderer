from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wanderer', '0004_mapstructure_solar_system_fk'),
    ]

    operations = [
        migrations.AddField(
            model_name='mapstructure',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='mapstructure',
            name='removed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
