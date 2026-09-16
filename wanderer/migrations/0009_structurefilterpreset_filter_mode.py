from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wanderer", "0008_structurefilterpreset_wh_filters"),
    ]

    operations = [
        migrations.AddField(
            model_name="structurefilterpreset",
            name="filter_mode",
            field=models.CharField(
                choices=[("or", "OR (match any)"), ("and", "AND (match all)")],
                default="or",
                help_text="Whether entity filters (system/corp/alliance) are combined with OR or AND logic.",
                max_length=3,
            ),
        ),
    ]
