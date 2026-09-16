from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wanderer', '0007_structure_history'),
    ]

    operations = [
        migrations.AddField(
            model_name='structurefilterpreset',
            name='wh_class_ids',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='structurefilterpreset',
            name='static_leads_to_ids',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='structurefilterpreset',
            name='effect_names',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
