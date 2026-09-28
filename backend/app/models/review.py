from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.catalog import ID_TYPE, UINT, CatalogEntity, ReadingList, ReadingListItem
from app.models.common import TimestampMixin


class ReviewBatch(TimestampMixin, Base):
    __tablename__ = "review_batches"
    __table_args__ = (
        UniqueConstraint("import_key", name="uq_review_batch_import_key"),
        Index("idx_review_batch_status", "status"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(500))
    source_file_path: Mapped[str | None] = mapped_column(String(1000))
    source_content_sha256: Mapped[str | None] = mapped_column(String(64))
    import_key: Mapped[str] = mapped_column(String(255), nullable=False)
    target_reading_list_id: Mapped[int | None] = mapped_column(
        ID_TYPE, ForeignKey("reading_lists.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", server_default="pending")
    total_items: Mapped[int] = mapped_column(UINT, nullable=False, default=0, server_default="0")
    resolved_items: Mapped[int] = mapped_column(UINT, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)

    target_reading_list: Mapped[ReadingList | None] = relationship()
    items: Mapped[list["ReviewItem"]] = relationship(back_populates="batch", cascade="all, delete-orphan")


class ReviewItem(TimestampMixin, Base):
    __tablename__ = "review_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "source_item_key", name="uq_review_item_source_key"),
        Index("idx_review_item_batch_status", "batch_id", "status"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("review_batches.id", ondelete="CASCADE"), nullable=False)
    source_item_key: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int | None] = mapped_column(UINT)
    raw_payload: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    extracted_payload: Mapped[dict | list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", server_default="pending")
    decision: Mapped[str | None] = mapped_column(String(30))
    resolved_catalog_entity_id: Mapped[int | None] = mapped_column(
        ID_TYPE, ForeignKey("catalog_entities.id", ondelete="RESTRICT")
    )
    committed_reading_list_item_id: Mapped[int | None] = mapped_column(
        ID_TYPE, ForeignKey("reading_list_items.id", ondelete="SET NULL"), unique=True
    )
    manual_note: Mapped[str | None] = mapped_column(Text)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)

    batch: Mapped[ReviewBatch] = relationship(back_populates="items")
    resolved_catalog_entity: Mapped[CatalogEntity | None] = relationship(foreign_keys=[resolved_catalog_entity_id])
    committed_reading_list_item: Mapped[ReadingListItem | None] = relationship()
    subject_links: Mapped[list["ReviewItemSubject"]] = relationship(back_populates="review_item", cascade="all, delete-orphan")
    action_logs: Mapped[list["ReviewActionLog"]] = relationship(back_populates="review_item", cascade="all, delete-orphan")


class ResearchSubject(TimestampMixin, Base):
    __tablename__ = "research_subjects"
    __table_args__ = (
        Index("idx_research_title", "proposed_display_title"),
        Index("idx_research_fingerprint", "research_fingerprint", mysql_length=191),
        Index("idx_research_entity", "resolved_catalog_entity_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    proposed_entity_type: Mapped[str | None] = mapped_column(String(50))
    proposed_display_title: Mapped[str | None] = mapped_column(String(500))
    proposed_title_zh: Mapped[str | None] = mapped_column(String(500))
    proposed_title_en: Mapped[str | None] = mapped_column(String(500))
    proposed_aliases: Mapped[list | None] = mapped_column(JSON)
    research_fingerprint: Mapped[str | None] = mapped_column(String(1000))
    facts_json: Mapped[dict | list | None] = mapped_column(JSON)
    ai_inferences_json: Mapped[dict | list | None] = mapped_column(JSON)
    research_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", server_default="pending")
    resolution_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unresolved", server_default="unresolved")
    resolved_catalog_entity_id: Mapped[int | None] = mapped_column(
        ID_TYPE, ForeignKey("catalog_entities.id", ondelete="RESTRICT")
    )
    manual_note: Mapped[str | None] = mapped_column(Text)
    research_version: Mapped[str | None] = mapped_column(String(50))
    researched_at: Mapped[datetime | None] = mapped_column(DateTime)

    resolved_catalog_entity: Mapped[CatalogEntity | None] = relationship()
    item_links: Mapped[list["ReviewItemSubject"]] = relationship(back_populates="research_subject")
    source_links: Mapped[list["ResearchSubjectSource"]] = relationship(back_populates="research_subject", cascade="all, delete-orphan")
    candidates: Mapped[list["ResearchCatalogCandidate"]] = relationship(back_populates="research_subject", cascade="all, delete-orphan")


class ReviewItemSubject(Base):
    __tablename__ = "review_item_subjects"

    review_item_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("review_items.id", ondelete="CASCADE"), primary_key=True
    )
    research_subject_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("research_subjects.id", ondelete="RESTRICT"), primary_key=True
    )
    subject_role: Mapped[str] = mapped_column(String(30), nullable=False)

    review_item: Mapped[ReviewItem] = relationship(back_populates="subject_links")
    research_subject: Mapped[ResearchSubject] = relationship(back_populates="item_links")


class ResearchSource(Base):
    __tablename__ = "research_sources"
    __table_args__ = (Index("idx_research_source_url", "source_url", mysql_length=191),)

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    source_type: Mapped[str | None] = mapped_column(String(50))
    source_url: Mapped[str] = mapped_column(String(1500), nullable=False)
    source_title: Mapped[str | None] = mapped_column(String(1000))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    subject_links: Mapped[list["ResearchSubjectSource"]] = relationship(back_populates="research_source", cascade="all, delete-orphan")


class ResearchSubjectSource(Base):
    __tablename__ = "research_subject_sources"

    research_subject_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("research_subjects.id", ondelete="CASCADE"), primary_key=True
    )
    research_source_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("research_sources.id", ondelete="CASCADE"), primary_key=True
    )

    research_subject: Mapped[ResearchSubject] = relationship(back_populates="source_links")
    research_source: Mapped[ResearchSource] = relationship(back_populates="subject_links")


class ResearchSubjectRelation(Base):
    __tablename__ = "research_subject_relations"
    __table_args__ = (
        UniqueConstraint("parent_subject_id", "member_subject_id", "relation_type", name="uq_research_relation"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    parent_subject_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("research_subjects.id", ondelete="CASCADE"), nullable=False
    )
    member_subject_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("research_subjects.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(30), nullable=False, default="contains", server_default="contains")
    position: Mapped[int | None] = mapped_column(UINT)
    evidence_type: Mapped[str | None] = mapped_column(String(30))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="proposed", server_default="proposed")

    parent_subject: Mapped[ResearchSubject] = relationship(foreign_keys=[parent_subject_id])
    member_subject: Mapped[ResearchSubject] = relationship(foreign_keys=[member_subject_id])


class ResearchCatalogCandidate(Base):
    __tablename__ = "research_catalog_candidates"
    __table_args__ = (
        UniqueConstraint("research_subject_id", "catalog_entity_id", name="uq_subject_candidate"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    research_subject_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("research_subjects.id", ondelete="CASCADE"), nullable=False
    )
    catalog_entity_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("catalog_entities.id", ondelete="CASCADE"), nullable=False
    )
    match_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    match_reasons: Mapped[dict | list | None] = mapped_column(JSON)
    rank_no: Mapped[int | None] = mapped_column(UINT)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    research_subject: Mapped[ResearchSubject] = relationship(back_populates="candidates")
    catalog_entity: Mapped[CatalogEntity] = relationship()


class ReviewDataConflict(TimestampMixin, Base):
    __tablename__ = "review_data_conflicts"
    __table_args__ = (Index("idx_review_conflict_status", "status"),)

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    review_item_id: Mapped[int | None] = mapped_column(
        ID_TYPE, ForeignKey("review_items.id", ondelete="SET NULL")
    )
    research_subject_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("research_subjects.id", ondelete="RESTRICT"), nullable=False
    )
    catalog_entity_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("catalog_entities.id", ondelete="RESTRICT"), nullable=False
    )
    field_path: Mapped[str] = mapped_column(String(255), nullable=False)
    existing_value: Mapped[dict | list | str | int | float | None] = mapped_column(JSON)
    proposed_value: Mapped[dict | list | str | int | float | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", server_default="pending")
    manual_note: Mapped[str | None] = mapped_column(Text)

    review_item: Mapped[ReviewItem | None] = relationship()
    research_subject: Mapped[ResearchSubject] = relationship()
    catalog_entity: Mapped[CatalogEntity] = relationship()


class ReviewActionLog(Base):
    __tablename__ = "review_action_logs"
    __table_args__ = (Index("idx_review_action_item", "review_item_id", "created_at"),)

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    review_item_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("review_items.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(255))
    details_json: Mapped[dict | list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    review_item: Mapped[ReviewItem] = relationship(back_populates="action_logs")
