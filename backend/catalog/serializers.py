from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from . import models as m
from .services import create_catalog_entity


class CleanModelSerializer(serializers.ModelSerializer):
    """DRF and Admin share model validation, including cross-field constraints."""

    def validate(self, attrs):
        values = {}
        if self.instance:
            values = {field.attname: getattr(self.instance, field.attname) for field in self.Meta.model._meta.concrete_fields}
        values.update(attrs)
        instance = self.Meta.model(**values)
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        return attrs


class WorkSerializer(CleanModelSerializer):
    page_count = serializers.SerializerMethodField()

    def get_page_count(self, obj):
        edition = next(iter(obj.editions.all()), None) if obj.pk else None
        return edition.page_count if edition else None

    class Meta:
        model = m.Work
        fields = ["author_text", "illustrator_text", "translator_text", "language_code", "detail_images", "page_count", "word_count", "headword_count", "ar_level", "lexile_code"]


class CategorySerializer(CleanModelSerializer):
    parent_id = serializers.PrimaryKeyRelatedField(source="parent", queryset=m.CatalogCategory.objects.all(), allow_null=True, required=False)

    class Meta:
        model = m.CatalogCategory
        fields = ["id", "parent_id", "category_type", "code", "name_zh", "name_en", "description", "sort_order"]


class IsbnSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.CatalogIsbn
        fields = ["id", "isbn_type", "isbn_val"]


class BookEditionSerializer(CleanModelSerializer):
    isbns = IsbnSerializer(many=True, read_only=True)

    class Meta:
        model = m.BookEdition
        fields = ["id", "work_id", "cover_local_path", "publisher", "format", "page_count", "publication_date", "dimensions", "isbns"]
        read_only_fields = ["id", "work_id"]


class CatalogEntitySerializer(serializers.ModelSerializer):
    work = WorkSerializer(read_only=True, allow_null=True)
    editions = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    volume_count = serializers.SerializerMethodField()
    lexile_min = serializers.SerializerMethodField()
    lexile_max = serializers.SerializerMethodField()
    isbns = serializers.SerializerMethodField()
    categories = serializers.SerializerMethodField()
    reading_pens = serializers.SerializerMethodField()
    parents = serializers.SerializerMethodField()
    members = serializers.SerializerMethodField()

    class Meta:
        model = m.CatalogEntity
        fields = ["id", "entity_type", "display_title", "title_zh", "title_en", "aliases", "description", "extra_info", "guide_markdown", "fiction_type", "cover_url", "independent_reading_suitable", "bookshelf_visible", "work", "editions", "volume_count", "lexile_min", "lexile_max", "isbns", "categories", "reading_pens", "parents", "members"]

    def get_editions(self, obj):
        work = getattr(obj, "work", None)
        return BookEditionSerializer(work.editions.all(), many=True).data if work else []

    def get_cover_url(self, obj):
        # Compatibility for existing public views; admin uses Edition covers.
        return obj.cover_url

    def get_volume_count(self, obj):
        collection = getattr(obj, "collection", None)
        return collection.volume_count if collection else None

    def get_lexile_min(self, obj):
        collection = getattr(obj, "collection", None)
        return collection.lexile_min if collection else None

    def get_lexile_max(self, obj):
        collection = getattr(obj, "collection", None)
        return collection.lexile_max if collection else None

    def get_isbns(self, obj):
        work = getattr(obj, "work", None)
        return IsbnSerializer([isbn for edition in work.editions.all() for isbn in edition.isbns.all()], many=True).data if work else []

    def get_categories(self, obj):
        return [{**CategorySerializer(link.category).data, "is_primary": link.is_primary} for link in obj.categories.all()]

    def get_reading_pens(self, obj):
        return [{"id": link.reading_pen_model_id, "name": link.reading_pen_model.name} for link in obj.reading_pens.all()]

    def get_parents(self, obj):
        return [{"id": row.collection_id, "display_title": row.collection.catalog_entity.display_title, "position": row.position}
                for row in obj.collection_memberships.select_related("collection__catalog_entity")]

    def get_members(self, obj):
        collection = getattr(obj, "collection", None)
        return [{"id": row.member_entity_id, "display_title": row.member_entity.display_title, "position": row.position}
                for row in collection.items.select_related("member_entity")] if collection else []


class CatalogEntityCreateSerializer(CleanModelSerializer):
    work = WorkSerializer(required=False, allow_null=True)
    volume_count = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    lexile_min = serializers.IntegerField(min_value=0, required=False, allow_null=True, write_only=True)
    lexile_max = serializers.IntegerField(min_value=0, required=False, allow_null=True, write_only=True)
    aliases = serializers.ListField(child=serializers.CharField(max_length=500), required=False, allow_null=True)

    class Meta:
        model = m.CatalogEntity
        fields = ["entity_type", "display_title", "title_zh", "title_en", "aliases", "description", "extra_info", "guide_markdown", "fiction_type", "independent_reading_suitable", "bookshelf_visible", "work", "volume_count", "lexile_min", "lexile_max"]

    def validate(self, attrs):
        if attrs.get("work") is not None and attrs.get("entity_type") != "book":
            raise serializers.ValidationError({"work": "只有图书可包含 Work 字段。"})
        if attrs.get("volume_count") is not None and attrs.get("entity_type") not in m.COLLECTION_ENTITY_TYPES:
            raise serializers.ValidationError({"volume_count": "只有集合类型可包含册数。"})
        if (attrs.get("lexile_min") is not None or attrs.get("lexile_max") is not None) and attrs.get("entity_type") not in m.COLLECTION_ENTITY_TYPES:
            raise serializers.ValidationError({"lexile_min": "只有集合类型可包含 Lexile 范围。"})
        if attrs.get("lexile_min") is not None and attrs.get("lexile_max") is not None and attrs["lexile_min"] > attrs["lexile_max"]:
            raise serializers.ValidationError({"lexile_max": "Lexile 上限不能小于下限。"})
        return attrs

    def create(self, validated_data):
        return create_catalog_entity(**validated_data)


class CatalogEntityBookshelfSerializer(serializers.Serializer):
    bookshelf_visible = serializers.BooleanField()


class CatalogEntityEditSerializer(serializers.Serializer):
    display_title = serializers.CharField(max_length=500, required=False)
    title_zh = serializers.CharField(max_length=500, allow_blank=True, allow_null=True, required=False)
    title_en = serializers.CharField(max_length=500, allow_blank=True, allow_null=True, required=False)
    aliases = serializers.ListField(child=serializers.CharField(max_length=500), allow_null=True, required=False)
    description = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    extra_info = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    guide_markdown = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    fiction_type = serializers.ChoiceField(choices=m.FICTION_TYPE_CHOICES, required=False)
    independent_reading_suitable = serializers.BooleanField(allow_null=True, required=False)
    bookshelf_visible = serializers.BooleanField(required=False)
    work = WorkSerializer(required=False)
    volume_count = serializers.IntegerField(min_value=0, allow_null=True, required=False)
    category_decisions = serializers.ListField(child=serializers.DictField(), required=False)


class CreatorSerializer(CleanModelSerializer):
    class Meta:
        model = m.ReadingListCreator
        fields = ["id", "name", "tagline", "background", "signature_focus", "avatar_url"]


class ReadingListItemSerializer(CleanModelSerializer):
    catalog_entity_id = serializers.PrimaryKeyRelatedField(source="catalog_entity", queryset=m.CatalogEntity.objects.all())
    recommended_edition_id = serializers.PrimaryKeyRelatedField(source="recommended_edition", queryset=m.BookEdition.objects.all(), allow_null=True, required=False)
    entity = CatalogEntitySerializer(source="catalog_entity", read_only=True)

    class Meta:
        model = m.ReadingListItem
        fields = ["id", "catalog_entity_id", "recommended_edition_id", "position", "sub_position", "stage_label", "recommended_age_min_months", "recommended_age_max_months", "source_ar_text", "source_lexile_text", "source_level_text", "is_strong_recommendation", "recommendation_emphasis_text", "comment", "note", "entity"]


class ReadingListSerializer(CleanModelSerializer):
    creator_id = serializers.PrimaryKeyRelatedField(source="creator", queryset=m.ReadingListCreator.objects.all())
    creator_name = serializers.CharField(source="creator.name", read_only=True)
    items = ReadingListItemSerializer(many=True, read_only=True)

    class Meta:
        model = m.ReadingList
        fields = ["id", "creator_id", "creator_name", "title", "age_min_months", "age_max_months", "stage_label", "material_type", "description", "items"]


class CollectionItemSerializer(serializers.Serializer):
    member_entity_id = serializers.PrimaryKeyRelatedField(queryset=m.CatalogEntity.objects.all())
    position = serializers.IntegerField(min_value=0, required=False, default=None, allow_null=True)


class EntityCategorySerializer(serializers.Serializer):
    category_id = serializers.PrimaryKeyRelatedField(queryset=m.CatalogCategory.objects.all())
    is_primary = serializers.BooleanField(default=False)


class DifficultyProfileSerializer(CleanModelSerializer):
    work_entity_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = m.WorkDifficultyProfile
        fields = ["work_entity_id", "language_complexity_score", "syntax_complexity_score", "cognitive_load_score", "language_detail", "syntax_detail", "cognitive_detail", "analysis_version"]


class AbilityRequirementSerializer(CleanModelSerializer):
    work_entity_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = m.WorkAbilityRequirement
        fields = ["work_entity_id", "language_requirement_score", "syntax_requirement_score", "cognitive_requirement_score", "requirement_detail", "model_version"]


class ChildSerializer(CleanModelSerializer):
    class Meta:
        model = m.ChildProfile
        fields = ["id", "name", "birth_date"]


class ChildAbilitySerializer(CleanModelSerializer):
    child_id = serializers.IntegerField(read_only=True)
    language_code = serializers.CharField(read_only=True)

    class Meta:
        model = m.ChildAbilityProfile
        fields = ["child_id", "language_code", "language_score", "syntax_score", "cognitive_score"]


class ChildAnnotationSerializer(CleanModelSerializer):
    child_id = serializers.IntegerField(read_only=True)
    catalog_entity_id = serializers.IntegerField(read_only=True)
    effective_independent_reading = serializers.SerializerMethodField()
    effective_source = serializers.SerializerMethodField()
    entity = CatalogEntitySerializer(source="catalog_entity", read_only=True)

    class Meta:
        model = m.ChildEntityAnnotation
        fields = ["child_id", "catalog_entity_id", "independent_reading_override", "retry_after_date", "note", "effective_independent_reading", "effective_source", "entity"]

    def get_effective_independent_reading(self, obj):
        if obj.independent_reading_override is not None:
            return obj.independent_reading_override
        return obj.catalog_entity.independent_reading_suitable

    def get_effective_source(self, obj):
        return "child_override" if obj.independent_reading_override is not None else "catalog"


class SourceStatSerializer(CleanModelSerializer):
    catalog_entity_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = m.CatalogSourceStat
        fields = ["id", "catalog_entity_id", "source_name", "external_id", "rating", "rating_max", "rating_count", "review_count", "source_url", "fetched_at"]
