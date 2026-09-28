from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.catalog import EntityType


ReviewDecision = Literal["match_existing", "create_new", "ignore"]


class ReviewBatchImport(BaseModel):
    source_file_path: str = Field(min_length=1, max_length=1000)
    target_reading_list_id: int | None = None


class ReviewBatchRead(BaseModel):
    id: int
    source_type: str
    source_name: str | None = None
    source_file_path: str | None = None
    target_reading_list_id: int | None = None
    status: str
    total_items: int
    resolved_items: int
    created_at: datetime
    updated_at: datetime


class ResearchSourceWrite(BaseModel):
    source_type: str | None = Field(default=None, max_length=50)
    source_url: str = Field(min_length=1, max_length=1500)
    source_title: str | None = Field(default=None, max_length=1000)
    fetched_at: datetime | None = None


class ResearchSubjectCreate(BaseModel):
    proposed_entity_type: EntityType | None = None
    proposed_display_title: str = Field(min_length=1, max_length=500)
    proposed_title_zh: str | None = None
    proposed_title_en: str | None = None
    proposed_aliases: list[str] | None = None
    facts_json: dict | list | None = None
    ai_inferences_json: dict | list | None = None
    research_status: str = "pending"
    research_version: str | None = None
    review_item_id: int | None = None
    subject_role: str = "discovered_member"


class ResearchSubjectUpdate(BaseModel):
    proposed_entity_type: EntityType | None = None
    proposed_display_title: str | None = Field(default=None, min_length=1, max_length=500)
    proposed_title_zh: str | None = None
    proposed_title_en: str | None = None
    proposed_aliases: list[str] | None = None
    facts_json: dict | list | None = None
    ai_inferences_json: dict | list | None = None
    research_status: Literal["pending", "researching", "ready", "partial", "failed"] | None = None
    manual_note: str | None = None
    research_version: str | None = None
    researched_at: datetime | None = None
    sources: list[ResearchSourceWrite] | None = None


class ResearchRelationCreate(BaseModel):
    parent_subject_id: int
    member_subject_id: int
    relation_type: str = Field(default="contains", min_length=1, max_length=30)
    position: int | None = Field(default=None, ge=0)
    evidence_type: Literal["source_fact", "ai_inference"] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def different_subjects(self):
        if self.parent_subject_id == self.member_subject_id:
            raise ValueError("A research subject cannot contain itself")
        return self


class ReviewDecisionWrite(BaseModel):
    decision: ReviewDecision
    catalog_entity_id: int | None = None
    expected_version: int = Field(ge=1)
    actor: str | None = Field(default=None, max_length=255)
    manual_note: str | None = None
    include_structure_subject_ids: list[int] = []

    @model_validator(mode="after")
    def validate_target(self):
        if self.decision == "match_existing" and self.catalog_entity_id is None:
            raise ValueError("catalog_entity_id is required for match_existing")
        if self.decision != "match_existing" and self.catalog_entity_id is not None:
            raise ValueError("catalog_entity_id is only valid for match_existing")
        return self


class BulkMatchEntry(BaseModel):
    review_item_id: int
    catalog_entity_id: int
    expected_version: int = Field(ge=1)


class BulkMatchWrite(BaseModel):
    entries: list[BulkMatchEntry] = Field(min_length=1, max_length=100)
    actor: str | None = Field(default=None, max_length=255)


class ConflictResolveWrite(BaseModel):
    status: Literal["keep_existing", "use_proposed", "ignored"]
    actor: str | None = Field(default=None, max_length=255)
    manual_note: str | None = None
