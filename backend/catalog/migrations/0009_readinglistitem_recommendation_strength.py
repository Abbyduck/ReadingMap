from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
from django.db.models import Q

import catalog.models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0008_animation_entity_type")]

    operations = [
        migrations.AddField(
            model_name="readinglistitem",
            name="recommendation_strength",
            field=catalog.models.UnsignedTinyIntegerField(
                blank=True,
                null=True,
                validators=[MinValueValidator(1), MaxValueValidator(3)],
            ),
        ),
        migrations.AddField(
            model_name="readinglistitem",
            name="recommendation_strength_text",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddConstraint(
            model_name="readinglistitem",
            constraint=models.CheckConstraint(
                condition=Q(recommendation_strength__isnull=True) | Q(recommendation_strength__in=[1, 2, 3]),
                name="reading_item_strength_valid",
            ),
        ),
    ]
