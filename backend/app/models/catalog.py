from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text, UniqueConstraint, event, func
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin


ID_TYPE = mysql.BIGINT(unsigned=True).with_variant(Integer, "sqlite")
UINT = mysql.INTEGER(unsigned=True).with_variant(Integer, "sqlite")
USMALLINT = mysql.SMALLINT(unsigned=True).with_variant(SmallInteger, "sqlite")
UTINYINT = mysql.TINYINT(unsigned=True).with_variant(SmallInteger, "sqlite")

ALLOWED_ENTITY_TYPES = frozenset({"book", "animation", "reading_system", "series", "level", "set"})
COLLECTION_ENTITY_TYPES = frozenset({"reading_system", "series", "level", "set"})


def normalize_search_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    text = re.sub(r"\s*&\s*", " and ", text)
    text = re.sub(r"[^\w\u3400-\u9fff]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def build_catalog_search_text(entity: "CatalogEntity") -> str:
    values = [entity.display_title, entity.title_zh, entity.title_en, *(entity.aliases or [])]
    normalized: list[str] = []
    for value in values:
        item = normalize_search_text(value)
        if item and item not in normalized:
            normalized.append(item)
    return "\n".join(normalized)


class CatalogEntity(TimestampMixin, Base):
    __tablename__ = "catalog_entities"
    __table_args__ = (Index("idx_catalog_entity_type", "entity_type"),)

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    display_title: Mapped[str] = mapped_column(String(500), nullable=False)
    title_zh: Mapped[str | None] = mapped_column(String(500))
    title_en: Mapped[str | None] = mapped_column(String(500))
    aliases: Mapped[list[str] | None] = mapped_column(MutableList.as_mutable(JSON))
    search_text: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    cover_url: Mapped[str | None] = mapped_column(String(1000))
    cover_local_path: Mapped[str | None] = mapped_column(String(1000))
    independent_reading_suitable: Mapped[bool | None] = mapped_column(Boolean)

    work: Mapped["Work | None"] = relationship(back_populates="catalog_entity", uselist=False, cascade="all, delete-orphan")
    collection: Mapped["Collection | None"] = relationship(back_populates="catalog_entity", uselist=False, cascade="all, delete-orphan")
    categories: Mapped[list["CatalogEntityCategory"]] = relationship(back_populates="catalog_entity", cascade="all, delete-orphan")
    reading_pens: Mapped[list["CatalogEntityReadingPen"]] = relationship(back_populates="catalog_entity", cascade="all, delete-orphan")
    source_stats: Mapped[list["CatalogSourceStat"]] = relationship(back_populates="catalog_entity", cascade="all, delete-orphan")


@event.listens_for(CatalogEntity, "before_insert")
@event.listens_for(CatalogEntity, "before_update")
def _refresh_catalog_search_text(_mapper, _connection, target: CatalogEntity) -> None:
    target.search_text = build_catalog_search_text(target)


class Work(TimestampMixin, Base):
    __tablename__ = "works"

    catalog_entity_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("catalog_entities.id", ondelete="CASCADE"), primary_key=True)
    author_text: Mapped[str | None] = mapped_column(String(1000))
    illustrator_text: Mapped[str | None] = mapped_column(String(1000))
    language_code: Mapped[str | None] = mapped_column(String(50))
    page_count: Mapped[int | None] = mapped_column(UINT)
    word_count: Mapped[int | None] = mapped_column(UINT)
    headword_count: Mapped[int | None] = mapped_column(UINT)
    ar_level: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    lexile_code: Mapped[str | None] = mapped_column(String(50))

    catalog_entity: Mapped[CatalogEntity] = relationship(back_populates="work")
    isbns: Mapped[list["CatalogIsbn"]] = relationship(back_populates="work", cascade="all, delete-orphan")
    difficulty_profile: Mapped["WorkDifficultyProfile | None"] = relationship(back_populates="work", uselist=False, cascade="all, delete-orphan")
    ability_requirement: Mapped["WorkAbilityRequirement | None"] = relationship(back_populates="work", uselist=False, cascade="all, delete-orphan")


class CatalogIsbn(Base):
    __tablename__ = "catalog_isbns"
    __table_args__ = (
        CheckConstraint("isbn_type IN (10, 13)", name="chk_catalog_isbn_type"),
        UniqueConstraint("isbn_type", "isbn_val", name="uq_catalog_isbn"),
        Index("idx_catalog_isbn_work", "work_entity_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    work_entity_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("works.catalog_entity_id", ondelete="CASCADE"), nullable=False)
    isbn_type: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    isbn_val: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    work: Mapped[Work] = relationship(back_populates="isbns")


class Collection(TimestampMixin, Base):
    __tablename__ = "collections"

    catalog_entity_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("catalog_entities.id", ondelete="CASCADE"), primary_key=True)
    volume_count: Mapped[int | None] = mapped_column(UINT)

    catalog_entity: Mapped[CatalogEntity] = relationship(back_populates="collection")
    items: Mapped[list["CollectionItem"]] = relationship(back_populates="collection", cascade="all, delete-orphan", foreign_keys="CollectionItem.collection_id")


class CollectionItem(Base):
    __tablename__ = "collection_items"
    __table_args__ = (
        UniqueConstraint("collection_id", "member_entity_id", name="uq_collection_member"),
        Index("idx_collection_member", "member_entity_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    collection_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("collections.catalog_entity_id", ondelete="CASCADE"), nullable=False)
    member_entity_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("catalog_entities.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int | None] = mapped_column(UINT)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    collection: Mapped[Collection] = relationship(back_populates="items", foreign_keys=[collection_id])
    member_entity: Mapped[CatalogEntity] = relationship(foreign_keys=[member_entity_id])


class ReadingPenModel(TimestampMixin, Base):
    __tablename__ = "reading_pen_models"
    __table_args__ = (UniqueConstraint("normalized_name", name="uq_reading_pen_normalized_name"),)

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)

    catalog_entities: Mapped[list["CatalogEntityReadingPen"]] = relationship(back_populates="reading_pen", cascade="all, delete-orphan")


class CatalogEntityReadingPen(Base):
    __tablename__ = "catalog_entity_reading_pens"

    catalog_entity_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("catalog_entities.id", ondelete="CASCADE"), primary_key=True)
    reading_pen_model_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("reading_pen_models.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    catalog_entity: Mapped[CatalogEntity] = relationship(back_populates="reading_pens")
    reading_pen: Mapped[ReadingPenModel] = relationship(back_populates="catalog_entities")


class ReadingListCreator(TimestampMixin, Base):
    __tablename__ = "reading_list_creators"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tagline: Mapped[str | None] = mapped_column(String(500))
    background: Mapped[str | None] = mapped_column(Text)
    signature_focus: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(String(1000))

    reading_lists: Mapped[list["ReadingList"]] = relationship(back_populates="creator", cascade="all, delete-orphan")


class ReadingList(TimestampMixin, Base):
    __tablename__ = "reading_lists"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    creator_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("reading_list_creators.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    age_min_months: Mapped[int | None] = mapped_column(USMALLINT)
    age_max_months: Mapped[int | None] = mapped_column(USMALLINT)
    stage_label: Mapped[str | None] = mapped_column(String(255))
    material_type: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)

    creator: Mapped[ReadingListCreator] = relationship(back_populates="reading_lists")
    items: Mapped[list["ReadingListItem"]] = relationship(back_populates="reading_list", cascade="all, delete-orphan")


class ReadingListItem(TimestampMixin, Base):
    __tablename__ = "reading_list_items"
    __table_args__ = (
        Index("idx_reading_list_entity", "catalog_entity_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    reading_list_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("reading_lists.id", ondelete="CASCADE"), nullable=False)
    catalog_entity_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("catalog_entities.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int | None] = mapped_column(UINT)
    sub_position: Mapped[int | None] = mapped_column(USMALLINT)
    stage_label: Mapped[str | None] = mapped_column(String(255))
    recommended_age_min_months: Mapped[int | None] = mapped_column(USMALLINT)
    recommended_age_max_months: Mapped[int | None] = mapped_column(USMALLINT)
    source_ar_text: Mapped[str | None] = mapped_column(String(100))
    source_lexile_text: Mapped[str | None] = mapped_column(String(100))
    source_level_text: Mapped[str | None] = mapped_column(String(255))
    is_strong_recommendation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recommendation_emphasis_text: Mapped[str | None] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)

    reading_list: Mapped[ReadingList] = relationship(back_populates="items")
    catalog_entity: Mapped[CatalogEntity] = relationship()


class CatalogCategory(TimestampMixin, Base):
    __tablename__ = "catalog_categories"
    __table_args__ = (UniqueConstraint("category_type", "code", name="uq_category_code"),)

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(ID_TYPE, ForeignKey("catalog_categories.id", ondelete="SET NULL"))
    category_type: Mapped[str] = mapped_column(String(50), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name_zh: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500))
    sort_order: Mapped[int | None] = mapped_column(UINT)

    parent: Mapped["CatalogCategory | None"] = relationship(remote_side="CatalogCategory.id")


class CatalogEntityCategory(Base):
    __tablename__ = "catalog_entity_categories"

    catalog_entity_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("catalog_entities.id", ondelete="CASCADE"), primary_key=True)
    category_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("catalog_categories.id", ondelete="CASCADE"), primary_key=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    catalog_entity: Mapped[CatalogEntity] = relationship(back_populates="categories")
    category: Mapped[CatalogCategory] = relationship()


class WorkDifficultyProfile(TimestampMixin, Base):
    __tablename__ = "work_difficulty_profiles"
    __table_args__ = (
        CheckConstraint("language_complexity_score IS NULL OR language_complexity_score BETWEEN 0 AND 10", name="chk_language_complexity"),
        CheckConstraint("syntax_complexity_score IS NULL OR syntax_complexity_score BETWEEN 0 AND 10", name="chk_syntax_complexity"),
        CheckConstraint("cognitive_load_score IS NULL OR cognitive_load_score BETWEEN 0 AND 10", name="chk_cognitive_load"),
    )

    work_entity_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("works.catalog_entity_id", ondelete="CASCADE"), primary_key=True)
    language_complexity_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    syntax_complexity_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    cognitive_load_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    language_detail: Mapped[dict | list | None] = mapped_column(JSON)
    syntax_detail: Mapped[dict | list | None] = mapped_column(JSON)
    cognitive_detail: Mapped[dict | list | None] = mapped_column(JSON)
    analysis_version: Mapped[str | None] = mapped_column(String(50))

    work: Mapped[Work] = relationship(back_populates="difficulty_profile")


class WorkAbilityRequirement(TimestampMixin, Base):
    __tablename__ = "work_ability_requirements"
    __table_args__ = (
        CheckConstraint("language_requirement_score IS NULL OR language_requirement_score BETWEEN 0 AND 10", name="chk_language_requirement"),
        CheckConstraint("syntax_requirement_score IS NULL OR syntax_requirement_score BETWEEN 0 AND 10", name="chk_syntax_requirement"),
        CheckConstraint("cognitive_requirement_score IS NULL OR cognitive_requirement_score BETWEEN 0 AND 10", name="chk_cognitive_requirement"),
    )

    work_entity_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("works.catalog_entity_id", ondelete="CASCADE"), primary_key=True)
    language_requirement_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    syntax_requirement_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    cognitive_requirement_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    requirement_detail: Mapped[dict | list | None] = mapped_column(JSON)
    model_version: Mapped[str | None] = mapped_column(String(50))

    work: Mapped[Work] = relationship(back_populates="ability_requirement")


class ChildProfile(TimestampMixin, Base):
    __tablename__ = "child_profiles"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    birth_date: Mapped[date | None] = mapped_column(Date)

    ability_profiles: Mapped[list["ChildAbilityProfile"]] = relationship(back_populates="child", cascade="all, delete-orphan")
    entity_annotations: Mapped[list["ChildEntityAnnotation"]] = relationship(back_populates="child", cascade="all, delete-orphan")


class ChildAbilityProfile(TimestampMixin, Base):
    __tablename__ = "child_ability_profiles"
    __table_args__ = (
        CheckConstraint("language_score IS NULL OR language_score BETWEEN 0 AND 10", name="chk_child_language_score"),
        CheckConstraint("syntax_score IS NULL OR syntax_score BETWEEN 0 AND 10", name="chk_child_syntax_score"),
        CheckConstraint("cognitive_score IS NULL OR cognitive_score BETWEEN 0 AND 10", name="chk_child_cognitive_score"),
    )

    child_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("child_profiles.id", ondelete="CASCADE"), primary_key=True)
    language_code: Mapped[str] = mapped_column(String(50), primary_key=True)
    language_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    syntax_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    cognitive_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))

    child: Mapped[ChildProfile] = relationship(back_populates="ability_profiles")


class ChildEntityAnnotation(TimestampMixin, Base):
    __tablename__ = "child_entity_annotations"

    child_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("child_profiles.id", ondelete="CASCADE"), primary_key=True)
    catalog_entity_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("catalog_entities.id", ondelete="CASCADE"), primary_key=True)
    independent_reading_override: Mapped[bool | None] = mapped_column(Boolean)
    retry_after_date: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)

    child: Mapped[ChildProfile] = relationship(back_populates="entity_annotations")
    catalog_entity: Mapped[CatalogEntity] = relationship()


class CatalogSourceStat(TimestampMixin, Base):
    __tablename__ = "catalog_source_stats"
    __table_args__ = (
        UniqueConstraint("source_name", "external_id", name="uq_catalog_source_external"),
        Index("idx_catalog_stats_entity", "catalog_entity_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    catalog_entity_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("catalog_entities.id", ondelete="CASCADE"), nullable=False)
    source_name: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255))
    rating: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    rating_max: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    rating_count: Mapped[int | None] = mapped_column(UINT)
    review_count: Mapped[int | None] = mapped_column(UINT)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime)

    catalog_entity: Mapped[CatalogEntity] = relationship(back_populates="source_stats")
