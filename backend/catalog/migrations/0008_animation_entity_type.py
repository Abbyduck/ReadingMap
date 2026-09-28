from django.db import migrations, models
from django.db.models import Q


ENTITY_TYPES = ["animation", "book", "level", "reading_system", "series", "set"]


class Migration(migrations.Migration):
    dependencies = [("catalog", "0007_reading_system_entity_type")]

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
                    ("animation", "动画"),
                    ("reading_system", "阅读产品线"),
                    ("series", "系列"),
                    ("level", "级别"),
                    ("set", "组合"),
                ],
                db_index=True,
                max_length=50,
            ),
        ),
        migrations.AddConstraint(
            model_name="catalogentity",
            constraint=models.CheckConstraint(
                condition=Q(entity_type__in=ENTITY_TYPES),
                name="catalog_entity_type_valid",
            ),
        ),
    ]
