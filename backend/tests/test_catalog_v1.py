from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.catalog import (
    ALLOWED_ENTITY_TYPES,
    COLLECTION_ENTITY_TYPES,
    CatalogEntity,
    ChildEntityAnnotation,
    ChildProfile,
    CollectionItem,
    ReadingList,
    ReadingListCreator,
    ReadingListItem,
    WorkDifficultyProfile,
)
from app.services.catalog_service import (
    CatalogDomainError,
    add_collection_item,
    add_isbn,
    create_catalog_entity,
    effective_independent_reading,
    expand_collection,
    find_by_isbn,
    search_catalog,
)
from app.services.migration_service import resolve_migration_rows


class CatalogV1AcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def entity(self, entity_type: str, title: str, **kwargs) -> CatalogEntity:
        entity = create_catalog_entity(self.db, entity_type=entity_type, display_title=title, **kwargs)
        self.db.flush()
        return entity

    def test_01_one_work_accepts_multiple_isbns_and_both_resolve_it(self) -> None:
        book = self.entity("book", "Book A")
        add_isbn(self.db, book.id, "0-306-40615-2")
        add_isbn(self.db, book.id, "978-0-306-40615-7")
        self.assertEqual(find_by_isbn(self.db, "0306406152").id, book.id)
        self.assertEqual(find_by_isbn(self.db, "9780306406157").id, book.id)

    def test_animation_is_supported_without_work_or_collection_rows(self) -> None:
        self.assertIn("animation", ALLOWED_ENTITY_TYPES)
        self.assertNotIn("animation", COLLECTION_ENTITY_TYPES)
        animation = self.entity("animation", "Example Animation")
        self.assertIsNone(animation.work)
        self.assertIsNone(animation.collection)

    def test_02_series_level_book_expands_recursively(self) -> None:
        series = self.entity("series", "丽声冒险岛")
        level = self.entity("level", "丽声冒险岛第1级")
        book = self.entity("book", "Book A")
        add_collection_item(self.db, series.id, level.id, 1)
        add_collection_item(self.db, level.id, book.id, 1)
        tree = expand_collection(self.db, series.id)
        self.assertEqual(tree["children"][0]["children"][0]["id"], book.id)

    def test_03_set_contains_levels_but_is_one_reading_list_item(self) -> None:
        bundle = self.entity("set", "丽声冒险岛1-3级")
        levels = [self.entity("level", f"第{i}级") for i in range(1, 4)]
        for position, level in enumerate(levels, 1):
            add_collection_item(self.db, bundle.id, level.id, position)
        creator = ReadingListCreator(name="达人")
        self.db.add(creator)
        self.db.flush()
        reading_list = ReadingList(creator_id=creator.id, title="路线")
        self.db.add(reading_list)
        self.db.flush()
        self.db.add(ReadingListItem(reading_list_id=reading_list.id, catalog_entity_id=bundle.id))
        self.db.flush()
        self.assertEqual(self.db.scalar(select(func.count(ReadingListItem.id))), 1)
        self.assertEqual(len(expand_collection(self.db, bundle.id)["children"]), 3)

    def test_04_book_can_belong_to_multiple_collections(self) -> None:
        book = self.entity("book", "小熊 A")
        series = self.entity("series", "心智麦田小熊系列")
        bundle = self.entity("set", "心智麦田第一辑")
        add_collection_item(self.db, series.id, book.id)
        add_collection_item(self.db, bundle.id, book.id)
        self.assertEqual(self.db.scalar(select(func.count(CollectionItem.id)).where(CollectionItem.member_entity_id == book.id)), 2)

    def test_05_bilingual_alias_search_uses_catalog_entities_only(self) -> None:
        entity = self.entity(
            "series",
            "小猪小象",
            title_zh="小猪小象",
            title_en="Elephant & Piggie",
            aliases=["小猪和小象", "Elephant and Piggie"],
        )
        self.db.flush()
        for query in ("小猪小象", "小猪和小象", "Elephant & Piggie", "Elephant and Piggie"):
            self.assertEqual([row.id for row in search_catalog(self.db, query)], [entity.id])

    def test_06_creator_age_opinions_remain_separate(self) -> None:
        book = self.entity("book", "Book A")
        for name, low, high in (("达人A", 30, 48), ("达人B", 36, 60)):
            creator = ReadingListCreator(name=name)
            self.db.add(creator)
            self.db.flush()
            reading_list = ReadingList(creator_id=creator.id, title=f"{name}书单")
            self.db.add(reading_list)
            self.db.flush()
            self.db.add(ReadingListItem(reading_list_id=reading_list.id, catalog_entity_id=book.id, recommended_age_min_months=low, recommended_age_max_months=high))
        self.db.flush()
        rows = list(self.db.scalars(select(ReadingListItem).order_by(ReadingListItem.id)))
        self.assertEqual([(row.recommended_age_min_months, row.recommended_age_max_months) for row in rows], [(30, 48), (36, 60)])
        self.assertFalse(hasattr(book.work, "recommended_age"))

    def test_07_source_lexile_does_not_overwrite_work_lexile(self) -> None:
        book = self.entity("book", "Book A")
        book.work.lexile_code = "350L"
        creator = ReadingListCreator(name="达人")
        self.db.add(creator)
        self.db.flush()
        reading_list = ReadingList(creator_id=creator.id, title="书单")
        self.db.add(reading_list)
        self.db.flush()
        item = ReadingListItem(reading_list_id=reading_list.id, catalog_entity_id=book.id, source_lexile_text="200L-500L")
        self.db.add(item)
        self.db.flush()
        self.assertEqual(book.work.lexile_code, "350L")
        self.assertEqual(item.source_lexile_text, "200L-500L")

    def test_08_unknown_syntax_remains_null(self) -> None:
        book = self.entity("book", "Book A")
        profile = WorkDifficultyProfile(work_entity_id=book.id, language_complexity_score=Decimal("3.2"), syntax_complexity_score=None, cognitive_load_score=Decimal("4.1"))
        self.db.add(profile)
        self.db.flush()
        self.assertIsNone(profile.syntax_complexity_score)

    def test_09_child_override_wins_over_catalog_flag(self) -> None:
        book = self.entity("book", "Book A", independent_reading_suitable=True)
        child = ChildProfile(name="孩子")
        self.db.add(child)
        self.db.flush()
        self.db.add(ChildEntityAnnotation(child_id=child.id, catalog_entity_id=book.id, independent_reading_override=False))
        self.db.flush()
        self.assertEqual(effective_independent_reading(self.db, child.id, book.id), (False, "child_override"))

    def test_10_unknown_migration_item_is_reported_without_creating_entity(self) -> None:
        self.entity("book", "Known Book")
        before = self.db.scalar(select(func.count(CatalogEntity.id)))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "migration_unresolved.json"
            report = resolve_migration_rows(self.db, [{"source": "legacy.json", "raw_title": "Unknown Book"}], path)
            unresolved = json.loads(path.read_text(encoding="utf-8"))
        after = self.db.scalar(select(func.count(CatalogEntity.id)))
        self.assertEqual(before, after)
        self.assertEqual(report["unresolved"], 1)
        self.assertEqual(unresolved[0]["reason"], "no catalog candidate")

    def test_collection_cycle_is_rejected(self) -> None:
        a = self.entity("series", "A")
        b = self.entity("set", "B")
        add_collection_item(self.db, a.id, b.id)
        with self.assertRaises(CatalogDomainError):
            add_collection_item(self.db, b.id, a.id)


if __name__ == "__main__":
    unittest.main()
