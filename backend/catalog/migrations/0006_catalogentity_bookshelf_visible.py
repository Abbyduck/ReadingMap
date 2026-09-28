from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0005_collection_lexile_range")]

    operations = [
        migrations.AddField(
            model_name="catalogentity",
            name="bookshelf_visible",
            field=models.BooleanField(default=False),
        ),
    ]
