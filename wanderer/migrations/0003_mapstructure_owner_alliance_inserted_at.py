from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wanderer', '0002_wanderermanagedmap_sync_structures_mapstructure'),
    ]

    operations = [
        migrations.AddField(
            model_name='mapstructure',
            name='owner_id',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='mapstructure',
            name='alliance_name',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='mapstructure',
            name='alliance_ticker',
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name='mapstructure',
            name='alliance_id',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='mapstructure',
            name='inserted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
