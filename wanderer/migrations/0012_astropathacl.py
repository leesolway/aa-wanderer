import django.db.models.deletion
from django.db import migrations, models


def create_acl_rows(apps, schema_editor):
    """For each distinct acl_id in AstropathACLMapping, create an AstropathACL row
    and point the mapping's acl_fk at it."""
    AstropathACLMapping = apps.get_model("wanderer", "AstropathACLMapping")
    AstropathACL = apps.get_model("wanderer", "AstropathACL")
    acl_by_id = {}
    for mapping in AstropathACLMapping.objects.all():
        if mapping.acl_id not in acl_by_id:
            acl_by_id[mapping.acl_id] = AstropathACL.objects.create(
                acl_id=mapping.acl_id, name=""
            )
        mapping.acl_fk = acl_by_id[mapping.acl_id]
        mapping.save()


class Migration(migrations.Migration):

    dependencies = [
        ("wanderer", "0011_astropathaaclmapping"),
    ]

    operations = [
        # 1. Create the new parent model
        migrations.CreateModel(
            name="AstropathACL",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("acl_id", models.BigIntegerField(unique=True, help_text="Numeric ID of the ACL in Astropath.")),
                ("name", models.CharField(blank=True, default="", max_length=200)),
            ],
            options={
                "verbose_name": "Astropath ACL",
                "verbose_name_plural": "Astropath ACLs",
                "ordering": ["name", "acl_id"],
            },
        ),
        # 2. Add nullable FK so we can populate it before making it required
        migrations.AddField(
            model_name="astropathaclmapping",
            name="acl_fk",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="mappings",
                to="wanderer.astropathacl",
            ),
        ),
        # 3. Populate AstropathACL rows and link existing mappings
        migrations.RunPython(create_acl_rows, migrations.RunPython.noop),
        # 4. Make FK non-nullable now that every row has a value
        migrations.AlterField(
            model_name="astropathaclmapping",
            name="acl_fk",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="mappings",
                to="wanderer.astropathacl",
            ),
        ),
        # 5. Drop the old unique constraint (references the old acl_id integer column)
        migrations.RemoveConstraint(
            model_name="astropathaclmapping",
            name="unique_astropath_group_acl",
        ),
        # 6. Remove the old integer acl_id column
        migrations.RemoveField(
            model_name="astropathaclmapping",
            name="acl_id",
        ),
        # 7. Rename acl_fk → acl (column becomes acl_id, matching the FK convention)
        migrations.RenameField(
            model_name="astropathaclmapping",
            old_name="acl_fk",
            new_name="acl",
        ),
        # 8. Add the new unique constraint on (acl, group)
        migrations.AddConstraint(
            model_name="astropathaclmapping",
            constraint=models.UniqueConstraint(
                fields=["acl", "group"],
                name="unique_astropath_acl_group",
            ),
        ),
    ]
