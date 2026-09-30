import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


def move_legacy_book_facts(apps, schema_editor):
    Work = apps.get_model("catalog", "Work")
    BookEdition = apps.get_model("catalog", "BookEdition")
    CatalogIsbn = apps.get_model("catalog", "CatalogIsbn")
    for work in Work.objects.select_related("catalog_entity").all().iterator():
        entity = work.catalog_entity
        isbns = CatalogIsbn.objects.filter(work_entity_id=work.pk)
        if entity.cover_local_path or entity.cover_url or work.page_count is not None or isbns.exists():
            edition = BookEdition.objects.create(
                work_id=work.pk,
                cover_local_path=entity.cover_local_path or None,
                page_count=work.page_count,
            )
            isbns.update(edition_id=edition.pk)
        if isinstance(entity.detail_images, list):
            paths = [row.get("local_path") if isinstance(row, dict) else row for row in entity.detail_images]
            work.detail_images = [path for path in paths if isinstance(path, str) and path and not path.casefold().startswith(("http://", "https://", "//", "data:"))]
            work.save(update_fields=["detail_images"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0010_recommendation_facts")]

    operations = [
        migrations.RemoveConstraint(model_name="catalogentity", name="catalog_entity_type_valid"),
        migrations.AddConstraint(
            model_name="catalogentity",
            constraint=models.CheckConstraint(
                condition=Q(entity_type__in=["animation", "book", "franchise", "level", "reading_system", "series", "set"]),
                name="catalog_entity_type_valid",
            ),
        ),
        migrations.AlterField(model_name="catalogentity", name="entity_type", field=models.CharField(
            choices=[("book", "单本"), ("animation", "动画"), ("reading_system", "阅读产品线"), ("series", "系列"), ("level", "级别"), ("set", "组合"), ("franchise", "IP")],
            db_index=True, max_length=50,
        )),
        migrations.AddField(model_name="catalogentity", name="guide_markdown", field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name="catalogentity", name="fiction_type", field=models.CharField(
            choices=[("unknown", "未知"), ("fiction", "虚构"), ("nonfiction", "非虚构"), ("mixed", "混合")], default="unknown", max_length=20,
        )),
        migrations.AlterField(model_name="catalogentity", name="cover_url", field=models.URLField(blank=True, editable=False, max_length=1000, null=True)),
        migrations.AlterField(model_name="catalogentity", name="cover_local_path", field=models.CharField(blank=True, editable=False, max_length=1000, null=True)),
        migrations.AlterField(model_name="catalogentity", name="detail_images", field=models.JSONField(blank=True, editable=False, null=True)),
        migrations.AddField(model_name="work", name="translator_text", field=models.CharField(blank=True, max_length=1000, null=True)),
        migrations.AddField(model_name="work", name="detail_images", field=models.JSONField(blank=True, null=True)),
        migrations.CreateModel(
            name="BookEdition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("cover_local_path", models.CharField(blank=True, max_length=1000, null=True)),
                ("publisher", models.CharField(blank=True, max_length=500, null=True)),
                ("format", models.CharField(blank=True, max_length=100, null=True)),
                ("page_count", models.PositiveIntegerField(blank=True, null=True)),
                ("publication_date", models.DateField(blank=True, null=True)),
                ("dimensions", models.CharField(blank=True, max_length=255, null=True)),
                ("work", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="editions", to="catalog.work")),
            ],
            options={"db_table": "book_editions"},
        ),
        migrations.AddField(model_name="catalogisbn", name="edition", field=models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="isbns", to="catalog.bookedition",
        )),
        migrations.AddField(model_name="readinglistitem", name="recommended_edition", field=models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="recommendations", to="catalog.bookedition",
        )),
        migrations.RunPython(move_legacy_book_facts, migrations.RunPython.noop),
        migrations.RemoveField(model_name="catalogisbn", name="work_entity"),
        migrations.AlterField(model_name="catalogisbn", name="edition", field=models.ForeignKey(
            on_delete=django.db.models.deletion.CASCADE, related_name="isbns", to="catalog.bookedition",
        )),
        migrations.RemoveField(model_name="work", name="page_count"),
    ]
