from django.db import models


class Timestamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ReviewBatch(Timestamped):
    source_type = models.CharField(max_length=50)
    source_name = models.CharField(max_length=500, null=True, blank=True)
    source_file_path = models.CharField(max_length=1000, null=True, blank=True)
    source_content_sha256 = models.CharField(max_length=64, null=True, blank=True)
    import_key = models.CharField(max_length=255, unique=True)
    target_reading_list = models.ForeignKey("catalog.ReadingList", on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=30, default="pending", db_index=True)
    total_items = models.PositiveIntegerField(default=0)
    resolved_items = models.PositiveIntegerField(default=0)
    last_error = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "review_batches"

    def __str__(self):
        return self.source_name or f"Batch {self.pk}"


class ReviewItem(Timestamped):
    batch = models.ForeignKey(ReviewBatch, on_delete=models.CASCADE, related_name="items")
    source_item_key = models.CharField(max_length=255)
    position = models.PositiveIntegerField(null=True, blank=True)
    raw_payload = models.JSONField()
    extracted_payload = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=30, default="pending")
    decision = models.CharField(max_length=30, null=True, blank=True)
    resolved_catalog_entity = models.ForeignKey("catalog.CatalogEntity", on_delete=models.PROTECT, null=True, blank=True)
    committed_reading_list_item = models.OneToOneField("catalog.ReadingListItem", on_delete=models.SET_NULL, null=True, blank=True)
    manual_note = models.TextField(null=True, blank=True)
    lock_version = models.PositiveIntegerField(default=1)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "review_items"
        constraints = [models.UniqueConstraint(fields=["batch", "source_item_key"], name="uq_review_item_source_key")]
        indexes = [models.Index(fields=["batch", "status"], name="idx_review_item_batch_status")]

    def __str__(self):
        return f"{self.batch_id} / {self.source_item_key}"


class ResearchSubject(Timestamped):
    proposed_entity_type = models.CharField(max_length=50, null=True, blank=True)
    proposed_display_title = models.CharField(max_length=500, null=True, blank=True)
    proposed_title_zh = models.CharField(max_length=500, null=True, blank=True)
    proposed_title_en = models.CharField(max_length=500, null=True, blank=True)
    proposed_aliases = models.JSONField(null=True, blank=True)
    research_fingerprint = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    facts_json = models.JSONField(null=True, blank=True)
    guide_markdown_draft = models.TextField(null=True, blank=True)
    ai_inferences_json = models.JSONField(null=True, blank=True)
    research_status = models.CharField(max_length=30, default="pending")
    resolution_status = models.CharField(max_length=30, default="unresolved")
    resolved_catalog_entity = models.ForeignKey("catalog.CatalogEntity", on_delete=models.PROTECT, null=True, blank=True)
    manual_note = models.TextField(null=True, blank=True)
    research_version = models.CharField(max_length=50, null=True, blank=True)
    researched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "research_subjects"

    def __str__(self):
        return self.proposed_display_title or f"Subject {self.pk}"


class ReviewItemSubject(models.Model):
    review_item = models.ForeignKey(ReviewItem, on_delete=models.CASCADE, related_name="subject_links")
    research_subject = models.ForeignKey(ResearchSubject, on_delete=models.PROTECT, related_name="item_links")
    subject_role = models.CharField(max_length=30)

    class Meta:
        db_table = "review_item_subjects"
        constraints = [models.UniqueConstraint(fields=["review_item", "research_subject"], name="uq_review_item_subject")]


class ResearchSource(models.Model):
    source_type = models.CharField(max_length=50, null=True, blank=True)
    source_url = models.CharField(max_length=1500)
    source_title = models.CharField(max_length=1000, null=True, blank=True)
    raw_content = models.TextField(null=True, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "research_sources"

    def __str__(self):
        return self.source_title or self.source_url


class ResearchSubjectSource(models.Model):
    research_subject = models.ForeignKey(ResearchSubject, on_delete=models.CASCADE, related_name="source_links")
    research_source = models.ForeignKey(ResearchSource, on_delete=models.CASCADE, related_name="subject_links")

    class Meta:
        db_table = "research_subject_sources"
        constraints = [models.UniqueConstraint(fields=["research_subject", "research_source"], name="uq_research_subject_source")]


class ResearchSubjectRelation(models.Model):
    parent_subject = models.ForeignKey(ResearchSubject, on_delete=models.CASCADE, related_name="member_relations")
    member_subject = models.ForeignKey(ResearchSubject, on_delete=models.CASCADE, related_name="parent_relations")
    relation_type = models.CharField(max_length=30, default="contains")
    position = models.PositiveIntegerField(null=True, blank=True)
    evidence_type = models.CharField(max_length=30, null=True, blank=True)
    confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    review_status = models.CharField(max_length=30, default="proposed")

    class Meta:
        db_table = "research_subject_relations"
        constraints = [models.UniqueConstraint(fields=["parent_subject", "member_subject", "relation_type"], name="uq_research_relation")]


class ResearchCatalogCandidate(models.Model):
    research_subject = models.ForeignKey(ResearchSubject, on_delete=models.CASCADE, related_name="candidates")
    catalog_entity = models.ForeignKey("catalog.CatalogEntity", on_delete=models.CASCADE)
    match_score = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    match_reasons = models.JSONField(null=True, blank=True)
    rank_no = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "research_catalog_candidates"
        constraints = [models.UniqueConstraint(fields=["research_subject", "catalog_entity"], name="uq_subject_candidate")]


class ReviewDataConflict(Timestamped):
    review_item = models.ForeignKey(ReviewItem, on_delete=models.SET_NULL, null=True, blank=True)
    research_subject = models.ForeignKey(ResearchSubject, on_delete=models.PROTECT)
    catalog_entity = models.ForeignKey("catalog.CatalogEntity", on_delete=models.PROTECT)
    field_path = models.CharField(max_length=255)
    existing_value = models.JSONField(null=True, blank=True)
    proposed_value = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=30, default="pending", db_index=True)
    manual_note = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "review_data_conflicts"


class ReviewEditionDraft(Timestamped):
    review_item = models.ForeignKey(ReviewItem, related_name="edition_drafts", on_delete=models.CASCADE)
    book_subject = models.ForeignKey(ResearchSubject, null=True, blank=True, on_delete=models.SET_NULL)
    matched_catalog_edition = models.ForeignKey("catalog.BookEdition", null=True, blank=True, on_delete=models.SET_NULL)
    proposed_data = models.JSONField(default=dict)
    review_status = models.CharField(max_length=30, default="proposed")
    source = models.ForeignKey(ResearchSource, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = "review_edition_drafts"


class ReviewActionLog(models.Model):
    review_item = models.ForeignKey(ReviewItem, on_delete=models.CASCADE, related_name="action_logs")
    action = models.CharField(max_length=50)
    actor = models.CharField(max_length=255, null=True, blank=True)
    details_json = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "review_action_logs"
        indexes = [models.Index(fields=["review_item", "created_at"], name="idx_review_action_item")]
