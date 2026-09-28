from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app


class CatalogApiSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)

        def session_override():
            with Session(self.engine) as session:
                yield session

        app.dependency_overrides[get_db] = session_override
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.engine.dispose()

    def post(self, path: str, payload: dict) -> dict:
        response = self.client.post(path, json=payload)
        self.assertLess(response.status_code, 300, response.text)
        return response.json()

    def test_catalog_reading_list_and_child_flows(self) -> None:
        book = self.post(
            "/api/catalog/entities",
            {"entity_type": "book", "display_title": "Book A", "title_en": "Book A", "work": {"lexile_code": "350L"}},
        )
        series = self.post("/api/catalog/entities", {"entity_type": "series", "display_title": "Series A"})
        tree = self.post(f"/api/collections/{series['id']}/items", {"member_entity_id": book["id"], "position": 1})
        self.assertEqual(tree["children"][0]["id"], book["id"])

        creator = self.post("/api/creators", {"name": "达人A"})
        reading_list = self.post("/api/reading-lists", {"creator_id": creator["id"], "title": "2.5–4岁书单"})
        detail = self.post(
            f"/api/reading-lists/{reading_list['id']}/items",
            {"catalog_entity_id": book["id"], "recommended_age_min_months": 30, "recommended_age_max_months": 48, "source_lexile_text": "200L-500L"},
        )
        self.assertEqual(detail["items"][0]["entity"]["work"]["lexile_code"], "350L")
        self.assertEqual(detail["items"][0]["source_lexile_text"], "200L-500L")

        child = self.post("/api/children", {"name": "孩子"})
        response = self.client.put(
            f"/api/children/{child['id']}/entities/{book['id']}",
            json={"independent_reading_override": False},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["effective_source"], "child_override")

    def test_review_import_and_match_endpoint(self) -> None:
        creator = self.post("/api/creators", {"name": "审核达人"})
        reading_list = self.post("/api/reading-lists", {"creator_id": creator["id"], "title": "审核路线"})
        entity = self.post("/api/catalog/entities", {"entity_type": "series", "display_title": "小猪小象", "aliases": ["小猪和小象"]})
        document = {
            "document_type": "reading_list",
            "list": {"title": "待审核书单"},
            "items": [{"position": 1, "raw_title": "小猪和小象", "extracted": {"title": "小猪和小象"}, "analysis": {"possible_entity_type": "series"}}],
        }
        with tempfile.TemporaryDirectory() as directory:
            source_root = Path(directory)
            (source_root / "list.json").write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            with patch("app.services.review_service.SOURCE_ROOT", source_root):
                imported = self.post(
                    "/api/review/batches/import",
                    {"source_file_path": "list.json", "target_reading_list_id": reading_list["id"]},
                )
        response = self.client.get(f"/api/review/items?batch_id={imported['batch']['id']}")
        self.assertEqual(response.status_code, 200, response.text)
        item = response.json()[0]
        resolved = self.post(
            f"/api/review/items/{item['id']}/decision",
            {"decision": "match_existing", "catalog_entity_id": entity["id"], "expected_version": item["lock_version"]},
        )
        self.assertEqual(resolved["resolved_catalog_entity_id"], entity["id"])
        detail = self.client.get(f"/api/reading-lists/{reading_list['id']}")
        self.assertEqual([row["catalog_entity_id"] for row in detail.json()["items"]], [entity["id"]])


if __name__ == "__main__":
    unittest.main()
