from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


EntityType = Literal["book", "animation", "reading_system", "series", "level", "set"]


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class WorkFields(BaseModel):
    author_text: str | None = None
    illustrator_text: str | None = None
    language_code: str | None = None
    page_count: int | None = Field(default=None, ge=0)
    word_count: int | None = Field(default=None, ge=0)
    headword_count: int | None = Field(default=None, ge=0)
    ar_level: Decimal | None = None
    lexile_code: str | None = None


class CatalogEntityCreate(BaseModel):
    entity_type: EntityType
    display_title: str = Field(min_length=1, max_length=500)
    title_zh: str | None = None
    title_en: str | None = None
    aliases: list[str] | None = None
    description: str | None = None
    cover_url: str | None = None
    independent_reading_suitable: bool | None = None
    volume_count: int | None = Field(default=None, ge=0)
    work: WorkFields | None = None


class IsbnRead(OrmModel):
    id: int
    isbn_type: int
    isbn_val: str


class CategoryRead(OrmModel):
    id: int
    parent_id: int | None
    category_type: str
    code: str
    name_zh: str
    name_en: str | None
    description: str | None
    sort_order: int | None


class ReadingPenRead(BaseModel):
    id: int
    name: str


class CatalogEntityRead(BaseModel):
    id: int
    entity_type: str
    display_title: str
    title_zh: str | None = None
    title_en: str | None = None
    aliases: list[str] | None = None
    description: str | None = None
    cover_url: str | None = None
    independent_reading_suitable: bool | None = None
    work: WorkFields | None = None
    volume_count: int | None = None
    isbns: list[IsbnRead] = []
    categories: list[CategoryRead] = []
    reading_pens: list[ReadingPenRead] = []


class CollectionItemCreate(BaseModel):
    member_entity_id: int
    position: int | None = Field(default=None, ge=0)


class CollectionNode(BaseModel):
    id: int
    entity_type: str
    display_title: str
    children: list["CollectionNode"] = []


class CreatorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    tagline: str | None = None
    background: str | None = None
    signature_focus: str | None = None
    avatar_url: str | None = None


class CreatorRead(CreatorCreate, OrmModel):
    id: int


class ReadingListCreate(BaseModel):
    creator_id: int
    title: str = Field(min_length=1, max_length=500)
    age_min_months: int | None = Field(default=None, ge=0)
    age_max_months: int | None = Field(default=None, ge=0)
    stage_label: str | None = None
    material_type: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_age_range(self):
        if self.age_min_months is not None and self.age_max_months is not None and self.age_min_months > self.age_max_months:
            raise ValueError("age_min_months must not exceed age_max_months")
        return self


class ReadingListItemCreate(BaseModel):
    catalog_entity_id: int
    position: int | None = Field(default=None, ge=0)
    sub_position: int | None = Field(default=None, ge=0)
    stage_label: str | None = None
    recommended_age_min_months: int | None = Field(default=None, ge=0)
    recommended_age_max_months: int | None = Field(default=None, ge=0)
    source_ar_text: str | None = None
    source_lexile_text: str | None = None
    source_level_text: str | None = None
    is_strong_recommendation: bool = False
    recommendation_emphasis_text: str | None = Field(default=None, max_length=255)
    comment: str | None = None
    note: str | None = None


class ReadingListItemRead(ReadingListItemCreate):
    id: int
    entity: CatalogEntityRead


class ReadingListRead(ReadingListCreate):
    id: int
    creator_name: str
    items: list[ReadingListItemRead] = []


class CategoryCreate(BaseModel):
    parent_id: int | None = None
    category_type: str = Field(min_length=1, max_length=50)
    code: str = Field(min_length=1, max_length=100)
    name_zh: str = Field(min_length=1, max_length=100)
    name_en: str | None = None
    description: str | None = None
    sort_order: int | None = Field(default=None, ge=0)


class EntityCategoryCreate(BaseModel):
    category_id: int
    is_primary: bool = False


class DifficultyProfileWrite(BaseModel):
    language_complexity_score: Decimal | None = Field(default=None, ge=0, le=10, decimal_places=1)
    syntax_complexity_score: Decimal | None = Field(default=None, ge=0, le=10, decimal_places=1)
    cognitive_load_score: Decimal | None = Field(default=None, ge=0, le=10, decimal_places=1)
    language_detail: dict | list | None = None
    syntax_detail: dict | list | None = None
    cognitive_detail: dict | list | None = None
    analysis_version: str | None = None


class DifficultyProfileRead(DifficultyProfileWrite):
    work_entity_id: int


class AbilityRequirementWrite(BaseModel):
    language_requirement_score: Decimal | None = Field(default=None, ge=0, le=10, decimal_places=1)
    syntax_requirement_score: Decimal | None = Field(default=None, ge=0, le=10, decimal_places=1)
    cognitive_requirement_score: Decimal | None = Field(default=None, ge=0, le=10, decimal_places=1)
    requirement_detail: dict | list | None = None
    model_version: str | None = None


class AbilityRequirementRead(AbilityRequirementWrite):
    work_entity_id: int


class ChildCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    birth_date: date | None = None


class ChildRead(ChildCreate):
    id: int


class ChildAbilityWrite(BaseModel):
    language_score: Decimal | None = Field(default=None, ge=0, le=10, decimal_places=1)
    syntax_score: Decimal | None = Field(default=None, ge=0, le=10, decimal_places=1)
    cognitive_score: Decimal | None = Field(default=None, ge=0, le=10, decimal_places=1)


class ChildAbilityRead(ChildAbilityWrite):
    child_id: int
    language_code: str


class ChildAnnotationWrite(BaseModel):
    independent_reading_override: bool | None = None
    retry_after_date: date | None = None
    note: str | None = None


class ChildAnnotationRead(ChildAnnotationWrite):
    child_id: int
    catalog_entity_id: int
    effective_independent_reading: bool | None = None
    effective_source: str | None = None


class SourceStatCreate(BaseModel):
    source_name: str = Field(min_length=1, max_length=50)
    external_id: str | None = None
    rating: Decimal | None = None
    rating_max: Decimal | None = None
    rating_count: int | None = Field(default=None, ge=0)
    review_count: int | None = Field(default=None, ge=0)
    source_url: str | None = None
    fetched_at: datetime | None = None


class SourceStatRead(SourceStatCreate):
    id: int
    catalog_entity_id: int
