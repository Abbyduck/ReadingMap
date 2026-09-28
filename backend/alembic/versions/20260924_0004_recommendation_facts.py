"""Persist source-strong facts instead of numeric recommendation tiers."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260924_0004"
down_revision: str | None = "20260923_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("reading_list_items", sa.Column("is_strong_recommendation", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("reading_list_items", sa.Column("recommendation_emphasis_text", sa.String(length=255), nullable=True))
    op.execute(sa.text("UPDATE reading_list_items SET is_strong_recommendation = 1, recommendation_emphasis_text = recommendation_strength_text WHERE recommendation_strength = 3"))
    op.drop_constraint("chk_reading_item_strength", "reading_list_items", type_="check")
    op.drop_column("reading_list_items", "recommendation_strength_text")
    op.drop_column("reading_list_items", "recommendation_strength")


def downgrade() -> None:
    op.add_column("reading_list_items", sa.Column("recommendation_strength", sa.SmallInteger(), nullable=True))
    op.add_column("reading_list_items", sa.Column("recommendation_strength_text", sa.String(length=255), nullable=True))
    op.execute(sa.text("UPDATE reading_list_items SET recommendation_strength = 3, recommendation_strength_text = recommendation_emphasis_text WHERE is_strong_recommendation = 1"))
    op.create_check_constraint("chk_reading_item_strength", "reading_list_items", "recommendation_strength IS NULL OR recommendation_strength BETWEEN 1 AND 3")
    op.drop_column("reading_list_items", "recommendation_emphasis_text")
    op.drop_column("reading_list_items", "is_strong_recommendation")
