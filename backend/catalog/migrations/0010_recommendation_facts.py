from django.db import migrations, models


def copy_strong_facts(apps, schema_editor):
    ReadingListItem = apps.get_model("catalog", "ReadingListItem")
    ReviewItem = apps.get_model("reviews", "ReviewItem")
    for item in ReadingListItem.objects.filter(recommendation_strength=3).iterator():
        item.is_strong_recommendation = True
        item.recommendation_emphasis_text = item.recommendation_strength_text or None
        item.save(update_fields=["is_strong_recommendation", "recommendation_emphasis_text"])
    for review_item in ReviewItem.objects.exclude(committed_reading_list_item_id__isnull=True).iterator():
        raw = review_item.raw_payload if isinstance(review_item.raw_payload, dict) else {}
        extracted = raw.get("extracted") if isinstance(raw.get("extracted"), dict) else {}
        other = extracted.get("other_info") if isinstance(extracted.get("other_info"), dict) else {}
        stage = other.get("stage") if isinstance(other.get("stage"), dict) else {}
        stage_title = stage.get("title")
        if stage_title:
            ReadingListItem.objects.filter(pk=review_item.committed_reading_list_item_id, stage_label__isnull=True).update(stage_label=str(stage_title)[:255])


def restore_strong_facts(apps, schema_editor):
    ReadingListItem = apps.get_model("catalog", "ReadingListItem")
    for item in ReadingListItem.objects.filter(is_strong_recommendation=True).iterator():
        item.recommendation_strength = 3
        item.recommendation_strength_text = item.recommendation_emphasis_text
        item.save(update_fields=["recommendation_strength", "recommendation_strength_text"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0009_readinglistitem_recommendation_strength"), ("reviews", "0001_initial")]

    operations = [
        migrations.AddField(model_name="readinglistitem", name="is_strong_recommendation", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="readinglistitem", name="recommendation_emphasis_text", field=models.CharField(blank=True, max_length=255, null=True)),
        migrations.RunPython(copy_strong_facts, restore_strong_facts),
        migrations.RemoveConstraint(model_name="readinglistitem", name="reading_item_strength_valid"),
        migrations.RemoveField(model_name="readinglistitem", name="recommendation_strength"),
        migrations.RemoveField(model_name="readinglistitem", name="recommendation_strength_text"),
    ]
