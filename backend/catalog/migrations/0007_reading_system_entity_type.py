from django.db import migrations, models
from django.db.models import Q


ENTITY_TYPES = ["book", "level", "reading_system", "series", "set"]


def migrate_ready_to_read(apps, schema_editor):
    CatalogEntity = apps.get_model("catalog", "CatalogEntity")
    CatalogEntity.objects.filter(
        display_title="Ready-to-Read",
        entity_type="series",
    ).update(entity_type="reading_system")


def reverse_ready_to_read(apps, schema_editor):
    CatalogEntity = apps.get_model("catalog", "CatalogEntity")
    CatalogEntity.objects.filter(
        display_title="Ready-to-Read",
        entity_type="reading_system",
    ).update(entity_type="series")


class Migration(migrations.Migration):
    dependencies = [("catalog", "0006_catalogentity_bookshelf_visible")]

    operations = [
        migrations.RemoveConstraint(
            model_name="catalogentity",
            name="catalog_entity_type_valid",
        ),
        migrations.AlterField(
            model_name="catalogentity",
            name="entity_type",
            field=models.CharField(
                choices=[
                    ("book", "单本"),
                    ("reading_system", "阅读产品线"),
                    ("series", "系列"),
                    ("level", "级别"),
                    ("set", "组合"),
                ],
                db_index=True,
                max_length=50,
            ),
        ),
        migrations.RunPython(migrate_ready_to_read, reverse_ready_to_read),
        migrations.AddConstraint(
            model_name="catalogentity",
            constraint=models.CheckConstraint(
                condition=Q(entity_type__in=ENTITY_TYPES),
                name="catalog_entity_type_valid",
            ),
        ),
    ]
