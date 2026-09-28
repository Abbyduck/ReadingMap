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
    class Meta:
        model = m.Work
        fields = ["author_text", "illustrator_text", "language_code", "page_count", "word_count", "headword_count", "ar_level", "lexile_code"]


class CategorySerializer(CleanModelSerializer):
    parent_id = serializers.PrimaryKeyRelatedField(source="parent", queryset=m.CatalogCategory.objects.all(), allow_null=True, required=False)

    class Meta:
        model = m.CatalogCategory
        fields = ["id", "parent_id", "category_type", "code", "name_zh", "name_en", "description", "sort_order"]


class IsbnSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.CatalogIsbn
        fields = ["id", "isbn_type", "isbn_val"]


class CatalogEntitySerializer(serializers.ModelSerializer):
    work = WorkSerializer(read_only=True, allow_null=True)
    volume_count = serializers.SerializerMethodField()
    lexile_min = serializers.SerializerMethodField()
    lexile_max = serializers.SerializerMethodField()
    isbns = serializers.SerializerMethodField()
    categories = serializers.SerializerMethodField()
    reading_pens = serializers.SerializerMethodField()

    class Meta:
        model = m.CatalogEntity
        fields = ["id", "entity_type", "display_title", "title_zh", "title_en", "aliases", "description", "extra_info", "cover_url", "cover_local_path", "detail_images", "independent_reading_suitable", "bookshelf_visible", "work", "volume_count", "lexile_min", "lexile_max", "isbns", "categories", "reading_pens"]

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
        return IsbnSerializer(work.isbns.all(), many=True).data if work else []

    def get_categories(self, obj):
        return CategorySerializer([link.category for link in obj.categories.all()], many=True).data

    def get_reading_pens(self, obj):
        return [{"id": link.reading_pen_model_id, "name": link.reading_pen_model.name} for link in obj.reading_pens.all()]


class CatalogEntityCreateSerializer(CleanModelSerializer):
    work = WorkSerializer(required=False, allow_null=True)
    volume_count = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    lexile_min = serializers.IntegerField(min_value=0, required=False, allow_null=True, write_only=True)
    lexile_max = serializers.IntegerField(min_value=0, required=False, allow_null=True, write_only=True)
    aliases = serializers.ListField(child=serializers.CharField(max_length=500), required=False, allow_null=True)

    class Meta:
        model = m.CatalogEntity
        fields = ["entity_type", "display_title", "title_zh", "title_en", "aliases", "description", "extra_info", "cover_url", "cover_local_path", "detail_images", "independent_reading_suitable", "bookshelf_visible", "work", "volume_count", "lexile_min", "lexile_max"]

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


class CreatorSerializer(CleanModelSerializer):
    class Meta:
        model = m.ReadingListCreator
        fields = ["id", "name", "tagline", "background", "signature_focus", "avatar_url"]


class ReadingListItemSerializer(CleanModelSerializer):
    catalog_entity_id = serializers.PrimaryKeyRelatedField(source="catalog_entity", queryset=m.CatalogEntity.objects.all())
    entity = CatalogEntitySerializer(source="catalog_entity", read_only=True)

    class Meta:
        model = m.ReadingListItem
        fields = ["id", "catalog_entity_id", "position", "sub_position", "stage_label", "recommended_age_min_months", "recommended_age_max_months", "source_ar_text", "source_lexile_text", "source_level_text", "is_strong_recommendation", "recommendation_emphasis_text", "comment", "note", "entity"]


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
