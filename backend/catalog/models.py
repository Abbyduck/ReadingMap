from __future__ import annotations

import re
import unicodedata

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import F, Q


ALLOWED_ENTITY_TYPES = frozenset({"book", "animation", "reading_system", "series", "level", "set"})
COLLECTION_ENTITY_TYPES = frozenset({"reading_system", "series", "level", "set"})
ENTITY_CHOICES = [
    ("book", "单本"),
    ("animation", "动画"),
    ("reading_system", "阅读产品线"),
    ("series", "系列"),
    ("level", "级别"),
    ("set", "组合"),
]
CATEGORY_TYPE_CHOICES = [
    ("material_type", "阅读材料"),
    ("genre", "内容类型"),
    ("theme", "主题"),
    ("topic", "题材"),
    ("reading_form", "阅读形式"),
]
ALLOWED_CATEGORY_TYPES = frozenset(value for value, _ in CATEGORY_TYPE_CHOICES)


def normalize_search_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    text = re.sub(r"\s*&\s*", " and ", text)
    return " ".join(re.sub(r"[^\w\u3400-\u9fff]+", " ", text, flags=re.UNICODE).split())


def build_catalog_search_text(entity) -> str:
    values = [entity.display_title, entity.title_zh, entity.title_en, *(entity.aliases or [])]
    return "\n".join(dict.fromkeys(normalize_search_text(v) for v in values if normalize_search_text(v)))


class TimestampModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CatalogEntity(TimestampModel):
    entity_type = models.CharField(max_length=50, choices=ENTITY_CHOICES, db_index=True)
    display_title = models.CharField(max_length=500)
    title_zh = models.CharField(max_length=500, null=True, blank=True)
    title_en = models.CharField(max_length=500, null=True, blank=True)
    aliases = models.JSONField(null=True, blank=True)
    search_text = models.TextField(blank=True, editable=False)
    description = models.TextField(null=True, blank=True)
    extra_info = models.TextField(null=True, blank=True)
    cover_url = models.URLField(max_length=1000, null=True, blank=True)
    cover_local_path = models.CharField(max_length=1000, null=True, blank=True)
    detail_images = models.JSONField(null=True, blank=True)
    independent_reading_suitable = models.BooleanField(null=True, blank=True)
    bookshelf_visible = models.BooleanField(default=False)

    class Meta:
        db_table = "catalog_entities"
        ordering = ["-id"]
        constraints = [models.CheckConstraint(condition=Q(entity_type__in=sorted(ALLOWED_ENTITY_TYPES)), name="catalog_entity_type_valid")]

    def __str__(self):
        return self.display_title

    def clean(self):
        super().clean()
        if not self.display_title or not self.display_title.strip():
            raise ValidationError({"display_title": "标题不能为空。"})
        if self.aliases is not None and (not isinstance(self.aliases, list) or any(not isinstance(v, str) for v in self.aliases)):
            raise ValidationError({"aliases": "别名必须是字符串列表。"})
        if self.detail_images is not None and not isinstance(self.detail_images, list):
            raise ValidationError({"detail_images": "详情图片必须是列表。"})
        if self.pk:
            old_type = type(self).objects.filter(pk=self.pk).values_list("entity_type", flat=True).first()
            if old_type and old_type != self.entity_type:
                raise ValidationError({"entity_type": "已创建实体不能直接更改类型，请创建正确类型后通过审核关联。"})

    def save(self, *args, **kwargs):
        self.full_clean()
        self.search_text = build_catalog_search_text(self)
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"search_text", "updated_at"}
        with transaction.atomic():
            super().save(*args, **kwargs)
            if self.entity_type == "book":
                Work.objects.get_or_create(catalog_entity_id=self.pk)
            elif self.entity_type in COLLECTION_ENTITY_TYPES:
                Collection.objects.get_or_create(catalog_entity_id=self.pk)


class Work(TimestampModel):
    catalog_entity = models.OneToOneField(CatalogEntity, primary_key=True, related_name="work", on_delete=models.CASCADE)
    author_text = models.CharField(max_length=1000, null=True, blank=True)
    illustrator_text = models.CharField(max_length=1000, null=True, blank=True)
    language_code = models.CharField(max_length=50, null=True, blank=True)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    word_count = models.PositiveIntegerField(null=True, blank=True)
    headword_count = models.PositiveIntegerField(null=True, blank=True)
    ar_level = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    lexile_code = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        db_table = "works"

    def __str__(self):
        return str(self.catalog_entity)

    def clean(self):
        if self.catalog_entity_id and self.catalog_entity.entity_type != "book":
            raise ValidationError({"catalog_entity": "只有 book 类型可包含图书事实字段。"})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class CatalogIsbn(models.Model):
    work_entity = models.ForeignKey(Work, related_name="isbns", on_delete=models.CASCADE)
    isbn_type = models.PositiveSmallIntegerField(choices=[(10, "ISBN-10"), (13, "ISBN-13")])
    isbn_val = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "catalog_isbns"
        constraints = [models.UniqueConstraint(fields=["isbn_type", "isbn_val"], name="uq_catalog_isbn"), models.CheckConstraint(condition=Q(isbn_type__in=[10, 13]), name="chk_catalog_isbn_type")]

    def __str__(self):
        return self.isbn_val

    def clean(self):
        from .services import normalize_isbn
        kind, value = normalize_isbn(self.isbn_val)
        if kind is None or kind != self.isbn_type:
            raise ValidationError({"isbn_val": "ISBN 格式或位数与类型不符。"})
        self.isbn_val = value

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Collection(TimestampModel):
    catalog_entity = models.OneToOneField(CatalogEntity, primary_key=True, related_name="collection", on_delete=models.CASCADE)
    volume_count = models.PositiveIntegerField(null=True, blank=True)
    # Collection difficulty is derived from its direct members.  Keep numeric
    # bounds for filtering/sorting; member Work rows retain the exact Lexile
    # code (for example BR80L or AD200L).
    lexile_min = models.PositiveSmallIntegerField(null=True, blank=True)
    lexile_max = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        db_table = "collections"
        constraints = [
            models.CheckConstraint(
                condition=Q(lexile_min__isnull=True) | Q(lexile_max__isnull=True) | Q(lexile_min__lte=F("lexile_max")),
                name="collection_lexile_range_order",
            ),
        ]

    def __str__(self):
        return str(self.catalog_entity)

    def clean(self):
        if self.catalog_entity_id and self.catalog_entity.entity_type not in COLLECTION_ENTITY_TYPES:
            raise ValidationError({"catalog_entity": "只有阅读产品线、系列、级别、组合可包含集合结构。"})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class CollectionItem(models.Model):
    collection = models.ForeignKey(Collection, related_name="items", on_delete=models.CASCADE)
    member_entity = models.ForeignKey(CatalogEntity, related_name="collection_memberships", on_delete=models.CASCADE)
    position = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "collection_items"
        ordering = [F("position").asc(nulls_last=True), "id"]
        constraints = [models.UniqueConstraint(fields=["collection", "member_entity"], name="uq_collection_member"), models.CheckConstraint(condition=~Q(collection=F("member_entity")), name="collection_not_self")]

    def clean(self):
        from .services import validate_collection_membership
        if self.collection_id and self.member_entity_id:
            validate_collection_membership(self.collection_id, self.member_entity_id)

    def save(self, *args, **kwargs):
        from .services import lock_collection_graph
        with transaction.atomic():
            lock_collection_graph()
            self.full_clean()
            super().save(*args, **kwargs)


class ReadingPenModel(TimestampModel):
    name = models.CharField(max_length=255)
    normalized_name = models.CharField(max_length=255, unique=True)

    class Meta:
        db_table = "reading_pen_models"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.normalized_name = normalize_search_text(self.name)
        super().save(*args, **kwargs)


class CatalogEntityReadingPen(models.Model):
    catalog_entity = models.ForeignKey(CatalogEntity, related_name="reading_pens", on_delete=models.CASCADE)
    reading_pen_model = models.ForeignKey(ReadingPenModel, related_name="catalog_entities", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "catalog_entity_reading_pens"
        constraints = [models.UniqueConstraint(fields=["catalog_entity", "reading_pen_model"], name="uq_entity_reading_pen")]

    @property
    def reading_pen(self):
        return self.reading_pen_model


class ReadingListCreator(TimestampModel):
    name = models.CharField(max_length=255)
    tagline = models.CharField(max_length=500, null=True, blank=True)
    background = models.TextField(null=True, blank=True)
    signature_focus = models.TextField(null=True, blank=True)
    avatar_url = models.URLField(max_length=1000, null=True, blank=True)

    class Meta:
        db_table = "reading_list_creators"
        ordering = ["name", "id"]

    def __str__(self):
        return self.name


def validate_age_range(instance, low, high):
    lower, upper = getattr(instance, low), getattr(instance, high)
    if lower is not None and upper is not None and lower > upper:
        raise ValidationError({high: "年龄上限不能小于下限。"})


class UnsignedTinyIntegerField(models.PositiveSmallIntegerField):
    """Use the specification's TINYINT UNSIGNED on MySQL."""

    def db_type(self, connection):
        return "tinyint unsigned" if connection.vendor == "mysql" else super().db_type(connection)


class ReadingList(TimestampModel):
    creator = models.ForeignKey(ReadingListCreator, related_name="reading_lists", on_delete=models.CASCADE)
    title = models.CharField(max_length=500)
    age_min_months = models.PositiveSmallIntegerField(null=True, blank=True)
    age_max_months = models.PositiveSmallIntegerField(null=True, blank=True)
    stage_label = models.CharField(max_length=255, null=True, blank=True)
    material_type = models.CharField(max_length=50, null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "reading_lists"
        ordering = ["-id"]
        constraints = [models.CheckConstraint(condition=Q(age_min_months__isnull=True) | Q(age_max_months__isnull=True) | Q(age_min_months__lte=F("age_max_months")), name="reading_list_age_order")]

    def __str__(self):
        return self.title

    def clean(self):
        validate_age_range(self, "age_min_months", "age_max_months")


class ReadingListItem(TimestampModel):
    reading_list = models.ForeignKey(ReadingList, related_name="items", on_delete=models.CASCADE)
    catalog_entity = models.ForeignKey(CatalogEntity, related_name="reading_list_items", on_delete=models.CASCADE)
    position = models.PositiveIntegerField(null=True, blank=True)
    sub_position = models.PositiveSmallIntegerField(null=True, blank=True)
    stage_label = models.CharField(max_length=255, null=True, blank=True)
    recommended_age_min_months = models.PositiveSmallIntegerField(null=True, blank=True)
    recommended_age_max_months = models.PositiveSmallIntegerField(null=True, blank=True)
    source_ar_text = models.CharField(max_length=100, null=True, blank=True)
    source_lexile_text = models.CharField(max_length=100, null=True, blank=True)
    source_level_text = models.CharField(max_length=255, null=True, blank=True)
    is_strong_recommendation = models.BooleanField(default=False)
    recommendation_emphasis_text = models.CharField(max_length=255, null=True, blank=True)
    comment = models.TextField(null=True, blank=True)
    note = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "reading_list_items"
        ordering = [F("position").asc(nulls_last=True), F("sub_position").asc(nulls_last=True), "id"]
        constraints = [
            models.CheckConstraint(condition=Q(recommended_age_min_months__isnull=True) | Q(recommended_age_max_months__isnull=True) | Q(recommended_age_min_months__lte=F("recommended_age_max_months")), name="reading_item_age_order"),
        ]

    def clean(self):
        validate_age_range(self, "recommended_age_min_months", "recommended_age_max_months")


class CatalogCategory(TimestampModel):
    parent = models.ForeignKey("self", null=True, blank=True, related_name="children", on_delete=models.SET_NULL)
    category_type = models.CharField(max_length=50, choices=CATEGORY_TYPE_CHOICES)
    code = models.CharField(max_length=100)
    name_zh = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100, null=True, blank=True)
    description = models.CharField(max_length=500, null=True, blank=True)
    sort_order = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "catalog_categories"
        ordering = ["category_type", "sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["category_type", "code"], name="uq_category_code"),
            models.CheckConstraint(condition=Q(category_type__in=[value for value, _ in CATEGORY_TYPE_CHOICES]), name="catalog_category_type_valid"),
        ]

    def __str__(self):
        return self.name_zh

    def clean(self):
        if self.category_type not in ALLOWED_CATEGORY_TYPES:
            raise ValidationError({"category_type": "分类维度不在受控词表中。"})
        if self.parent_id:
            if self.parent.category_type != self.category_type:
                raise ValidationError({"parent": "父分类必须属于同一个分类维度。"})
            if self.parent.parent_id:
                raise ValidationError({"parent": "分类最多允许两层。"})
        current = self.parent
        seen = {self.pk} if self.pk else set()
        while current:
            if current.pk in seen:
                raise ValidationError({"parent": "分类不能形成循环。"})
            seen.add(current.pk)
            current = current.parent


class CatalogEntityCategory(models.Model):
    catalog_entity = models.ForeignKey(CatalogEntity, related_name="categories", on_delete=models.CASCADE)
    category = models.ForeignKey(CatalogCategory, related_name="entities", on_delete=models.CASCADE)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "catalog_entity_categories"
        constraints = [models.UniqueConstraint(fields=["catalog_entity", "category"], name="uq_entity_category")]


def score_field():
    return models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(10)])


def score_constraints(prefix, fields):
    return [models.CheckConstraint(condition=Q(**{field + "__isnull": True}) | (Q(**{field + "__gte": 0}) & Q(**{field + "__lte": 10})), name=f"{prefix}_{idx}_range") for idx, field in enumerate(fields)]


class WorkDifficultyProfile(TimestampModel):
    work_entity = models.OneToOneField(Work, primary_key=True, related_name="difficulty_profile", on_delete=models.CASCADE)
    language_complexity_score = score_field()
    syntax_complexity_score = score_field()
    cognitive_load_score = score_field()
    language_detail = models.JSONField(null=True, blank=True)
    syntax_detail = models.JSONField(null=True, blank=True)
    cognitive_detail = models.JSONField(null=True, blank=True)
    analysis_version = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        db_table = "work_difficulty_profiles"
        constraints = score_constraints("difficulty", ["language_complexity_score", "syntax_complexity_score", "cognitive_load_score"])


class WorkAbilityRequirement(TimestampModel):
    work_entity = models.OneToOneField(Work, primary_key=True, related_name="ability_requirement", on_delete=models.CASCADE)
    language_requirement_score = score_field()
    syntax_requirement_score = score_field()
    cognitive_requirement_score = score_field()
    requirement_detail = models.JSONField(null=True, blank=True)
    model_version = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        db_table = "work_ability_requirements"
        constraints = score_constraints("requirement", ["language_requirement_score", "syntax_requirement_score", "cognitive_requirement_score"])


class ChildProfile(TimestampModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="children", on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    birth_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "child_profiles"
        ordering = ["id"]

    def __str__(self):
        return self.name


class ChildAbilityProfile(TimestampModel):
    child = models.ForeignKey(ChildProfile, related_name="ability_profiles", on_delete=models.CASCADE)
    language_code = models.CharField(max_length=50)
    language_score = score_field()
    syntax_score = score_field()
    cognitive_score = score_field()

    class Meta:
        db_table = "child_ability_profiles"
        constraints = [models.UniqueConstraint(fields=["child", "language_code"], name="uq_child_language")] + score_constraints("child_ability", ["language_score", "syntax_score", "cognitive_score"])


class ChildEntityAnnotation(TimestampModel):
    child = models.ForeignKey(ChildProfile, related_name="entity_annotations", on_delete=models.CASCADE)
    catalog_entity = models.ForeignKey(CatalogEntity, related_name="child_annotations", on_delete=models.CASCADE)
    independent_reading_override = models.BooleanField(null=True, blank=True)
    retry_after_date = models.DateField(null=True, blank=True)
    note = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "child_entity_annotations"
        constraints = [models.UniqueConstraint(fields=["child", "catalog_entity"], name="uq_child_entity")]


class CatalogSourceStat(TimestampModel):
    catalog_entity = models.ForeignKey(CatalogEntity, related_name="source_stats", on_delete=models.CASCADE)
    source_name = models.CharField(max_length=50)
    external_id = models.CharField(max_length=255, null=True, blank=True)
    rating = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    rating_max = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    rating_count = models.PositiveIntegerField(null=True, blank=True)
    review_count = models.PositiveIntegerField(null=True, blank=True)
    source_url = models.URLField(max_length=1000, null=True, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "catalog_source_stats"
        constraints = [models.UniqueConstraint(fields=["source_name", "external_id"], name="uq_catalog_source_external")]


class CatalogGraphLock(models.Model):
    """A shared row serializes collection edges, including previously disjoint graphs."""

    key = models.CharField(max_length=50, primary_key=True)

    class Meta:
        db_table = "catalog_graph_locks"
