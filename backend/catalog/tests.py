from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from unittest.mock import patch
from pathlib import Path
import tempfile
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import (
    ALLOWED_ENTITY_TYPES, COLLECTION_ENTITY_TYPES, BookEdition, CatalogCategory, CatalogEntity, CatalogEntityCategory, CatalogIsbn,
    CatalogSourceStat, ReadingList, ReadingListCreator, ReadingListItem,
)
from catalog.services import (
    CatalogDomainError,
    aggregate_stage_entities,
    assign_entity_categories,
    assign_importance_levels,
    add_isbn, find_by_isbn, search_catalog,
)

from reviews.models import ResearchSource, ReviewItem


class DatabaseBrowserTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            "admin@example.com", "Wisteria!River@42", is_staff=True
        )

    def test_database_browser_requires_staff(self):
        self.assertIn(self.client.get("/api/database/tables").status_code, {401, 403})
        user = User.objects.create_user("reader@example.com", "Wisteria!River@42")
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get("/api/database/tables").status_code, 403)

    def test_staff_can_list_tables_and_paginate_rows(self):
        CatalogEntity.objects.create(entity_type="book", display_title="Database Browser Book")
        self.client.force_authenticate(self.admin)

        inventory = self.client.get("/api/database/tables")
        self.assertEqual(inventory.status_code, 200, inventory.data)
        self.assertIn("catalog_entities", [table["name"] for table in inventory.data["tables"]])

        detail = self.client.get("/api/database/tables/catalog_entities?page=1&page_size=10")
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertIn("id", [column["name"] for column in detail.data["columns"]])
        self.assertEqual(detail.data["rows"][0]["display_title"], "Database Browser Book")

    def test_unknown_table_is_not_queried(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/database/tables/not_a_real_table")
        self.assertEqual(response.status_code, 404)

    def test_staff_can_toggle_bookshelf_visibility_and_default_is_hidden(self):
        entity = CatalogEntity.objects.create(entity_type="book", display_title="Shelf toggle")
        self.assertFalse(entity.bookshelf_visible)
        self.client.force_authenticate(self.admin)

        response = self.client.patch(
            f"/api/catalog/entities/{entity.pk}", {"bookshelf_visible": True}, format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["bookshelf_visible"])
        entity.refresh_from_db()
        self.assertTrue(entity.bookshelf_visible)

    def test_catalog_uses_seven_entity_types_and_animation_is_not_a_collection(self):
        self.assertEqual(ALLOWED_ENTITY_TYPES, {"book", "animation", "reading_system", "series", "level", "set", "franchise"})
        self.assertIn("reading_system", COLLECTION_ENTITY_TYPES)
        self.assertNotIn("animation", COLLECTION_ENTITY_TYPES)
        entity = CatalogEntity.objects.create(entity_type="reading_system", display_title="Acorn")
        self.assertEqual(entity.collection.catalog_entity_id, entity.pk)
        franchise = CatalogEntity.objects.create(entity_type="franchise", display_title="Example IP")
        self.assertEqual(franchise.collection.catalog_entity_id, franchise.pk)
        animation = CatalogEntity.objects.create(entity_type="animation", display_title="Example Animation")
        self.assertFalse(hasattr(animation, "work"))
        self.assertFalse(hasattr(animation, "collection"))
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/catalog/entities", {"entity_type": "animation", "display_title": "API Animation"}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["entity_type"], "animation")


class EditionAndAdminTests(TestCase):
    def setUp(self):
        self.book = CatalogEntity.objects.create(entity_type="book", display_title="A Book")
        self.admin = User.objects.create_user("edition-admin@example.com", "Wisteria!River@42", is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_sparse_edition_isbn_uniqueness_and_recommendation_work(self):
        edition = BookEdition.objects.create(work=self.book.work)
        self.assertIsNone(edition.page_count)
        isbn = add_isbn(self.book.pk, "978-0-7636-8086-2", edition.pk)
        self.assertEqual(isbn.edition_id, edition.pk)
        other_edition = BookEdition.objects.create(work=self.book.work)
        with self.assertRaises(CatalogDomainError):
            add_isbn(self.book.pk, "9780763680862", other_edition.pk)
        self.assertEqual(find_by_isbn("9780763680862").pk, self.book.pk)
        other = CatalogEntity.objects.create(entity_type="book", display_title="Other Book")
        with self.assertRaises(CatalogDomainError):
            add_isbn(other.pk, "9780763680862")
        creator = ReadingListCreator.objects.create(name="Creator")
        reading_list = ReadingList.objects.create(creator=creator, title="List")
        item = ReadingListItem.objects.create(reading_list=reading_list, catalog_entity=self.book, recommended_edition=edition)
        self.assertEqual(item.recommended_edition_id, edition.pk)
        with self.assertRaises(ValidationError):
            ReadingListItem(reading_list=reading_list, catalog_entity=other, recommended_edition=edition).full_clean()

    def test_work_search_and_catalog_fields(self):
        self.book.work.author_text = "Kate DiCamillo"
        self.book.work.illustrator_text = "Chris Van Dusen"
        self.book.work.translator_text = "李先生"
        self.book.work.detail_images = ["research_data/interior.jpg"]
        self.book.work.save()
        self.book.guide_markdown = "## 阅读方法\n\n先一起读。"
        self.book.fiction_type = "fiction"
        self.book.save()
        for query in ("Kate DiCamillo", "Chris Van Dusen", "李先生"):
            self.assertEqual(search_catalog(query).get().pk, self.book.pk)
        with self.assertRaises(ValidationError):
            CatalogEntity(entity_type="book", display_title="Bad", fiction_type="maybe").full_clean()
        data = self.client.get(f"/api/catalog/entities/{self.book.pk}").data
        self.assertEqual(data["work"]["detail_images"], ["research_data/interior.jpg"])
        self.assertEqual(data["guide_markdown"], "## 阅读方法\n\n先一起读。")
        self.assertEqual(data["fiction_type"], "fiction")

    def test_catalog_image_fields_reject_external_urls(self):
        with self.assertRaises(ValidationError):
            BookEdition.objects.create(work=self.book.work, cover_local_path="https://example.com/cover.jpg")
        self.book.work.detail_images = ["https://example.com/interior.jpg"]
        with self.assertRaises(ValidationError):
            self.book.work.save()
        self.book.work.refresh_from_db()
        response = self.client.patch(f"/api/catalog/entities/{self.book.pk}", {
            "work": {"detail_images": ["https://example.com/interior.jpg"]},
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_catalog_asset_requires_admin_and_serves_only_local_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "backend").mkdir()
            (root / "research_data").mkdir()
            (root / "research_data" / "cover.jpg").write_bytes(b"local-image")
            (root / "research_data" / "notes.txt").write_text("private note")
            with override_settings(BASE_DIR=root / "backend"):
                self.assertIn(APIClient().get("/api/catalog-assets/cover.jpg").status_code, {401, 403})
                response = self.client.get("/api/catalog-assets/cover.jpg")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b"".join(response.streaming_content), b"local-image")
                self.assertEqual(self.client.get("/api/catalog-assets/notes.txt").status_code, 404)

    def test_empty_collection_and_declared_total_are_independent(self):
        franchise = CatalogEntity.objects.create(entity_type="franchise", display_title="Shared IP")
        self.assertEqual(franchise.collection.items.count(), 0)
        franchise.collection.volume_count = 12
        franchise.collection.save()
        from catalog.services import add_collection_item
        add_collection_item(franchise.pk, self.book.pk)
        franchise.collection.refresh_from_db()
        self.assertEqual(franchise.collection.volume_count, 12)
        self.assertEqual(franchise.collection.items.count(), 1)

    def test_admin_detail_loads_work_edition_structure_classification_and_guide(self):
        edition = BookEdition.objects.create(work=self.book.work, cover_local_path="research_data/cover.jpg", page_count=32)
        add_isbn(self.book.pk, "9780763680862", edition.pk)
        parent = CatalogEntity.objects.create(entity_type="series", display_title="A Series")
        from catalog.services import add_collection_item
        add_collection_item(parent.pk, self.book.pk)
        category = CatalogCategory.objects.get(category_type="theme", code="friendship")
        assign_entity_categories(self.book, [{"category_id": category.pk, "is_primary": True}])
        self.book.guide_markdown = "## 共读"
        self.book.save(update_fields=["guide_markdown"])
        data = self.client.get(f"/api/catalog/entities/{self.book.pk}").data
        self.assertEqual(data["editions"][0]["isbns"][0]["isbn_val"], "9780763680862")
        self.assertEqual(data["editions"][0]["page_count"], 32)
        self.assertEqual(data["parents"][0]["id"], parent.pk)
        self.assertEqual(data["categories"][0]["code"], "friendship")
        self.assertEqual(data["guide_markdown"], "## 共读")
        self.assertIsNone(data["cover_url"])

    @patch("catalog.admin_capture._capture")
    def test_admin_capture_requires_confirmation_and_does_not_create_review_item(self, capture):
        capture.return_value = {"source_url": "https://publisher.example/book", "facts": {"author": "New Author", "description": "New synopsis"}}
        response = self.client.post(f"/api/catalog/entities/{self.book.pk}/admin-capture", {"provider": "official", "scope": "page"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.book.refresh_from_db()
        self.assertIsNone(self.book.description)
        self.assertEqual(ReviewItem.objects.count(), 0)
        confirmed = self.client.post(f"/api/catalog/entities/{self.book.pk}/admin-confirm", {
            "token": response.data["token"], "selected_fields": ["work.author_text"],
        }, format="json")
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.book.refresh_from_db()
        self.assertIsNone(self.book.description)
        self.assertEqual(self.book.work.author_text, "New Author")
        self.assertEqual(ReviewItem.objects.count(), 0)

    @patch("catalog.admin_capture._capture")
    def test_admin_unselected_edition_capture_does_not_create_empty_version(self, capture):
        capture.return_value = {"source_url": "https://publisher.example/book", "facts": {"page_count": 32}}
        candidate = self.client.post(f"/api/catalog/entities/{self.book.pk}/admin-capture", {
            "provider": "official", "scope": "edition",
        }, format="json")
        self.assertEqual(candidate.status_code, 200, candidate.data)
        response = self.client.post(f"/api/catalog/entities/{self.book.pk}/admin-confirm", {
            "token": candidate.data["token"], "selected_fields": [],
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(BookEdition.objects.count(), 0)

    def test_admin_guide_material_stays_draft_until_confirmed(self):
        response = self.client.post(f"/api/catalog/entities/{self.book.pk}/guide-material", {
            "raw_content": "原始资料\n如何使用", "source_title": "个人笔记",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.book.refresh_from_db()
        self.assertIsNone(self.book.guide_markdown)
        self.assertEqual(ResearchSource.objects.get(source_type="manual_guide").raw_content, "原始资料\n如何使用")
        confirmed = self.client.post(f"/api/catalog/entities/{self.book.pk}/admin-confirm", {
            "token": response.data["token"], "selected_fields": ["entity.guide_markdown"], "guide_markdown": "## 人工确认\n\n如何使用",
        }, format="json")
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.book.refresh_from_db()
        self.assertEqual(self.book.guide_markdown, "## 人工确认\n\n如何使用")


class CategoryTaxonomyTests(TestCase):
    def test_seed_contains_only_five_dimensions_and_required_hierarchy(self):
        self.assertEqual(
            set(CatalogCategory.objects.values_list("category_type", flat=True)),
            {"material_type", "genre", "theme", "topic", "reading_form"},
        )
        self.assertEqual(CatalogCategory.objects.get(category_type="theme", code="fear").parent.code, "emotion")
        self.assertEqual(CatalogCategory.objects.get(category_type="topic", code="pets").parent.code, "animals")

    def test_parent_must_share_dimension_and_taxonomy_has_at_most_two_levels(self):
        genre = CatalogCategory.objects.get(category_type="genre", code="fiction")
        invalid = CatalogCategory(category_type="theme", code="invalid", name_zh="错误", parent=genre)
        with self.assertRaises(ValidationError):
            invalid.full_clean()
        fear = CatalogCategory.objects.get(category_type="theme", code="fear")
        too_deep = CatalogCategory(category_type="theme", code="too_deep", name_zh="过深", parent=fear)
        with self.assertRaises(ValidationError):
            too_deep.full_clean()

    def test_assignment_allows_only_one_primary_per_dimension(self):
        entity = CatalogEntity.objects.create(entity_type="book", display_title="分类测试")
        fiction = CatalogCategory.objects.get(category_type="genre", code="fiction")
        humor = CatalogCategory.objects.get(category_type="genre", code="humor")
        assign_entity_categories(entity, [{"category_id": fiction.pk, "is_primary": True}])
        assign_entity_categories(entity, [{"category_id": humor.pk, "is_primary": True}])
        self.assertFalse(CatalogEntityCategory.objects.get(catalog_entity=entity, category=fiction).is_primary)
        self.assertTrue(CatalogEntityCategory.objects.get(catalog_entity=entity, category=humor).is_primary)
        with self.assertRaises(CatalogDomainError):
            assign_entity_categories(entity, [
                {"category_id": fiction.pk, "is_primary": True},
                {"category_id": humor.pk, "is_primary": True},
            ])


class StageImportanceAcceptanceTests(TestCase):
    def setUp(self):
        self.book = CatalogEntity.objects.create(entity_type="book", display_title="Dear Zoo")

    def creator(self, name):
        return ReadingListCreator.objects.create(name=name)

    def recommendation(self, creator, stage, strong=False, position=1, text=None, entity=None, reading_list=None):
        reading_list = reading_list or ReadingList.objects.create(creator=creator, title=f"{creator.name} {stage}", stage_label=stage)
        return ReadingListItem.objects.create(
            reading_list=reading_list,
            catalog_entity=entity or self.book,
            position=position,
            is_strong_recommendation=strong,
            recommendation_emphasis_text=text,
        )

    def test_case_1_same_creator_keeps_stage_specific_strengths(self):
        creator = self.creator("达人A")
        first = self.recommendation(creator, "2-3岁")
        second = self.recommendation(creator, "3-4岁", True)

        younger = aggregate_stage_entities("2-3岁")
        older = aggregate_stage_entities("3-4岁")

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(ReadingListItem.objects.filter(catalog_entity=self.book).count(), 2)
        self.assertFalse(younger[0]["recommendation_meta"]["strong_now"])
        self.assertTrue(younger[0]["recommendation_meta"]["strong_in_scope"])
        self.assertEqual(younger[0]["recommendation_score"], 1.28)
        self.assertTrue(older[0]["recommendation_meta"]["strong_now"])
        self.assertEqual(older[0]["recommendation_score"], 1.58)
        self.assertEqual(younger[0]["recommendation_meta"]["creator_count"], 1)
        self.assertEqual(younger[0]["recommendation_meta"]["list_count"], 2)

    def test_case_2_future_strong_does_not_insert_entity_into_current_stage(self):
        self.recommendation(self.creator("达人A"), "3-4岁", True)
        self.assertEqual(aggregate_stage_entities("2-3岁"), [])

    def test_case_2_three_creators_collapse_to_one_entity(self):
        for name in ("达人A", "达人B", "达人C"):
            self.recommendation(self.creator(name), "2-3岁")

        rows = aggregate_stage_entities("2-3岁")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["catalog_entity_id"], self.book.pk)
        self.assertEqual(rows[0]["recommendation_meta"]["creator_count"], 3)
        self.assertEqual(rows[0]["recommendation_score"], 1.4755)
        self.assertLess(1.22, rows[0]["recommendation_score"])

    def test_case_3_high_score_uses_exact_v1_formula_and_is_featured(self):
        for name, strong in (("达人A", True), ("达人B", False), ("达人C", False)):
            self.recommendation(self.creator(name), "2-3岁", strong)
        CatalogSourceStat.objects.create(
            catalog_entity=self.book,
            source_name="amazon",
            rating=4.8,
            rating_max=5,
            rating_count=12000,
        )

        row = aggregate_stage_entities("2-3岁", my_rating_by_entity={self.book.pk: 5})[0]

        self.assertEqual(row["recommendation_score"], 1.9755)
        self.assertEqual(row["importance_score"], 82.9)
        self.assertEqual(row["importance_level"], "featured")

    def test_case_4_ordinary_recommendation_has_one_point(self):
        self.recommendation(self.creator("达人A"), "2-3岁")

        row = aggregate_stage_entities("2-3岁")[0]

        self.assertEqual(row["recommendation_score"], 1.0)
        self.assertEqual(row["importance_score"], 22.0)

    def test_case_5_creator_count_is_never_accumulated_across_stages(self):
        creators = [self.creator(f"达人{letter}") for letter in "ABC"]
        for creator in creators:
            self.recommendation(creator, "2-3岁")
        self.recommendation(creators[0], "3-4岁", True)

        self.assertEqual(aggregate_stage_entities("2-3岁")[0]["creator_count"], 3)
        self.assertEqual(aggregate_stage_entities("3-4岁")[0]["creator_count"], 3)

    def test_same_creator_duplicate_rows_count_once(self):
        creator = self.creator("达人A")
        reading_list = ReadingList.objects.create(creator=creator, title="重复数据", stage_label="2-3岁")
        ReadingListItem.objects.create(reading_list=reading_list, catalog_entity=self.book)
        ReadingListItem.objects.create(reading_list=reading_list, catalog_entity=self.book, is_strong_recommendation=True)

        row = aggregate_stage_entities("2-3岁")[0]

        self.assertEqual(row["creator_count"], 1)
        self.assertEqual(row["recommendation_meta"]["list_count"], 1)
        self.assertEqual(row["recommendation_score"], 1.5)

    def test_case_6_extra_list_weaker_than_extra_creator(self):
        creator = self.creator("达人A")
        self.recommendation(creator, "2-3岁")
        self.recommendation(creator, "3-4岁")
        same_creator = aggregate_stage_entities("2-3岁")[0]["recommendation_score"]
        self.recommendation(self.creator("达人B"), "3-4岁")
        another_creator = aggregate_stage_entities("2-3岁")[0]["recommendation_score"]
        self.assertEqual(same_creator, 1.08)
        self.assertGreater(another_creator - same_creator, .08)

    def test_case_7_creator_scope_does_not_mix_other_routes(self):
        creator = self.creator("达人A")
        self.recommendation(creator, "2-3岁")
        baseline = aggregate_stage_entities("2-3岁", creator_id=creator.id)[0]["recommendation_score"]
        for index in range(3):
            self.recommendation(self.creator(f"其他路线{index}"), "3-4岁", True)
        self.assertEqual(aggregate_stage_entities("2-3岁", creator_id=creator.id)[0]["recommendation_score"], baseline)

    def test_case_8_recommendation_evidence_contains_stages_and_creators(self):
        creator = self.creator("香蕉妈妈")
        self.recommendation(creator, "2-3岁")
        self.recommendation(creator, "3-4岁", True, text="强烈推荐")
        self.recommendation(self.creator("庆爸"), "2-3岁")
        evidence = aggregate_stage_entities("2-3岁")[0]["recommendations"]
        self.assertEqual(len(evidence), 3)
        self.assertEqual([row["stage_label"] for row in evidence if row["creator_id"] == creator.id], ["2-3岁", "3-4岁"])
        self.assertTrue(any(row["is_strong_recommendation"] for row in evidence))

    def test_bulk_scope_query_does_not_repeat_per_entity(self):
        creator = self.creator("达人A")
        for index in range(6):
            entity = CatalogEntity.objects.create(entity_type="book", display_title=f"Book {index}")
            self.recommendation(creator, "2-3岁", entity=entity)
        with CaptureQueriesContext(connection) as queries:
            aggregate_stage_entities("2-3岁")
        relation_reads = [query for query in queries if "FROM `reading_list_items`" in query["sql"] or 'FROM "reading_list_items"' in query["sql"]]
        self.assertEqual(len(relation_reads), 2)

    def test_api_returns_relationship_fields_and_dynamic_score_without_persistence(self):
        self.recommendation(self.creator("达人A"), "2-3岁", True, text="这个阶段必读")

        list_response = self.client.get("/api/reading-lists")
        map_response = self.client.get("/api/reading-map/entities", {"stage_label": "2-3岁"})

        self.assertEqual(list_response.status_code, 200, list_response.data)
        self.assertTrue(list_response.data[0]["items"][0]["is_strong_recommendation"])
        self.assertEqual(list_response.data[0]["items"][0]["recommendation_emphasis_text"], "这个阶段必读")
        self.assertEqual(map_response.status_code, 200, map_response.data)
        self.assertEqual(map_response.data["entities"][0]["recommendation_score"], 1.5)
        self.assertEqual(map_response.data["entities"][0]["recommendation_meta"]["list_count"], 1)
        self.assertEqual(map_response.data["entities"][0]["importance_score"], 33.0)
        self.assertNotIn("importance_score", {field.name for field in CatalogEntity._meta.fields})

    def test_importance_level_count_rules_cover_all_thresholds(self):
        expectations = {
            6: (1, 5, 0),
            7: (2, 3, 2),
            16: (3, 6, 7),
            31: (5, 9, 17),
            60: (5, 18, 37),
        }
        for count, expected_counts in expectations.items():
            with self.subTest(count=count):
                rows = [
                    {"catalog_entity_id": index + 1, "importance_score": count - index}
                    for index in range(count)
                ]
                assign_importance_levels(rows)
                actual_counts = tuple(
                    sum(row["importance_level"] == level for row in rows)
                    for level in ("featured", "normal", "compact")
                )
                self.assertEqual(actual_counts, expected_counts)
