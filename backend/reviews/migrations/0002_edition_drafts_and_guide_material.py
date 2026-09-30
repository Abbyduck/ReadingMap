import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("reviews", "0001_initial"), ("catalog", "0011_book_editions_and_admin_identity")]

    operations = [
        migrations.AddField(model_name="researchsource", name="raw_content", field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name="researchsubject", name="guide_markdown_draft", field=models.TextField(blank=True, null=True)),
        migrations.CreateModel(
            name="ReviewEditionDraft",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("proposed_data", models.JSONField(default=dict)),
                ("review_status", models.CharField(default="proposed", max_length=30)),
                ("book_subject", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="reviews.researchsubject")),
                ("matched_catalog_edition", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="catalog.bookedition")),
                ("review_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="edition_drafts", to="reviews.reviewitem")),
                ("source", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="reviews.researchsource")),
            ],
            options={"db_table": "review_edition_drafts"},
        ),
    ]
