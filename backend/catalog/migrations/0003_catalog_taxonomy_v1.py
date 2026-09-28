from django.db import migrations, models
from django.db.models import Q


CATEGORIES = {
    "material_type": [
        ("picture_book", "绘本", "Picture Book", None),
        ("graded_reader", "分级读物", "Graded Reader", None),
        ("early_reader", "初级自主阅读", "Early Reader", None),
        ("chapter_book", "章节书", "Chapter Book", None),
        ("comic", "漫画", "Comic", None),
        ("reference", "百科 / 工具类", "Reference", None),
        ("poetry", "诗歌 / 童谣", "Poetry / Nursery Rhyme", None),
    ],
    "genre": [
        ("fiction", "虚构", "Fiction", None),
        ("nonfiction", "非虚构", "Nonfiction", None),
        ("adventure", "冒险", "Adventure", None),
        ("fantasy", "奇幻", "Fantasy", None),
        ("humor", "幽默", "Humor", None),
        ("mystery", "悬疑 / 解谜", "Mystery", None),
        ("biography", "传记", "Biography", None),
        ("poetry_rhyme", "诗歌 / 韵文", "Poetry / Rhyme", None),
    ],
    "theme": [
        ("daily_life", "日常生活", "Daily Life", None),
        ("family", "家庭", "Family", None),
        ("friendship", "友情", "Friendship", None),
        ("school", "学校", "School", None),
        ("growth", "成长", "Growth", None),
        ("courage", "勇气", "Courage", None),
        ("emotion", "情绪", "Emotion", None),
        ("social_relationship", "人际关系", "Social Relationship", None),
        ("problem_solving", "解决问题", "Problem Solving", None),
        ("independence", "独立", "Independence", None),
        ("sharing", "分享", "Sharing", None),
        ("cooperation", "合作", "Cooperation", None),
        ("fear", "害怕", "Fear", "emotion"),
        ("anger", "愤怒", "Anger", "emotion"),
        ("sadness", "悲伤", "Sadness", "emotion"),
        ("jealousy", "嫉妒", "Jealousy", "emotion"),
        ("frustration", "挫败", "Frustration", "emotion"),
        ("separation_anxiety", "分离焦虑", "Separation Anxiety", "emotion"),
        ("confidence", "自信", "Confidence", "emotion"),
        ("empathy", "同理心", "Empathy", "emotion"),
        ("embarrassment", "尴尬 / 羞怯", "Embarrassment", "emotion"),
        ("grief", "失落 / 哀伤", "Grief", "emotion"),
    ],
    "topic": [
        ("animals", "动物", "Animals", None),
        ("dinosaurs", "恐龙", "Dinosaurs", None),
        ("pets", "宠物", "Pets", "animals"),
        ("insects", "昆虫", "Insects", "animals"),
        ("ocean_animals", "海洋动物", "Ocean Animals", "animals"),
        ("plants", "植物", "Plants", None),
        ("nature", "自然", "Nature", None),
        ("weather", "天气", "Weather", None),
        ("vehicles", "交通工具", "Vehicles", None),
        ("robots", "机器人", "Robots", None),
        ("machines", "机械", "Machines", None),
        ("body", "身体", "Body", None),
        ("health", "健康", "Health", None),
        ("space", "太空", "Space", None),
        ("earth", "地球", "Earth", None),
        ("science", "科学", "Science", None),
        ("math", "数学", "Math", None),
        ("arts_music", "艺术 / 音乐", "Arts / Music", None),
        ("food", "食物", "Food", None),
        ("sports", "运动", "Sports", None),
        ("holidays", "节日", "Holidays", None),
    ],
    "reading_form": [
        ("repetitive_pattern", "重复 / 可预测句型", "Repetitive / Predictable Pattern", None),
        ("rhyme_rhythm", "押韵 / 强韵律", "Rhyme / Strong Rhythm", None),
        ("interactive", "互动式", "Interactive", None),
        ("wordless", "无字 / 极少文字", "Wordless / Minimal Text", None),
        ("cumulative", "累积式结构", "Cumulative", None),
    ],
}


def seed_taxonomy(apps, schema_editor):
    Category = apps.get_model("catalog", "CatalogCategory")
    rows = {}
    for category_type, categories in CATEGORIES.items():
        for sort_order, (code, name_zh, name_en, _parent_code) in enumerate(categories, 1):
            row, _ = Category.objects.update_or_create(
                category_type=category_type,
                code=code,
                defaults={"name_zh": name_zh, "name_en": name_en, "sort_order": sort_order},
            )
            rows[(category_type, code)] = row
    for category_type, categories in CATEGORIES.items():
        for code, _name_zh, _name_en, parent_code in categories:
            if parent_code:
                row = rows[(category_type, code)]
                row.parent_id = rows[(category_type, parent_code)].pk
                row.save(update_fields=["parent_id"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0002_catalogentity_extra_info_detail_images")]

    operations = [
        migrations.AlterField(
            model_name="catalogcategory",
            name="category_type",
            field=models.CharField(
                choices=[
                    ("material_type", "阅读材料"),
                    ("genre", "内容类型"),
                    ("theme", "主题"),
                    ("topic", "题材"),
                    ("reading_form", "阅读形式"),
                ],
                max_length=50,
            ),
        ),
        migrations.AddConstraint(
            model_name="catalogcategory",
            constraint=models.CheckConstraint(
                condition=Q(category_type__in=["material_type", "genre", "theme", "topic", "reading_form"]),
                name="catalog_category_type_valid",
            ),
        ),
        migrations.RunPython(seed_taxonomy, migrations.RunPython.noop),
    ]
