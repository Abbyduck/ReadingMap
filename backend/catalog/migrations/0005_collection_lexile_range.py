from django.db import migrations, models
from django.db.models import F, Q


class Migration(migrations.Migration):
    dependencies = [("catalog", "0004_catalog_taxonomy_descriptions_v1")]

    operations = [
        migrations.AddField(
            model_name="collection",
            name="lexile_min",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="collection",
            name="lexile_max",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="collection",
            constraint=models.CheckConstraint(
                condition=Q(lexile_min__isnull=True) | Q(lexile_max__isnull=True) | Q(lexile_min__lte=F("lexile_max")),
                name="collection_lexile_range_order",
            ),
        ),
    ]
