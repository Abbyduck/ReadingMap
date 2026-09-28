"""Catalog v1 clean baseline.

Revision ID: 20260907_0001
Revises:
Create Date: 2026-09-07

This is intentionally a new, incompatible development baseline. Existing data is
not migrated; recreate the development database before applying it.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20260907_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIGINT = mysql.BIGINT(unsigned=True)
UINT = mysql.INTEGER(unsigned=True)
USMALLINT = mysql.SMALLINT(unsigned=True)


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
    op.create_table(
        "catalog_entities",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("display_title", sa.String(500), nullable=False),
        sa.Column("title_zh", sa.String(500)),
        sa.Column("title_en", sa.String(500)),
        sa.Column("aliases", sa.JSON()),
        sa.Column("search_text", sa.Text()),
        sa.Column("cover_url", sa.String(1000)),
        sa.Column("cover_local_path", sa.String(1000)),
        sa.Column("independent_reading_suitable", sa.Boolean()),
        *_timestamps(),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_catalog_entity_type", "catalog_entities", ["entity_type"])

    op.create_table(
        "works",
        sa.Column("catalog_entity_id", BIGINT, sa.ForeignKey("catalog_entities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("author_text", sa.String(1000)),
        sa.Column("illustrator_text", sa.String(1000)),
        sa.Column("language_code", sa.String(50)),
        sa.Column("page_count", UINT),
        sa.Column("word_count", UINT),
        sa.Column("headword_count", UINT),
        sa.Column("ar_level", sa.Numeric(4, 2)),
        sa.Column("lexile_code", sa.String(50)),
        *_timestamps(),
        mysql_charset="utf8mb4",
    )
    op.create_table(
        "catalog_isbns",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("work_entity_id", BIGINT, sa.ForeignKey("works.catalog_entity_id", ondelete="CASCADE"), nullable=False),
        sa.Column("isbn_type", sa.SmallInteger(), nullable=False),
        sa.Column("isbn_val", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("isbn_type IN (10, 13)", name="chk_catalog_isbn_type"),
        sa.UniqueConstraint("isbn_type", "isbn_val", name="uq_catalog_isbn"),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_catalog_isbn_work", "catalog_isbns", ["work_entity_id"])

    op.create_table(
        "collections",
        sa.Column("catalog_entity_id", BIGINT, sa.ForeignKey("catalog_entities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("volume_count", UINT),
        *_timestamps(),
        mysql_charset="utf8mb4",
    )
    op.create_table(
        "collection_items",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("collection_id", BIGINT, sa.ForeignKey("collections.catalog_entity_id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_entity_id", BIGINT, sa.ForeignKey("catalog_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", UINT),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("collection_id", "member_entity_id", name="uq_collection_member"),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_collection_member", "collection_items", ["member_entity_id"])

    op.create_table(
        "reading_list_creators",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("tagline", sa.String(500)),
        sa.Column("background", sa.Text()),
        sa.Column("signature_focus", sa.Text()),
        sa.Column("avatar_url", sa.String(1000)),
        *_timestamps(),
        mysql_charset="utf8mb4",
    )
    op.create_table(
        "reading_lists",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("creator_id", BIGINT, sa.ForeignKey("reading_list_creators.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("age_min_months", USMALLINT),
        sa.Column("age_max_months", USMALLINT),
        sa.Column("stage_label", sa.String(255)),
        sa.Column("material_type", sa.String(50)),
        sa.Column("description", sa.Text()),
        *_timestamps(),
        mysql_charset="utf8mb4",
    )
    op.create_table(
        "reading_list_items",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("reading_list_id", BIGINT, sa.ForeignKey("reading_lists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("catalog_entity_id", BIGINT, sa.ForeignKey("catalog_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", UINT),
        sa.Column("sub_position", USMALLINT),
        sa.Column("stage_label", sa.String(255)),
        sa.Column("recommended_age_min_months", USMALLINT),
        sa.Column("recommended_age_max_months", USMALLINT),
        sa.Column("source_ar_text", sa.String(100)),
        sa.Column("source_lexile_text", sa.String(100)),
        sa.Column("source_level_text", sa.String(255)),
        sa.Column("comment", sa.Text()),
        sa.Column("note", sa.Text()),
        *_timestamps(),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_reading_list_entity", "reading_list_items", ["catalog_entity_id"])

    op.create_table(
        "catalog_categories",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("parent_id", BIGINT, sa.ForeignKey("catalog_categories.id", ondelete="SET NULL")),
        sa.Column("category_type", sa.String(50), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name_zh", sa.String(100), nullable=False),
        sa.Column("name_en", sa.String(100)),
        sa.Column("description", sa.String(500)),
        sa.Column("sort_order", UINT),
        *_timestamps(),
        sa.UniqueConstraint("category_type", "code", name="uq_category_code"),
        mysql_charset="utf8mb4",
    )
    op.create_table(
        "catalog_entity_categories",
        sa.Column("catalog_entity_id", BIGINT, sa.ForeignKey("catalog_entities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("category_id", BIGINT, sa.ForeignKey("catalog_categories.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        mysql_charset="utf8mb4",
    )

    score_check = lambda column, name: sa.CheckConstraint(f"{column} IS NULL OR {column} BETWEEN 0 AND 10", name=name)
    op.create_table(
        "work_difficulty_profiles",
        sa.Column("work_entity_id", BIGINT, sa.ForeignKey("works.catalog_entity_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("language_complexity_score", sa.Numeric(3, 1)),
        sa.Column("syntax_complexity_score", sa.Numeric(3, 1)),
        sa.Column("cognitive_load_score", sa.Numeric(3, 1)),
        sa.Column("language_detail", sa.JSON()),
        sa.Column("syntax_detail", sa.JSON()),
        sa.Column("cognitive_detail", sa.JSON()),
        sa.Column("analysis_version", sa.String(50)),
        *_timestamps(),
        score_check("language_complexity_score", "chk_language_complexity"),
        score_check("syntax_complexity_score", "chk_syntax_complexity"),
        score_check("cognitive_load_score", "chk_cognitive_load"),
        mysql_charset="utf8mb4",
    )
    op.create_table(
        "work_ability_requirements",
        sa.Column("work_entity_id", BIGINT, sa.ForeignKey("works.catalog_entity_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("language_requirement_score", sa.Numeric(3, 1)),
        sa.Column("syntax_requirement_score", sa.Numeric(3, 1)),
        sa.Column("cognitive_requirement_score", sa.Numeric(3, 1)),
        sa.Column("requirement_detail", sa.JSON()),
        sa.Column("model_version", sa.String(50)),
        *_timestamps(),
        score_check("language_requirement_score", "chk_language_requirement"),
        score_check("syntax_requirement_score", "chk_syntax_requirement"),
        score_check("cognitive_requirement_score", "chk_cognitive_requirement"),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "child_profiles",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("birth_date", sa.Date()),
        *_timestamps(),
        mysql_charset="utf8mb4",
    )
    op.create_table(
        "child_ability_profiles",
        sa.Column("child_id", BIGINT, sa.ForeignKey("child_profiles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("language_code", sa.String(50), primary_key=True),
        sa.Column("language_score", sa.Numeric(3, 1)),
        sa.Column("syntax_score", sa.Numeric(3, 1)),
        sa.Column("cognitive_score", sa.Numeric(3, 1)),
        *_timestamps(),
        score_check("language_score", "chk_child_language_score"),
        score_check("syntax_score", "chk_child_syntax_score"),
        score_check("cognitive_score", "chk_child_cognitive_score"),
        mysql_charset="utf8mb4",
    )
    op.create_table(
        "child_entity_annotations",
        sa.Column("child_id", BIGINT, sa.ForeignKey("child_profiles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("catalog_entity_id", BIGINT, sa.ForeignKey("catalog_entities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("independent_reading_override", sa.Boolean()),
        sa.Column("retry_after_date", sa.Date()),
        sa.Column("note", sa.Text()),
        *_timestamps(),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "catalog_source_stats",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("catalog_entity_id", BIGINT, sa.ForeignKey("catalog_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_name", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(255)),
        sa.Column("rating", sa.Numeric(4, 2)),
        sa.Column("rating_max", sa.Numeric(4, 2)),
        sa.Column("rating_count", UINT),
        sa.Column("review_count", UINT),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("fetched_at", sa.DateTime()),
        *_timestamps(),
        sa.UniqueConstraint("source_name", "external_id", name="uq_catalog_source_external"),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_catalog_stats_entity", "catalog_source_stats", ["catalog_entity_id"])


def downgrade() -> None:
    for table in (
        "catalog_source_stats",
        "child_entity_annotations",
        "child_ability_profiles",
        "child_profiles",
        "work_ability_requirements",
        "work_difficulty_profiles",
        "catalog_entity_categories",
        "catalog_categories",
        "reading_list_items",
        "reading_lists",
        "reading_list_creators",
        "collection_items",
        "collections",
        "catalog_isbns",
        "works",
        "catalog_entities",
    ):
        op.drop_table(table)
