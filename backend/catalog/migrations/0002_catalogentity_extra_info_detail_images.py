from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("catalog", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="catalogentity",
            name="extra_info",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="catalogentity",
            name="detail_images",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
