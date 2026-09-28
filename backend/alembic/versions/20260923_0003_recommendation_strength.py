"""Add source recommendation strength to reading-list relationships.

Revision ID: 20260923_0003
Revises: 20260908_0002
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20260923_0003"
down_revision: str | None = "20260908_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("reading_list_items", sa.Column("recommendation_strength", mysql.TINYINT(unsigned=True), nullable=True))
    op.add_column("reading_list_items", sa.Column("recommendation_strength_text", sa.String(length=255), nullable=True))
    op.create_check_constraint(
        "chk_reading_item_strength",
        "reading_list_items",
        "recommendation_strength IS NULL OR recommendation_strength BETWEEN 1 AND 3",
    )


def downgrade() -> None:
    op.drop_constraint("chk_reading_item_strength", "reading_list_items", type_="check")
    op.drop_column("reading_list_items", "recommendation_strength_text")
    op.drop_column("reading_list_items", "recommendation_strength")
