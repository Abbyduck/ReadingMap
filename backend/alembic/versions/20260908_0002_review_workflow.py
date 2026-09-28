"""Add the persistent research and catalog review workflow.

Revision ID: 20260908_0002
Revises: 20260907_0001
Create Date: 2026-09-08
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20260908_0002"
down_revision: str | None = "20260907_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIGINT = mysql.BIGINT(unsigned=True)
UINT = mysql.INTEGER(unsigned=True)


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
    )


def upgrade() -> None:
    op.add_column("catalog_entities", sa.Column("description", sa.Text()))
    op.create_table(
        "reading_pen_models",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("normalized_name", name="uq_reading_pen_normalized_name"),
        mysql_charset="utf8mb4",
    )
    op.create_table(
        "catalog_entity_reading_pens",
        sa.Column("catalog_entity_id", BIGINT, sa.ForeignKey("catalog_entities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("reading_pen_model_id", BIGINT, sa.ForeignKey("reading_pen_models.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "review_batches",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_name", sa.String(500)),
        sa.Column("source_file_path", sa.String(1000)),
        sa.Column("source_content_sha256", sa.String(64)),
        sa.Column("import_key", sa.String(255), nullable=False),
        sa.Column("target_reading_list_id", BIGINT, sa.ForeignKey("reading_lists.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("total_items", UINT, nullable=False, server_default="0"),
        sa.Column("resolved_items", UINT, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        *_timestamps(),
        sa.UniqueConstraint("import_key", name="uq_review_batch_import_key"),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_review_batch_status", "review_batches", ["status"])

    op.create_table(
        "review_items",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("batch_id", BIGINT, sa.ForeignKey("review_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_item_key", sa.String(255), nullable=False),
        sa.Column("position", UINT),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("extracted_payload", sa.JSON()),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("decision", sa.String(30)),
        sa.Column("resolved_catalog_entity_id", BIGINT, sa.ForeignKey("catalog_entities.id", ondelete="RESTRICT")),
        sa.Column("committed_reading_list_item_id", BIGINT, sa.ForeignKey("reading_list_items.id", ondelete="SET NULL"), unique=True),
        sa.Column("manual_note", sa.Text()),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("resolved_at", sa.DateTime()),
        *_timestamps(),
        sa.UniqueConstraint("batch_id", "source_item_key", name="uq_review_item_source_key"),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_review_item_batch_status", "review_items", ["batch_id", "status"])

    op.create_table(
        "research_subjects",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("proposed_entity_type", sa.String(50)),
        sa.Column("proposed_display_title", sa.String(500)),
        sa.Column("proposed_title_zh", sa.String(500)),
        sa.Column("proposed_title_en", sa.String(500)),
        sa.Column("proposed_aliases", sa.JSON()),
        sa.Column("research_fingerprint", sa.String(1000)),
        sa.Column("facts_json", sa.JSON()),
        sa.Column("ai_inferences_json", sa.JSON()),
        sa.Column("research_status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("resolution_status", sa.String(30), nullable=False, server_default="unresolved"),
        sa.Column("resolved_catalog_entity_id", BIGINT, sa.ForeignKey("catalog_entities.id", ondelete="RESTRICT")),
        sa.Column("manual_note", sa.Text()),
        sa.Column("research_version", sa.String(50)),
        sa.Column("researched_at", sa.DateTime()),
        *_timestamps(),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_research_title", "research_subjects", ["proposed_display_title"])
    op.create_index("idx_research_fingerprint", "research_subjects", ["research_fingerprint"], mysql_length=191)
    op.create_index("idx_research_entity", "research_subjects", ["resolved_catalog_entity_id"])

    op.create_table(
        "review_item_subjects",
        sa.Column("review_item_id", BIGINT, sa.ForeignKey("review_items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("research_subject_id", BIGINT, sa.ForeignKey("research_subjects.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("subject_role", sa.String(30), nullable=False),
        mysql_charset="utf8mb4",
    )
    op.create_table(
        "research_sources",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("source_type", sa.String(50)),
        sa.Column("source_url", sa.String(1500), nullable=False),
        sa.Column("source_title", sa.String(1000)),
        sa.Column("fetched_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_research_source_url", "research_sources", ["source_url"], mysql_length=191)
    op.create_table(
        "research_subject_sources",
        sa.Column("research_subject_id", BIGINT, sa.ForeignKey("research_subjects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("research_source_id", BIGINT, sa.ForeignKey("research_sources.id", ondelete="CASCADE"), primary_key=True),
        mysql_charset="utf8mb4",
    )
    op.create_table(
        "research_subject_relations",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("parent_subject_id", BIGINT, sa.ForeignKey("research_subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_subject_id", BIGINT, sa.ForeignKey("research_subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(30), nullable=False, server_default="contains"),
        sa.Column("position", UINT),
        sa.Column("evidence_type", sa.String(30)),
        sa.Column("confidence", sa.Numeric(4, 3)),
        sa.Column("review_status", sa.String(30), nullable=False, server_default="proposed"),
        sa.UniqueConstraint("parent_subject_id", "member_subject_id", "relation_type", name="uq_research_relation"),
        mysql_charset="utf8mb4",
    )
    op.create_table(
        "research_catalog_candidates",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("research_subject_id", BIGINT, sa.ForeignKey("research_subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("catalog_entity_id", BIGINT, sa.ForeignKey("catalog_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_score", sa.Numeric(5, 4)),
        sa.Column("match_reasons", sa.JSON()),
        sa.Column("rank_no", UINT),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("research_subject_id", "catalog_entity_id", name="uq_subject_candidate"),
        mysql_charset="utf8mb4",
    )
    op.create_table(
        "review_data_conflicts",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("review_item_id", BIGINT, sa.ForeignKey("review_items.id", ondelete="SET NULL")),
        sa.Column("research_subject_id", BIGINT, sa.ForeignKey("research_subjects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("catalog_entity_id", BIGINT, sa.ForeignKey("catalog_entities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("field_path", sa.String(255), nullable=False),
        sa.Column("existing_value", sa.JSON()),
        sa.Column("proposed_value", sa.JSON()),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("manual_note", sa.Text()),
        *_timestamps(),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_review_conflict_status", "review_data_conflicts", ["status"])
    op.create_table(
        "review_action_logs",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("review_item_id", BIGINT, sa.ForeignKey("review_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("actor", sa.String(255)),
        sa.Column("details_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_review_action_item", "review_action_logs", ["review_item_id", "created_at"])


def downgrade() -> None:
    for table in (
        "review_action_logs",
        "review_data_conflicts",
        "research_catalog_candidates",
        "research_subject_relations",
        "research_subject_sources",
        "research_sources",
        "review_item_subjects",
        "research_subjects",
        "review_items",
        "review_batches",
        "catalog_entity_reading_pens",
        "reading_pen_models",
    ):
        op.drop_table(table)
    op.drop_column("catalog_entities", "description")
