from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.catalog import (
    CatalogEntity,
    CatalogEntityReadingPen,
    CollectionItem,
    ReadingList,
    ReadingListCreator,
    ReadingListItem,
)
from app.models.review import (
    ResearchSource,
    ResearchSubject,
    ResearchSubjectSource,
    ReviewDataConflict,
    ReviewItem,
    ReviewItemSubject,
)
from app.services.catalog_service import create_catalog_entity
from app.services.review_service import (
    DuplicateCandidateError,
    create_research_relation,
    create_research_subject,
    import_source_file,
    resolve_review_item,
)


class ReviewWorkflowAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        creator = ReadingListCreator(name="达人")
        self.db.add(creator)
        self.db.flush()
        self.reading_list = ReadingList(creator_id=creator.id, title="路线")
        self.db.add(self.reading_list)
        self.db.flush()
        self.temp = tempfile.TemporaryDirectory()
        self.source_root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()
        self.temp.cleanup()

    def _document(self, title: str, entity_type: str = "book", marker: str = "") -> dict:
        return {
            "schema_version": "1.0",
            "document_type": "reading_list",
            "list": {"title": f"测试书单{marker}"},
            "items": [
                {
                    "position": 1,
                    "raw_title": title,
                    "extracted": {"title": title},
                    "analysis": {"possible_entity_type": entity_type},
                }
            ],
        }

    def _import(self, document: dict, filename: str = "list.json") -> tuple:
        path = self.source_root / filename
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        with patch("app.services.review_service.SOURCE_ROOT", self.source_root):
            batch, created = import_source_file(self.db, filename, self.reading_list.id)
        self.db.flush()
        item = self.db.scalar(select(ReviewItem).where(ReviewItem.batch_id == batch.id))
        link = self.db.scalar(
            select(ReviewItemSubject).where(
                ReviewItemSubject.review_item_id == item.id,
                ReviewItemSubject.subject_role == "primary",
            )
        )
        return batch, item, self.db.get(ResearchSubject, link.research_subject_id), created

    def _source_fact(self, subject: ResearchSubject, facts: dict) -> None:
        source = ResearchSource(source_type="official", source_url=f"https://example.test/{subject.id}")
        self.db.add(source)
        self.db.flush()
        self.db.add(ResearchSubjectSource(research_subject_id=subject.id, research_source_id=source.id))
        subject.facts_json = {key: {"value": value, "source_ids": [source.id]} for key, value in facts.items()}
        self.db.flush()

    def _decision(self, item: ReviewItem, decision: str, catalog_entity_id: int | None = None, include: list[int] | None = None):
        return resolve_review_item(
            self.db,
            item.id,
            {
                "decision": decision,
                "catalog_entity_id": catalog_entity_id,
                "expected_version": item.lock_version,
                "actor": "tester",
                "manual_note": None,
                "include_structure_subject_ids": include or [],
            },
        )

    def test_01_match_existing_creates_only_source_relation(self) -> None:
        entity = create_catalog_entity(
            self.db,
            entity_type="series",
            display_title="小猪小象",
            aliases=["小猪和小象", "Elephant & Piggie"],
        )
        self.db.flush()
        before = self.db.scalar(select(func.count(CatalogEntity.id)))
        _, item, _, _ = self._import(self._document("小猪和小象", "series"))
        self._decision(item, "match_existing", entity.id)
        self.db.flush()
        self.assertEqual(self.db.scalar(select(func.count(CatalogEntity.id))), before)
        relations = list(self.db.scalars(select(ReadingListItem)).all())
        self.assertEqual([row.catalog_entity_id for row in relations], [entity.id])

    def test_02_discovered_series_is_completed_without_fake_recommendations(self) -> None:
        _, item, primary, _ = self._import(self._document("丽声冒险岛第3级", "level"))
        parent = create_research_subject(self.db, {"proposed_entity_type": "series", "proposed_display_title": "丽声冒险岛"})
        siblings = []
        for number in (1, 2, 4, 5):
            subject = create_research_subject(
                self.db,
                {"proposed_entity_type": "level", "proposed_display_title": f"丽声冒险岛第{number}级"},
            )
            siblings.append(subject)
        for position, subject in enumerate([siblings[0], siblings[1], primary, siblings[2], siblings[3]], 1):
            create_research_relation(
                self.db,
                {"parent_subject_id": parent.id, "member_subject_id": subject.id, "position": position},
            )
        selected = [parent.id, primary.id, *(subject.id for subject in siblings)]
        self._decision(item, "create_new", include=selected)
        self.db.flush()
        self.assertEqual(self.db.scalar(select(func.count(CollectionItem.id))), 5)
        recommendation_ids = list(self.db.scalars(select(ReadingListItem.catalog_entity_id)).all())
        self.assertEqual(recommendation_ids, [item.resolved_catalog_entity_id])

    def test_03_partial_structure_reuses_existing_entities(self) -> None:
        series = create_catalog_entity(self.db, entity_type="series", display_title="丽声冒险岛")
        level1 = create_catalog_entity(self.db, entity_type="level", display_title="丽声冒险岛第1级")
        level3 = create_catalog_entity(self.db, entity_type="level", display_title="丽声冒险岛第3级")
        self.db.flush()
        _, item, primary, _ = self._import(self._document("丽声冒险岛第3级", "level"))
        parent = create_research_subject(self.db, {"proposed_entity_type": "series", "proposed_display_title": "丽声冒险岛"})
        levels = {3: primary}
        for number in (1, 2, 4, 5):
            levels[number] = create_research_subject(
                self.db,
                {"proposed_entity_type": "level", "proposed_display_title": f"丽声冒险岛第{number}级"},
            )
        for number in range(1, 6):
            create_research_relation(
                self.db,
                {"parent_subject_id": parent.id, "member_subject_id": levels[number].id, "position": number},
            )
        selected = [parent.id, *(subject.id for subject in levels.values())]
        self._decision(item, "match_existing", level3.id, selected)
        self.db.flush()
        self.assertEqual(parent.resolved_catalog_entity_id, series.id)
        self.assertEqual(levels[1].resolved_catalog_entity_id, level1.id)
        self.assertEqual(self.db.scalar(select(func.count(CatalogEntity.id))), 6)

    def test_04_sourced_research_fills_an_empty_catalog_field(self) -> None:
        entity = create_catalog_entity(self.db, entity_type="book", display_title="Book A")
        self.db.flush()
        _, item, subject, _ = self._import(self._document("Book A"))
        self._source_fact(subject, {"description": "官方简介"})
        self._decision(item, "match_existing", entity.id)
        self.assertEqual(entity.description, "官方简介")

    def test_05_conflicting_fact_never_overwrites_catalog(self) -> None:
        entity = create_catalog_entity(self.db, entity_type="book", display_title="Book A")
        entity.work.lexile_code = "300L"
        self.db.flush()
        _, item, subject, _ = self._import(self._document("Book A"))
        self._source_fact(subject, {"lexile": "400L"})
        self._decision(item, "match_existing", entity.id)
        self.db.flush()
        self.assertEqual(entity.work.lexile_code, "300L")
        conflict = self.db.scalar(select(ReviewDataConflict))
        self.assertEqual((conflict.field_path, conflict.proposed_value), ("work.lexile_code", "400L"))

    def test_06_same_identity_reuses_long_lived_research(self) -> None:
        _, _, first_subject, first_created = self._import(self._document("丽声冒险岛第3级", "level", "A"), "a.json")
        _, _, second_subject, second_created = self._import(self._document("丽声冒险岛第3级", "level", "B"), "b.json")
        self.assertTrue(first_created and second_created)
        self.assertEqual(first_subject.id, second_subject.id)
        self.assertEqual(self.db.scalar(select(func.count(ResearchSubject.id))), 1)

    def test_07_reading_pen_versions_stay_on_one_catalog_entity(self) -> None:
        entity = create_catalog_entity(self.db, entity_type="series", display_title="美国国家地理分级")
        self.db.flush()
        _, item, subject, _ = self._import(self._document("美国国家地理分级", "series"))
        self._source_fact(subject, {"reading_pens": ["毛毛虫", "童趣"]})
        self._decision(item, "match_existing", entity.id)
        self.db.flush()
        self.assertEqual(self.db.scalar(select(func.count(CatalogEntity.id))), 1)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CatalogEntityReadingPen)), 2)

    def test_08_create_new_rechecks_candidates_at_submit_time(self) -> None:
        _, item, _, _ = self._import(self._document("并发新书"))
        create_catalog_entity(self.db, entity_type="book", display_title="并发新书")
        self.db.flush()
        with self.assertRaises(DuplicateCandidateError):
            self._decision(item, "create_new")
        self.assertEqual(self.db.scalar(select(func.count(CatalogEntity.id))), 1)


if __name__ == "__main__":
    unittest.main()
