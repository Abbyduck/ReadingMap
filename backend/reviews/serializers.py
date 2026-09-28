from rest_framework import serializers
from catalog.models import ALLOWED_ENTITY_TYPES, COLLECTION_ENTITY_TYPES
from .models import ResearchSubject, ReviewBatch, ReviewDataConflict


class ReviewBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewBatch
        fields = ["id", "source_type", "source_name", "source_file_path", "target_reading_list_id", "status", "total_items", "resolved_items", "created_at", "updated_at"]


class ReviewBatchImportSerializer(serializers.Serializer):
    source_file_path = serializers.CharField(max_length=1000)
    target_reading_list_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class ReviewItemSourceCopySerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    is_strong_recommendation = serializers.BooleanField(required=False)
    recommendation_emphasis_text = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    # Old open review tabs may still post the retired three-tier field. Translate
    # it at the API boundary; the catalog relation never stores that tier.
    recommendation_strength = serializers.ChoiceField(choices=[1, 2, 3], required=False, allow_null=True, write_only=True)
    recommendation_strength_text = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True, write_only=True)
    comment = serializers.CharField(max_length=5000, required=False, allow_null=True, allow_blank=True)
    note = serializers.CharField(max_length=5000, required=False, allow_null=True, allow_blank=True)

    def validate(self, attrs):
        legacy_strength = attrs.pop("recommendation_strength", serializers.empty)
        legacy_text = attrs.pop("recommendation_strength_text", serializers.empty)
        if legacy_strength is not serializers.empty and "is_strong_recommendation" not in attrs:
            attrs["is_strong_recommendation"] = legacy_strength == 3
        if legacy_text is not serializers.empty and "recommendation_emphasis_text" not in attrs:
            attrs["recommendation_emphasis_text"] = legacy_text
        editable = {"is_strong_recommendation", "recommendation_emphasis_text", "comment", "note"}
        if editable.isdisjoint(attrs):
            raise serializers.ValidationError("at least one recommendation field is required")
        return attrs


class ResearchSourceSerializer(serializers.Serializer):
    source_type = serializers.CharField(max_length=50, required=False, allow_null=True)
    source_url = serializers.URLField(max_length=1500)
    source_title = serializers.CharField(max_length=1000, required=False, allow_null=True, allow_blank=True)
    fetched_at = serializers.DateTimeField(required=False, allow_null=True)


class ResearchSubjectSerializer(serializers.ModelSerializer):
    proposed_entity_type = serializers.ChoiceField(choices=sorted(ALLOWED_ENTITY_TYPES), required=False, allow_null=True)
    proposed_display_title = serializers.CharField(max_length=500)
    proposed_aliases = serializers.ListField(child=serializers.CharField(max_length=500), required=False, allow_null=True)
    research_status = serializers.ChoiceField(choices=["pending", "researching", "ready", "partial", "failed"], required=False)
    review_item_id = serializers.IntegerField(min_value=1, required=False, allow_null=True, write_only=True)
    subject_role = serializers.ChoiceField(choices=["primary", "discovered_member", "discovered_parent", "related"], default="discovered_member", write_only=True)
    sources = ResearchSourceSerializer(many=True, required=False, write_only=True)

    class Meta:
        model = ResearchSubject
        fields = ["proposed_entity_type", "proposed_display_title", "proposed_title_zh", "proposed_title_en", "proposed_aliases", "facts_json", "ai_inferences_json", "research_status", "research_version", "review_item_id", "subject_role", "manual_note", "researched_at", "sources"]


CATALOG_DRAFT_FACT_KEYS = {
    "author", "illustrator", "publisher", "language", "page_count",
    "description", "official_age", "ar", "lexile", "lexile_min",
    "lexile_max", "cover",
}


class ResearchSubjectDraftSerializer(serializers.Serializer):
    """A conflict-safe patch for the human-editable Catalog Draft fields.

    ``facts_json`` intentionally is not accepted here.  The review UI sends
    only fields the human actually changed, so newer retailer/official facts
    cannot be replaced by an older browser snapshot.
    """

    expected_version = serializers.IntegerField(min_value=1)
    proposed_entity_type = serializers.ChoiceField(choices=sorted(ALLOWED_ENTITY_TYPES), required=False, allow_null=True)
    proposed_display_title = serializers.CharField(max_length=500, required=False)
    proposed_title_zh = serializers.CharField(max_length=500, required=False, allow_null=True, allow_blank=True)
    proposed_title_en = serializers.CharField(max_length=500, required=False, allow_null=True, allow_blank=True)
    proposed_aliases = serializers.ListField(child=serializers.CharField(max_length=500), required=False, allow_null=True)
    fact_values = serializers.DictField(child=serializers.JSONField(), required=False, default=dict)
    clear_fact_keys = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(CATALOG_DRAFT_FACT_KEYS)),
        required=False,
        default=list,
    )

    def validate_fact_values(self, values):
        unknown = sorted(set(values) - CATALOG_DRAFT_FACT_KEYS)
        if unknown:
            raise serializers.ValidationError(f"Unsupported Catalog Draft facts: {', '.join(unknown)}")
        empty = sorted(key for key, value in values.items() if value in (None, "", [], {}))
        if empty:
            raise serializers.ValidationError(f"Use clear_fact_keys to clear facts: {', '.join(empty)}")
        return values

    def validate(self, attrs):
        overlap = set(attrs.get("fact_values") or {}) & set(attrs.get("clear_fact_keys") or [])
        if overlap:
            raise serializers.ValidationError(f"A fact cannot be updated and cleared together: {', '.join(sorted(overlap))}")
        return attrs


class ProductImageSelectionSerializer(serializers.Serializer):
    selected_source_urls = serializers.ListField(
        child=serializers.URLField(max_length=2000), max_length=32,
    )
    cover_source_url = serializers.URLField(max_length=2000, required=False, allow_null=True)


class SelectedStructureResearchSerializer(serializers.Serializer):
    member_subject_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), min_length=1, max_length=500,
    )


class ParentStructureCreateSerializer(serializers.Serializer):
    child_subject_id = serializers.IntegerField(min_value=1)
    proposed_entity_type = serializers.ChoiceField(choices=sorted(COLLECTION_ENTITY_TYPES))
    proposed_display_title = serializers.CharField(max_length=500)
    proposed_title_zh = serializers.CharField(max_length=500, required=False, allow_null=True, allow_blank=True)
    proposed_title_en = serializers.CharField(max_length=500, required=False, allow_null=True, allow_blank=True)

    def validate_proposed_display_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("父级名称不能为空")
        return value


class ResearchRelationSerializer(serializers.Serializer):
    parent_subject_id = serializers.IntegerField(min_value=1)
    member_subject_id = serializers.IntegerField(min_value=1)
    relation_type = serializers.CharField(max_length=30, default="contains")
    position = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    evidence_type = serializers.ChoiceField(choices=["source_fact", "ai_inference"], required=False, allow_null=True)
    confidence = serializers.DecimalField(max_digits=4, decimal_places=3, min_value=0, max_value=1, required=False, allow_null=True)

    def validate(self, attrs):
        if attrs["parent_subject_id"] == attrs["member_subject_id"]:
            raise serializers.ValidationError("A research subject cannot contain itself")
        return attrs


class StructureDecisionSerializer(serializers.Serializer):
    subject_id = serializers.IntegerField(min_value=1)
    decision = serializers.ChoiceField(choices=["match_existing", "create_new"])
    catalog_entity_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)

    def validate(self, attrs):
        if (attrs["decision"] == "match_existing") != (attrs.get("catalog_entity_id") is not None):
            raise serializers.ValidationError("Only match_existing requires catalog_entity_id")
        return attrs


class CategoryDecisionSerializer(serializers.Serializer):
    category_id = serializers.IntegerField(min_value=1)
    is_primary = serializers.BooleanField(default=False)


class BookshelfVisibilitySerializer(serializers.Serializer):
    subject_id = serializers.IntegerField(min_value=1)
    visible = serializers.BooleanField()


class ReviewDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["match_existing", "create_new", "ignore"])
    catalog_entity_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    expected_version = serializers.IntegerField(min_value=1)
    manual_note = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    include_structure_subject_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), default=list, max_length=500)
    structure_decisions = StructureDecisionSerializer(many=True, default=list)
    category_decisions = CategoryDecisionSerializer(many=True, default=list, max_length=100)
    bookshelf_visibility = BookshelfVisibilitySerializer(many=True, default=list, max_length=500)

    def validate(self, attrs):
        if attrs["decision"] == "match_existing" and attrs.get("catalog_entity_id") is None:
            raise serializers.ValidationError("catalog_entity_id is required for match_existing")
        if attrs["decision"] != "match_existing" and attrs.get("catalog_entity_id") is not None:
            raise serializers.ValidationError("catalog_entity_id is only valid for match_existing")
        return attrs


class BulkMatchEntrySerializer(serializers.Serializer):
    review_item_id = serializers.IntegerField(min_value=1)
    catalog_entity_id = serializers.IntegerField(min_value=1)
    expected_version = serializers.IntegerField(min_value=1)


class BulkMatchSerializer(serializers.Serializer):
    entries = BulkMatchEntrySerializer(many=True, min_length=1, max_length=100)


class ConflictResolveSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["keep_existing", "use_proposed", "ignored"])
    manual_note = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class ReviewDataConflictSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewDataConflict
        fields = ["id", "review_item_id", "research_subject_id", "catalog_entity_id", "field_path", "existing_value", "proposed_value", "status", "manual_note"]
