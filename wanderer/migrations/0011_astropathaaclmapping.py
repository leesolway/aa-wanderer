import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("wanderer", "0010_priority_structurefilterpreset"),
    ]

    operations = [
        # Drop tables if they were partially created by a previously failed run
        # of this migration before the model state was recorded.
        migrations.RunSQL(
            "DROP TABLE IF EXISTS wanderer_astropathaclmapping",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "DROP TABLE IF EXISTS wanderer_astropathconfiguration",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.CreateModel(
            name="AstropathConfiguration",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "url",
                    models.CharField(
                        max_length=200,
                        help_text="URL of the Astropath instance (e.g. https://astropath.outfit418.com)",
                    ),
                ),
                (
                    "api_key",
                    models.CharField(
                        max_length=200,
                        help_text="API key with the access_lists:read and access_lists:write scopes.",
                    ),
                ),
            ],
            options={
                "verbose_name": "Astropath Configuration",
                "verbose_name_plural": "Astropath Configuration",
            },
        ),
        migrations.CreateModel(
            name="AstropathACLMapping",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        help_text="AA group whose members will be synced to the Astropath ACL.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="astropath_acl_mappings",
                        to="auth.group",
                        verbose_name="group",
                    ),
                ),
                (
                    "acl_id",
                    models.BigIntegerField(
                        help_text="Numeric ID of the ACL in Astropath.",
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("viewer", "Viewer"),
                            ("editor", "Editor"),
                            ("admin", "Admin"),
                        ],
                        default="viewer",
                        help_text="Role assigned to group members in the ACL.",
                        max_length=10,
                    ),
                ),
            ],
            options={
                "verbose_name": "Astropath ACL Mapping",
                "verbose_name_plural": "Astropath ACL Mappings",
            },
        ),
        migrations.AddConstraint(
            model_name="astropathaclmapping",
            constraint=models.UniqueConstraint(
                fields=["group", "acl_id"],
                name="unique_astropath_group_acl",
            ),
        ),
    ]
