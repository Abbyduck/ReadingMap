"""Django regression tests. All writes run in the isolated test database."""
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from catalog.models import CatalogCategory, CatalogEntity, CatalogEntityCategory, CollectionItem, ReadingList, ReadingListCreator, ReadingListItem
from research_worker import apply_manifest, prepare, queue, restore_creators, verify
from .models import ResearchSubject, ReviewBatch, ReviewDataConflict, ReviewItem
from .services import (
    ReviewDomainError, StaleReviewError, aggregate_selected_member_lexiles, apply_amazon_capture, apply_jd_capture, apply_official_capture, create_research_relation, create_research_subject,
    extract_review_payload, resolve_review_item, review_item_to_dict, review_write_transaction, stage_detected_parent_hierarchy, summarize_description_classification, update_product_image_selection, update_research_subject,
)
from .amazon_assist import AmazonAssistError, _assert_product_matches, _member_titles_from_product_title, _normalize_search_query
from .jd_assist import (
    JdAssistError, _absolute_image_url, _assert_jd_product_matches, _clean_jd_page_title,
    _gallery_image_urls, _included_titles_from_text, _jd_sku_from_url, _normalize_jd_query,
)
from .official_assist import OfficialAssistError, _is_official_candidate_page, _simon_schuster_cover_url, infer_official_entity_type, open_official_search

SOURCE = "reading_lists/香蕉妈妈__065__2026年香蕉妈妈牛1-高章泛听泛读书单-小红书.json"


class OfficialSearchTests(TestCase):
    @patch("reviews.official_assist._google_search_page")
    @patch("reviews.official_assist._open_search_in_running_browser")
    @patch("reviews.official_assist._browser_is_running", return_value=True)
    @patch("reviews.official_assist._chrome_binary", return_value="chrome")
    def test_reused_browser_opens_search_in_debuggable_session(self, _binary, _running, open_tab, search_page):
        search_page.return_value = {"url": "https://www.google.com/search?q=Flubby+official+publisher", "title": "Flubby"}

        result = open_official_search("Flubby")

        open_tab.assert_called_once_with("https://www.google.com/search?q=Flubby+official+publisher")
        self.assertTrue(result["session_reused"])

    @patch("reviews.official_assist.time.monotonic", side_effect=[0, 13])
    @patch("reviews.official_assist._google_search_page", return_value=None)
    @patch("reviews.official_assist._open_search_in_running_browser")
    @patch("reviews.official_assist._browser_is_running", return_value=True)
    @patch("reviews.official_assist._chrome_binary", return_value="chrome")
    def test_missing_search_tab_is_error_not_false_success(self, _binary, _running, _open_tab, _page, _clock):
        with self.assertRaises(OfficialAssistError):
            open_official_search("Flubby")


class RecommendationEmphasisImportTests(TestCase):
    def payload(self, **extracted):
        return extract_review_payload({
            "raw_title": "Dear Zoo",
            "extracted": {"title": "Dear Zoo", "other_info": {}, **extracted},
        })

    def test_explicit_strong_phrases_are_parsed_and_preserved(self):
        cases = [
            "这个阶段必读", "非常推荐", "强烈推荐", "重点推荐", "首推",
            "这个阶段一定要读", "这个阶段最推荐",
        ]
        for wording in cases:
            with self.subTest(wording=wording):
                payload = self.payload(note=wording)
                self.assertTrue(payload["is_strong_recommendation"])
                self.assertTrue(payload["recommendation_emphasis_text"])

    def test_plain_list_occurrence_does_not_guess_normal_strength(self):
        payload = self.payload(note="适合亲子共读")
        self.assertFalse(payload["is_strong_recommendation"])
        self.assertIsNone(payload["recommendation_emphasis_text"])

    def test_negative_recommendation_wording_is_not_misclassified(self):
        for wording in ("这个阶段不推荐", "并非推荐，只是列出备查", "并非强烈推荐", "不是强烈推荐", "建议读", "可选"):
            with self.subTest(wording=wording):
                payload = self.payload(note=wording)
                self.assertFalse(payload["is_strong_recommendation"])
                self.assertIsNone(payload["recommendation_emphasis_text"])

    def test_structured_original_wording_wins_over_inferred_fragment(self):
        payload = self.payload(
            recommendation_strength=3,
            recommendation_strength_text="这一本在这个阶段非常推荐",
        )
        self.assertTrue(payload["is_strong_recommendation"])
        self.assertEqual(payload["recommendation_emphasis_text"], "这一本在这个阶段非常推荐")

    def test_plain_series_suffix_is_identity_clue_but_parenthetical_series_is_not(self):
        self.assertEqual(self.payload(title="Flubby系列")["proposed_entity_type"], "series")
        self.assertIsNone(self.payload(title="The Adventure of Otto（Ready-to-Read系列）")["proposed_entity_type"])


class ResearchReviewTests(TestCase):
    def setUp(self):
        # A fresh clone has no operator's raw source tree. Keep import/hash/path
        # assertions real by writing deterministic JSON into an isolated root.
        directory = tempfile.TemporaryDirectory(prefix="reading-map-review-test-")
        self.addCleanup(directory.cleanup)
        source_root = Path(directory.name)
        settings_override = override_settings(SOURCE_ROOT=source_root)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        source_override = patch("reviews.services.SOURCE_ROOT", source_root)
        source_override.start()
        self.addCleanup(source_override.stop)
        titles = [
            "Diary of a Wimpy Kid", "How to Train Your Dragon", "Asterix",
            "Percy Jackson", "Because of Winn-Dixie", "Out of My Mind", "Holes",
        ]
        document = {
            "schema_version": "1.0", "document_type": "reading_list",
            "creator": {"name": "香蕉妈妈"},
            "list": {"title": "Research regression fixture"},
            "items": [{
                "sequence": index, "position": index, "raw_title": title,
                "extracted": {"title": title, "ar": {"raw": "3.9"} if index == 5 else None},
            } for index, title in enumerate(titles, 1)],
        }
        source_path = source_root / SOURCE
        source_path.parent.mkdir(parents=True)
        source_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        for index, name in enumerate(["盖兆泉", "廖彩杏", "庆爸", "Susan教英语"], 1):
            creator_source = {"document_type": "reading_list", "creator": {"name": name}, "items": []}
            (source_path.parent / f"creator-{index}.json").write_text(
                json.dumps(creator_source, ensure_ascii=False), encoding="utf-8",
            )
        result = prepare(SOURCE)
        self.batch = ReviewBatch.objects.get(pk=result["batch"]["id"])
        self.item = self.batch.items.get(source_item_key="row:5")
        self.subject = self.item.subject_links.get(subject_role="primary").research_subject

    def manifest(self):
        return {
            "subject_id": self.subject.pk, "source_item_key": self.item.source_item_key,
            "source_content_sha256": self.batch.source_content_sha256,
            "identity": {"entity_type": "book", "display_title": "Because of Winn-Dixie"},
            "sources": [{"key": "publisher", "source_url": "https://example.com/book", "source_title": "Test publisher"}],
            "facts": {"description": {"value": "A sourced test description", "source_keys": ["publisher"]}},
            "ai_inferences": {"syntax": {"value": None, "reason": "No text analyzed"}},
            "research_status": "ready",
        }

    def test_simon_schuster_official_cover_url(self):
        self.assertEqual(
            _simon_schuster_cover_url("https://www.simonandschuster.com/books/Swing-Otto-Swing%21/David-Milgrim/The-Adventures-of-Otto/9781481467902"),
            "https://d28hgpri8am2if.cloudfront.net/book_images/onix/cvr9781481467902/swing-otto-swing-9781481467902_lg.jpg",
        )

    def test_official_type_inference_distinguishes_reading_system_series_and_animation(self):
        reading_system = infer_official_entity_type(
            current_type="series",
            subject_title="Ready-to-Read",
            source_url="https://publisher.example/ready-to-read",
            page_title="Ready-to-Read Book Series",
            description="A reading program with five reading levels for beginning through confident independent readers.",
            page_signals=["Explore the levels", "Ages 3–7"],
        )
        series = infer_official_entity_type(
            current_type="series",
            subject_title="Frog and Dog",
            source_url="https://publisher.example/series/frog-and-dog",
            page_title="Frog and Dog Series",
            description="This series is part of the publisher's early reader line and is about best friends Frog and Dog.",
            page_signals=["FROG AND DOG SERIES"],
        )
        animation = infer_official_entity_type(
            current_type=None,
            subject_title="Bluey",
            source_url="https://publisher.example/watch/bluey",
            page_title="Bluey Animated Series",
            description="Watch episodes from the animated television series.",
            page_signals=["Episodes", "Watch now"],
        )
        self.assertEqual(reading_system["value"], "reading_system")
        self.assertEqual(series["value"], "series")
        self.assertEqual(animation["value"], "animation")

    def test_official_page_candidate_requires_matching_non_search_page(self):
        self.assertTrue(_is_official_candidate_page({
            "type": "page",
            "url": "https://www.scholastic.com/site/en/books/frog-and-dog.html",
            "title": "Frog and Dog | Scholastic",
        }, ["Frog and Dog"]))
        self.assertFalse(_is_official_candidate_page({
            "type": "page",
            "url": "https://www.google.com/search?q=Frog+and+Dog",
            "title": "Frog and Dog - Google Search",
        }, ["Frog and Dog"]))
        self.assertFalse(_is_official_candidate_page({
            "type": "page",
            "url": "https://publisher.example/otto",
            "title": "The Adventures of Otto",
        }, ["Frog and Dog"]))

    def research(self, manifest=None):
        with patch("research_worker.load_json", return_value=manifest or self.manifest()):
            with review_write_transaction():
                result = apply_manifest(self.batch.pk, "test-manifest.json", "test-worker")
        self.item.refresh_from_db()
        self.subject.refresh_from_db()
        return result

    def decide(self, decision="create_new", **extra):
        self.item.refresh_from_db()
        with review_write_transaction():
            return resolve_review_item(self.item.pk, {
                "decision": decision, "expected_version": self.item.lock_version, "actor": "test-human", **extra,
            })

    def test_creator_restore_is_idempotent_and_does_not_import_other_lists(self):
        self.assertEqual(len(restore_creators()["creators"]), 5)
        restore_creators(True)
        restore_creators(True)
        self.assertEqual(ReadingListCreator.objects.count(), 5)
        self.assertEqual(ReadingList.objects.count(), 1)
        self.assertEqual(ReviewBatch.objects.count(), 1)
        self.assertEqual(CatalogEntity.objects.count(), 0)

    def test_import_is_idempotent_preserves_source_and_waits_for_research(self):
        self.assertFalse(prepare(SOURCE)["batch"]["created"])
        self.assertEqual(self.batch.status, "researching")
        self.assertEqual(self.item.status, "pending")
        self.assertEqual(self.batch.items.count(), 7)
        self.assertEqual(self.item.raw_payload["extracted"]["ar"]["raw"], "3.9")
        self.assertEqual(self.item.extracted_payload["source_ar_text"], "3.9")
        self.assertEqual(queue(self.batch.pk)["batch"]["source_content_sha256"], self.batch.source_content_sha256)

    def test_research_does_not_commit_and_invalidates_old_review_snapshot(self):
        version = self.item.lock_version
        self.research()
        self.assertEqual(self.item.status, "ready")
        self.assertGreater(self.item.lock_version, version)
        self.assertEqual(CatalogEntity.objects.count(), 0)
        self.assertEqual(ReadingListItem.objects.count(), 0)
        self.assertTrue(verify(self.batch.pk)["safe_for_human_review"])
        self.assertFalse(verify(self.batch.pk)["research_attempts_complete"])
        with self.assertRaises(StaleReviewError), review_write_transaction():
            resolve_review_item(self.item.pk, {"decision": "create_new", "expected_version": version})

    def test_wrong_source_binding_rejects_old_manifest(self):
        manifest = self.manifest()
        manifest["source_content_sha256"] = "wrong-database-source"
        with self.assertRaises(ValueError):
            self.research(manifest)
        self.subject.refresh_from_db()
        self.assertIsNone(self.subject.facts_json)

    def test_uncited_fact_rolls_back_sources_and_subject(self):
        manifest = self.manifest()
        manifest["facts"]["description"]["source_keys"] = ["missing"]
        with self.assertRaises(ValueError):
            self.research(manifest)
        self.assertEqual(self.subject.source_links.count(), 0)

    def test_partial_research_is_reviewable_and_ignore_retains_source(self):
        manifest = self.manifest()
        manifest["research_status"] = "partial"
        self.research(manifest)
        self.assertEqual(self.item.status, "ready")
        self.decide("ignore")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "ignored")
        self.assertEqual(self.item.raw_payload["raw_title"], "Because of Winn-Dixie")
        self.assertEqual(CatalogEntity.objects.count(), 0)
        with self.assertRaises(ReviewDomainError), review_write_transaction():
            update_research_subject(self.subject, {"proposed_display_title": "Changed after review"})

    def test_description_summary_fills_only_missing_controlled_categories(self):
        self.research()
        self.subject.refresh_from_db()
        source_id = self.subject.source_links.values_list("research_source_id", flat=True).first()
        self.subject.facts_json = {
            "description": {
                "value": "A funny robot story about Otto's adventures with his friends and family.",
                "source_ids": [source_id],
            }
        }
        self.subject.ai_inferences_json = {
            "classification": {
                "material_type": [{"code": "early_reader", "source": "publisher", "confidence": 1.0}],
            }
        }
        self.subject.save(update_fields=["facts_json", "ai_inferences_json"])

        summarize_description_classification(self.subject)

        self.subject.refresh_from_db()
        classification = self.subject.ai_inferences_json["classification"]
        self.assertEqual(classification["material_type"], [{"code": "early_reader", "source": "publisher", "confidence": 1.0}])
        self.assertEqual({row["code"] for row in classification["genre"]}, {"fiction", "adventure", "humor"})
        self.assertEqual({row["code"] for row in classification["theme"]}, {"family", "friendship"})
        self.assertEqual([row["code"] for row in classification["topic"]], ["robots"])
        self.assertNotIn("reading_form", classification)
        self.assertTrue(all(
            row["source"] == "description_summary"
            for category_type, rows in classification.items() if category_type != "material_type"
            for row in rows
        ))
        self.assertEqual(CatalogEntity.objects.count(), 0)
        self.assertEqual(CatalogEntityCategory.objects.count(), 0)

    def test_human_create_commits_once_and_does_not_accept_ai_scores(self):
        self.research()
        self.decide()
        self.decide()
        self.assertEqual(CatalogEntity.objects.count(), 1)
        entity = CatalogEntity.objects.get()
        self.assertEqual(entity.entity_type, "book")
        self.assertEqual(entity.description, "A sourced test description")
        self.assertEqual(ReadingListItem.objects.count(), 1)
        self.assertEqual(ReadingListItem.objects.get().source_ar_text, "3.9")
        with self.assertRaises(ReviewDomainError), review_write_transaction():
            self.subject.refresh_from_db()
            update_research_subject(self.subject, {"facts_json": {}})

    def test_human_confirmed_catalog_draft_overrides_research_before_commit(self):
        self.research()
        with review_write_transaction():
            update_research_subject(self.subject, {
                "proposed_display_title": "Because of Winn-Dixie",
                "facts_json": {
                    **self.subject.facts_json,
                    "description": {"value": "Human edited Catalog Draft", "reviewed_by_human": True},
                },
            })
        self.decide()
        self.assertEqual(CatalogEntity.objects.get().description, "Human edited Catalog Draft")

    def test_human_can_clear_optional_chinese_title(self):
        self.subject.proposed_title_zh = "旧中文名"
        self.subject.save(update_fields=["proposed_title_zh"])

        with review_write_transaction():
            update_research_subject(self.subject, {"proposed_title_zh": None})

        self.subject.refresh_from_db()
        self.assertIsNone(self.subject.proposed_title_zh)

    def test_human_confirmed_illustrator_is_committed_to_work(self):
        self.research()
        with review_write_transaction():
            update_research_subject(self.subject, {
                "facts_json": {
                    **self.subject.facts_json,
                    "illustrator": {"value": "Christian Robinson", "reviewed_by_human": True},
                },
            })

        self.decide()

        self.assertEqual(CatalogEntity.objects.get().work.illustrator_text, "Christian Robinson")

    def test_human_review_commits_only_selected_controlled_categories(self):
        manifest = self.manifest()
        manifest["ai_inferences"]["classification"] = {
            "material_type": [{"code": "chapter_book", "confidence": 0.94, "reason": "Publisher format"}],
            "genre": [
                {"code": "fiction", "confidence": 0.91, "reason": "Synopsis"},
                {"code": "adventure", "confidence": 0.72, "reason": "Plot"},
            ],
            "theme": None,
            "topic": [],
            "reading_form": None,
        }
        self.research(manifest)
        chapter = CatalogCategory.objects.get(category_type="material_type", code="chapter_book")
        fiction = CatalogCategory.objects.get(category_type="genre", code="fiction")
        self.decide(category_decisions=[
            {"category_id": chapter.pk, "is_primary": True},
            {"category_id": fiction.pk, "is_primary": False},
        ])
        links = CatalogEntityCategory.objects.select_related("category").order_by("category__category_type")
        self.assertEqual([(row.category.code, row.is_primary) for row in links], [("fiction", False), ("chapter_book", True)])
        self.assertFalse(any(hasattr(row, "confidence") for row in links))

    def test_research_rejects_category_codes_outside_controlled_taxonomy(self):
        manifest = self.manifest()
        manifest["ai_inferences"]["classification"] = {
            "genre": [{"code": "invented_by_ai", "confidence": 0.9}],
        }
        with self.assertRaises(ValueError):
            self.research(manifest)
        self.subject.refresh_from_db()
        self.assertIsNone(self.subject.facts_json)

    def test_match_keeps_existing_fact_and_queues_conflict(self):
        self.research()
        entity = CatalogEntity.objects.create(entity_type="book", display_title="Because of Winn-Dixie", description="Existing")
        self.decide("match_existing", catalog_entity_id=entity.pk)
        entity.refresh_from_db()
        self.assertEqual(entity.description, "Existing")
        self.assertEqual(CatalogEntity.objects.count(), 1)
        self.assertEqual(ReviewDataConflict.objects.get().proposed_value, "A sourced test description")

    def test_passive_parent_never_becomes_recommendation(self):
        self.research()
        with review_write_transaction():
            parent = create_research_subject({"proposed_entity_type": "series", "proposed_display_title": "Test parent", "review_item_id": self.item.pk, "subject_role": "discovered_parent"})
            create_research_relation({"parent_subject_id": parent.pk, "member_subject_id": self.subject.pk})
        self.decide(include_structure_subject_ids=[parent.pk], structure_decisions=[{"subject_id": parent.pk, "decision": "create_new"}])
        self.assertEqual(CatalogEntity.objects.count(), 2)
        self.assertEqual(CollectionItem.objects.count(), 1)
        self.assertEqual(ReadingListItem.objects.count(), 1)
        self.assertEqual(ReadingListItem.objects.get().catalog_entity.display_title, "Because of Winn-Dixie")

    def test_review_commits_bookshelf_projection_independently_for_each_entity(self):
        self.research()
        with review_write_transaction():
            parent = create_research_subject({
                "proposed_entity_type": "series", "proposed_display_title": "Visible parent",
                "review_item_id": self.item.pk, "subject_role": "discovered_parent",
            })
            create_research_relation({"parent_subject_id": parent.pk, "member_subject_id": self.subject.pk})

        self.decide(
            include_structure_subject_ids=[parent.pk],
            structure_decisions=[{"subject_id": parent.pk, "decision": "create_new"}],
            bookshelf_visibility=[
                {"subject_id": self.subject.pk, "visible": False},
                {"subject_id": parent.pk, "visible": True},
            ],
        )

        parent.refresh_from_db()
        self.subject.refresh_from_db()
        self.assertTrue(parent.resolved_catalog_entity.bookshelf_visible)
        self.assertFalse(self.subject.resolved_catalog_entity.bookshelf_visible)

    def test_nested_collections_store_direct_edges_only(self):
        self.research()
        with review_write_transaction():
            level = create_research_subject({
                "proposed_entity_type": "level", "proposed_display_title": "Oxford Reading Tree Level 1",
                "review_item_id": self.item.pk, "subject_role": "discovered_parent",
            })
            series = create_research_subject({
                "proposed_entity_type": "series", "proposed_display_title": "Oxford Reading Tree",
                "review_item_id": self.item.pk, "subject_role": "discovered_parent",
            })
            create_research_relation({"parent_subject_id": series.pk, "member_subject_id": level.pk})
            create_research_relation({"parent_subject_id": level.pk, "member_subject_id": self.subject.pk})

        self.decide(
            include_structure_subject_ids=[series.pk, level.pk],
            structure_decisions=[
                {"subject_id": series.pk, "decision": "create_new"},
                {"subject_id": level.pk, "decision": "create_new"},
            ],
        )

        series.refresh_from_db()
        level.refresh_from_db()
        self.subject.refresh_from_db()
        direct_edges = set(CollectionItem.objects.values_list("collection_id", "member_entity_id"))
        self.assertEqual(direct_edges, {
            (series.resolved_catalog_entity_id, level.resolved_catalog_entity_id),
            (level.resolved_catalog_entity_id, self.subject.resolved_catalog_entity_id),
        })
        self.assertNotIn((series.resolved_catalog_entity_id, self.subject.resolved_catalog_entity_id), direct_edges)

    def test_admin_can_stage_parent_and_match_existing_before_catalog_commit(self):
        existing = CatalogEntity.objects.create(entity_type="series", display_title="Ready-to-Read")
        admin = get_user_model().objects.create_superuser(email="parent-test@example.com", password="test-only-password")
        client = APIClient()
        client.force_login(admin)

        response = client.post(f"/api/review/items/{self.item.pk}/parents", {
            "child_subject_id": self.subject.pk,
            "proposed_entity_type": "series",
            "proposed_display_title": "Ready-to-Read",
            "proposed_title_en": "Ready-to-Read",
        }, format="json")

        self.assertEqual(response.status_code, 201, response.data)
        parent = ResearchSubject.objects.get(pk=response.data["parent_subject_id"])
        self.assertTrue(self.item.subject_links.filter(research_subject=parent, subject_role="discovered_parent").exists())
        detail_response = client.get(f"/api/review/subjects/{parent.pk}")
        self.assertEqual(detail_response.status_code, 200, detail_response.data)
        self.assertEqual(detail_response.data["id"], parent.pk)
        relation = parent.member_relations.get(member_subject=self.subject, relation_type="contains")
        self.assertEqual(relation.review_status, "proposed")
        self.assertEqual(parent.candidates.get().catalog_entity_id, existing.pk)
        self.assertEqual(CatalogEntity.objects.count(), 1)
        delete_response = client.delete(f"/api/review/relations/{relation.pk}")
        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(parent.member_relations.filter(pk=relation.pk).exists())

    def test_parent_staging_rejects_non_collection_parent_type(self):
        admin = get_user_model().objects.create_superuser(email="parent-type-test@example.com", password="test-only-password")
        client = APIClient()
        client.force_login(admin)
        response = client.post(f"/api/review/items/{self.item.pk}/parents", {
            "child_subject_id": self.subject.pk,
            "proposed_entity_type": "book",
            "proposed_display_title": "Not a parent collection",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CatalogEntity.objects.count(), 0)

    def test_ready_to_read_parent_research_stages_full_official_hierarchy_idempotently(self):
        self.subject.proposed_entity_type = "set"
        self.subject.facts_json = {
            "official_level": {"value": "Ready-to-Read Pre-Level 1"},
            "series_name": {"value": "The Adventures of Otto"},
        }
        self.subject.save(update_fields=["proposed_entity_type", "facts_json"])

        with review_write_transaction():
            first_ids, first_relations = stage_detected_parent_hierarchy(self.item, "test-human")
        with review_write_transaction():
            second_ids, second_relations = stage_detected_parent_hierarchy(self.item, "test-human")

        self.assertEqual(first_ids, second_ids)
        self.assertEqual(first_relations, second_relations)
        self.assertEqual(len(first_ids), 7)
        self.assertEqual(len(first_relations), 7)
        self.assertEqual(self.item.subject_links.filter(subject_role="discovered_parent").count(), 7)
        self.assertEqual(CatalogEntity.objects.count(), 0)
        root = ResearchSubject.objects.get(proposed_display_title="Ready-to-Read")
        pre_level = ResearchSubject.objects.get(proposed_display_title="Ready-to-Read · Pre-Level 1")
        otto = ResearchSubject.objects.get(proposed_display_title="The Adventures of Otto")
        self.assertEqual(root.proposed_entity_type, "reading_system")
        self.assertEqual(root.member_relations.filter(review_status="confirmed").count(), 6)
        self.assertTrue(root.member_relations.filter(member_subject=otto, evidence_type="source_fact").exists())
        self.assertFalse(pre_level.member_relations.filter(member_subject=otto).exists())
        self.assertTrue(otto.member_relations.filter(member_subject=self.subject, evidence_type="source_fact").exists())

        self.item.refresh_from_db()
        self.decide(
            include_structure_subject_ids=first_ids,
            structure_decisions=[{"subject_id": subject_id, "decision": "create_new"} for subject_id in first_ids],
        )
        self.assertEqual(CatalogEntity.objects.count(), 8)
        self.assertEqual(CollectionItem.objects.count(), 7)
        root.refresh_from_db()
        self.assertEqual(root.resolved_catalog_entity.collection.volume_count, 5)

    def test_ready_to_read_parent_research_accepts_series_clue_in_title(self):
        self.subject.proposed_entity_type = "set"
        self.subject.proposed_display_title = "The Adventures of Otto（Ready-to-Read系列）"
        self.subject.facts_json = {}
        self.subject.save(update_fields=["proposed_entity_type", "proposed_display_title", "facts_json"])

        with review_write_transaction():
            subject_ids, relation_ids = stage_detected_parent_hierarchy(self.item, "test-human")

        self.assertEqual(len(subject_ids), 7)
        self.assertEqual(len(relation_ids), 7)

    def test_nested_parent_selection_requires_complete_direct_chain(self):
        self.research()
        with review_write_transaction():
            level = create_research_subject({
                "proposed_entity_type": "level", "proposed_display_title": "Pre-Level 1",
                "review_item_id": self.item.pk, "subject_role": "discovered_parent",
            })
            series = create_research_subject({
                "proposed_entity_type": "series", "proposed_display_title": "Ready-to-Read",
                "review_item_id": self.item.pk, "subject_role": "discovered_parent",
            })
            create_research_relation({"parent_subject_id": series.pk, "member_subject_id": level.pk})
            create_research_relation({"parent_subject_id": level.pk, "member_subject_id": self.subject.pk})
        with self.assertRaises(ReviewDomainError):
            self.decide(
                include_structure_subject_ids=[series.pk],
                structure_decisions=[{"subject_id": series.pk, "decision": "create_new"}],
            )
        self.assertEqual(CatalogEntity.objects.count(), 0)

    def test_unrelated_structure_rejected_with_full_rollback(self):
        self.research()
        other = ResearchSubject.objects.create(proposed_entity_type="series", proposed_display_title="Unrelated")
        with self.assertRaises(ReviewDomainError):
            self.decide(include_structure_subject_ids=[other.pk])
        self.assertEqual(CatalogEntity.objects.count(), 0)
        self.assertEqual(ReadingListItem.objects.count(), 0)
        self.item.refresh_from_db()
        self.assertIsNone(self.item.decision)

    def test_guest_cannot_read_review_data(self):
        response = APIClient().get("/api/review/items")
        self.assertIn(response.status_code, [401, 403])

    def test_admin_can_edit_source_copy_without_mutating_raw_provenance(self):
        admin = get_user_model().objects.create_superuser(email="source-copy@example.com", password="test-only-password")
        client = APIClient()
        client.force_login(admin)
        original_raw = self.item.raw_payload
        version = self.item.lock_version

        response = client.patch(f"/api/review/items/{self.item.pk}", {
            "expected_version": version,
            "comment": "适合亲子共读，也适合自主阅读",
            "note": "音频：扫码音频；漫画；原图第1页第2行",
        }, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.item.refresh_from_db()
        self.assertEqual(self.item.raw_payload, original_raw)
        self.assertEqual(self.item.extracted_payload["comment"], "适合亲子共读，也适合自主阅读")
        self.assertEqual(self.item.extracted_payload["note"], "音频：扫码音频；漫画")
        self.assertEqual(self.item.lock_version, version + 1)
        self.assertEqual(self.item.action_logs.get(action="source_copy_edited").details_json["fields"], ["comment", "note"])

        stale = client.patch(f"/api/review/items/{self.item.pk}", {
            "expected_version": version,
            "note": "不应保存",
        }, format="json")
        self.assertEqual(stale.status_code, 409, stale.data)
        self.item.refresh_from_db()
        self.assertEqual(self.item.extracted_payload["note"], "音频：扫码音频；漫画")

    def test_admin_can_edit_strong_mark_without_comment_or_note(self):
        admin = get_user_model().objects.create_superuser(email="source-strength@example.com", password="test-only-password")
        client = APIClient()
        client.force_login(admin)

        response = client.patch(f"/api/review/items/{self.item.pk}", {
            "expected_version": self.item.lock_version,
            "is_strong_recommendation": True,
        }, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.item.refresh_from_db()
        self.assertTrue(self.item.extracted_payload["is_strong_recommendation"])

        text_response = client.patch(f"/api/review/items/{self.item.pk}", {
            "expected_version": self.item.lock_version,
            "recommendation_emphasis_text": "强烈推荐",
        }, format="json")
        self.assertEqual(text_response.status_code, 200, text_response.data)
        self.item.refresh_from_db()
        clear_response = client.patch(f"/api/review/items/{self.item.pk}", {
            "expected_version": self.item.lock_version,
            "is_strong_recommendation": False,
        }, format="json")
        self.assertEqual(clear_response.status_code, 200, clear_response.data)
        self.item.refresh_from_db()
        self.assertFalse(self.item.extracted_payload["is_strong_recommendation"])
        self.assertIsNone(self.item.extracted_payload["recommendation_emphasis_text"])

    def test_open_legacy_tab_can_save_strength_without_empty_payload_error(self):
        admin = get_user_model().objects.create_superuser(email="legacy-strength@example.com", password="test-only-password")
        client = APIClient()
        client.force_login(admin)
        response = client.patch(f"/api/review/items/{self.item.pk}", {
            "expected_version": self.item.lock_version,
            "recommendation_strength": 3,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.item.refresh_from_db()
        self.assertTrue(self.item.extracted_payload["is_strong_recommendation"])

    def test_legacy_item_derives_explicit_strength_from_original_note(self):
        raw_payload = dict(self.item.raw_payload)
        raw_extracted = dict(raw_payload.get("extracted") or {})
        raw_extracted["note"] = "音频：扫码音频；强烈推荐"
        raw_payload["extracted"] = raw_extracted
        stored = dict(self.item.extracted_payload)
        stored.pop("recommendation_strength", None)
        stored.pop("recommendation_strength_text", None)
        stored.pop("is_strong_recommendation", None)
        stored.pop("recommendation_emphasis_text", None)
        stored["note"] = "音频：扫码音频；强烈推荐"
        self.item.raw_payload = raw_payload
        self.item.extracted_payload = stored
        self.item.save(update_fields=["raw_payload", "extracted_payload"])

        payload = review_item_to_dict(self.item)["extracted_payload"]

        self.assertTrue(payload["is_strong_recommendation"])
        self.assertEqual(payload["recommendation_emphasis_text"], "强烈推荐")

    def test_catalog_draft_patch_preserves_newer_official_facts_and_rejects_stale_snapshot(self):
        admin = get_user_model().objects.create_superuser(email="draft-patch@example.com", password="test-only-password")
        client = APIClient()
        client.force_login(admin)
        self.subject.facts_json = {
            "description": {"value": "Official synopsis", "source_ids": [88]},
            "official_page_signals": {"value": ["Series", "Ages 4-6"], "source_ids": [88]},
        }
        self.subject.save(update_fields=["facts_json"])
        self.item.refresh_from_db()

        response = client.put(f"/api/review/items/{self.item.pk}/subjects/{self.subject.pk}/draft", {
            "expected_version": self.item.lock_version,
            "proposed_display_title": self.subject.proposed_display_title,
            "proposed_entity_type": "book",
            "fact_values": {"author": "Kate DiCamillo"},
            "clear_fact_keys": [],
        }, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.subject.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.subject.facts_json["description"]["value"], "Official synopsis")
        self.assertEqual(self.subject.facts_json["official_page_signals"]["value"], ["Series", "Ages 4-6"])
        self.assertEqual(self.subject.facts_json["author"]["value"], "Kate DiCamillo")
        log = self.item.action_logs.get(action="catalog_draft_edited")
        self.assertEqual(log.details_json["fact_keys"], ["author"])

        stale = client.put(f"/api/review/items/{self.item.pk}/subjects/{self.subject.pk}/draft", {
            "expected_version": self.item.lock_version - 1,
            "fact_values": {"publisher": "Stale publisher"},
        }, format="json")
        self.assertEqual(stale.status_code, 409, stale.data)
        self.subject.refresh_from_db()
        self.assertNotIn("publisher", self.subject.facts_json)

    @patch("reviews.views.open_amazon_search")
    def test_amazon_search_uses_saved_primary_title(self, open_search):
        open_search.return_value = {
            "query": self.subject.proposed_display_title,
            "search_url": "https://www.amazon.com/s?k=Because+of+Winn-Dixie",
            "session_reused": False,
        }
        admin = get_user_model().objects.create_superuser(email="amazon-test@example.com", password="test-only-password")
        client = APIClient()
        client.force_login(admin)
        response = client.post(f"/api/review/items/{self.item.pk}/amazon-search", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        open_search.assert_called_once_with(self.subject.proposed_title_en or self.subject.proposed_display_title)

    @patch("reviews.views.open_official_search")
    def test_official_search_uses_primary_title(self, open_search):
        open_search.return_value = {
            "query": "Because of Winn-Dixie official publisher",
            "search_url": "https://www.google.com/search?q=Because+of+Winn-Dixie+official+publisher",
            "session_reused": True,
            "current_url": "https://www.google.com/search?q=Because+of+Winn-Dixie+official+publisher",
            "page_title": "Google",
        }
        admin = get_user_model().objects.create_superuser(email="official-search@example.com", password="test-only-password")
        client = APIClient()
        client.force_login(admin)

        response = client.post(f"/api/review/items/{self.item.pk}/official-search", {}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        open_search.assert_called_once_with(self.subject.proposed_title_en or self.subject.proposed_display_title)

    @patch("reviews.views.capture_current_official")
    def test_current_official_page_is_merged_into_research_draft(self, capture):
        capture.return_value = {
            "source_url": "https://publisher.example/because-of-winn-dixie",
            "source_title": "Because of Winn-Dixie | Publisher",
            "source_type": "publisher_official",
            "facts": {"description": "Official synopsis", "publisher": "Candlewick"},
        }
        admin = get_user_model().objects.create_superuser(email="official-capture@example.com", password="test-only-password")
        client = APIClient()
        client.force_login(admin)

        response = client.post(f"/api/review/items/{self.item.pk}/official-capture", {}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.subject.refresh_from_db()
        self.assertEqual(self.subject.facts_json["description"]["value"], "Official synopsis")
        self.assertEqual(self.subject.facts_json["publisher"]["value"], "Candlewick")
        log = self.item.action_logs.get(action="official_source_captured")
        self.assertEqual(log.details_json["captured_facts"]["description"], "Official synopsis")

    def test_amazon_search_query_prefers_leading_english_title(self):
        self.assertEqual(
            _normalize_search_query("The Adventure of Otto 机器人奥托的冒险(Ready to Read系列)"),
            "The Adventure of Otto",
        )
        self.assertEqual(_normalize_search_query("Frog and Dog(漫画)"), "Frog and Dog")

    @patch("reviews.views.open_jd_search")
    def test_jd_search_uses_shared_title_priority(self, open_search):
        self.subject.proposed_title_zh = "机器人奥托的冒险"
        self.subject.save(update_fields=["proposed_title_zh"])
        open_search.return_value = {
            "query": self.subject.proposed_title_zh,
            "search_url": "https://search.jd.com/Search?keyword=机器人奥托的冒险",
            "session_reused": True,
        }
        admin = get_user_model().objects.create_superuser(email="jd-test@example.com", password="test-only-password")
        client = APIClient()
        client.force_login(admin)
        response = client.post(f"/api/review/items/{self.item.pk}/jd-search", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        open_search.assert_called_once_with(self.subject.proposed_title_en or self.subject.proposed_display_title)

    @patch("reviews.views.amazon_browser_status")
    def test_browser_session_status_uses_current_review_subject(self, session_status):
        session_status.return_value = {
            "provider": "amazon", "connected": True, "state": "search_results",
            "current_url": "https://www.amazon.com/s?k=Because+of+Winn-Dixie",
            "product_title": "", "product_id": "", "capture_ready": False,
            "message": "搜索结果已就绪",
        }
        admin = get_user_model().objects.create_superuser(email="browser-status@example.com", password="test-only-password")
        client = APIClient()
        client.force_login(admin)

        response = client.get(f"/api/review/browser-session/status?item_id={self.item.pk}&provider=amazon")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["state"], "search_results")
        session_status.assert_called_once_with(self.subject.proposed_title_en or self.subject.proposed_display_title)

    def test_jd_url_and_product_match_helpers(self):
        self.assertEqual(_normalize_jd_query("  机器人奥托的冒险  "), "机器人奥托的冒险")
        self.assertEqual(_jd_sku_from_url("https://item.jd.com/123456789.html"), "123456789")
        _assert_jd_product_matches("机器人奥托的冒险", {"title": "【正版】机器人奥托的冒险 全套6册"})
        _assert_jd_product_matches(
            "机器人奥托的冒险",
            {"title": "机器人奥拓的冒险6册 The Adventures of Otto 分级阅读系列 Ready to Read Level 1"},
            ["The Adventure of Otto"],
        )
        with self.assertRaises(JdAssistError):
            _assert_jd_product_matches("青蛙和小狗", {"title": "【正版】机器人奥托的冒险 全套6册"})

    def test_jd_new_carousel_images_are_promoted_to_original_size_and_deduplicated(self):
        cover = "https://img10.360buyimg.com/n1/jfs/t1/1/2/cover.jpg"
        carousel_values = [
            "https://img10.360buyimg.com/pcpubliccms/s228x228_jfs/t1/1/2/cover.jpg.avif",
            "https://img10.360buyimg.com/pcpubliccms/s228x228_jfs/t1/1/2/inside.jpg.avif",
        ]

        class FakeImage:
            def __init__(self, value): self.value = value
            def get_attribute(self, name): return self.value if name == "src" else None

        class FakeDriver:
            def find_elements(self, _by, selector):
                return [FakeImage(value) for value in carousel_values] if selector == ".image-carousel-content .item img.image" else []

        self.assertEqual(
            _absolute_image_url(carousel_values[1]),
            "https://img10.360buyimg.com/pcpubliccms/jfs/t1/1/2/inside.jpg",
        )
        self.assertEqual(
            _gallery_image_urls(FakeDriver(), cover),
            ["https://img10.360buyimg.com/pcpubliccms/jfs/t1/1/2/inside.jpg"],
        )

    def test_jd_current_page_title_and_set_catalog_helpers(self):
        page_title = (
            "机器人奥拓的冒险6册 The Adventures of Otto 分级阅读系列"
            "【行情 报价 价格 评测】-京东"
        )
        self.assertEqual(
            _clean_jd_page_title(page_title),
            "机器人奥拓的冒险6册 The Adventures of Otto 分级阅读系列",
        )
        description = """图书信息
6册目录
1.See Otto;
2.See Pip Point;
3.Swing, Otto, Swing!;
4.See Santa Nap;
5.Ride, Otto, Ride!;
6.Go, Otto, Go!
作者简介
David Milgrim"""
        self.assertEqual(
            _included_titles_from_text(description),
            ["See Otto", "See Pip Point", "Swing, Otto, Swing!", "See Santa Nap", "Ride, Otto, Ride!", "Go, Otto, Go!"],
        )

    def test_amazon_capture_rejects_wrong_review_item(self):
        page = {
            "title": "Amazon.com: The Adventures of Otto Collector's Set",
            "url": "https://www.amazon.com/dp/148149984X?keywords=The+Adventure+of+Otto",
        }
        _assert_product_matches("The Adventure of Otto", page)
        with self.assertRaises(AmazonAssistError):
            _assert_product_matches("Frog and Dog", page)

    def test_amazon_capture_stays_in_review_area_with_source_provenance(self):
        self.subject.proposed_entity_type = "set"
        self.subject.save(update_fields=["proposed_entity_type"])
        images = [
            {"source_url": "https://images.example/cover.jpg", "local_path": "research_data/amazon/0763680869/cover.jpg", "role": "cover", "selected": True},
            {"source_url": "https://images.example/detail-1.jpg", "local_path": "research_data/amazon/0763680869/detail-01.jpg", "role": "detail", "selected": True},
            {"source_url": "https://images.example/detail-2.jpg", "local_path": "research_data/amazon/0763680869/detail-02.jpg", "role": "detail", "selected": True},
        ]
        capture = {
            "asin": "0763680869",
            "title": "Because of Winn-Dixie",
            "source_url": "https://www.amazon.com/dp/0763680869",
            "downloaded_assets": images,
            "facts": {
                "amazon_title": "Because of Winn-Dixie",
                "asin": "0763680869",
                "isbns": ["9780763680862"],
                "publisher": "Candlewick",
                "extra_info": "Amazon 评分：4.8 / 5\n商品尺寸：10 x 8 in",
                "product_images": images,
                "included_titles": ["See Otto", "See Pip Point"],
            },
        }
        with review_write_transaction():
            apply_amazon_capture(self.subject, capture, "test-human")
        self.subject.refresh_from_db()
        self.item.refresh_from_db()
        source = self.subject.source_links.get().research_source
        self.assertEqual(source.source_type, "amazon_product")
        self.assertEqual(self.subject.facts_json["isbns"]["value"], ["9780763680862"])
        self.assertEqual(self.subject.facts_json["isbns"]["source_ids"], [source.pk])
        self.assertNotIn("amazon_title", self.subject.facts_json)
        self.assertNotIn("asin", self.subject.facts_json)
        self.assertEqual(len(self.subject.facts_json["product_images"]["value"]), 3)
        self.assertEqual(self.subject.research_status, "partial")
        self.assertEqual(self.item.status, "ready")
        self.assertEqual(
            list(self.subject.member_relations.order_by("position").values_list("member_subject__proposed_display_title", flat=True)),
            ["See Otto", "See Pip Point"],
        )
        self.assertEqual(CatalogEntity.objects.count(), 0)
        self.assertEqual(ReadingListItem.objects.count(), 0)

        with review_write_transaction():
            self.subject.refresh_from_db()
            update_product_image_selection(
                self.subject,
                [images[0]["source_url"], images[1]["source_url"]],
                images[1]["source_url"],
            )
        self.subject.refresh_from_db()
        selected_images = self.subject.facts_json["product_images"]["value"]
        self.assertEqual([image["role"] for image in selected_images], ["detail", "cover", "detail"])
        self.assertFalse(selected_images[2]["selected"])
        self.assertEqual(self.subject.facts_json["cover"]["value"], images[1]["source_url"])
        self.assertEqual(
            self.subject.facts_json["detail_images"]["value"],
            [
                {"source_url": images[0]["source_url"], "local_path": images[0]["local_path"]},
                {"source_url": images[1]["source_url"], "local_path": images[1]["local_path"]},
            ],
        )

        self.decide()
        entity = CatalogEntity.objects.get()
        self.assertEqual(entity.entity_type, "set")
        self.assertEqual(entity.extra_info, "Amazon 评分：4.8 / 5\n商品尺寸：10 x 8 in")
        self.assertEqual(entity.cover_url, images[1]["source_url"])
        self.assertEqual(entity.cover_local_path, images[1]["local_path"])
        self.assertEqual(entity.detail_images, [
            {"source_url": images[0]["source_url"], "local_path": images[0]["local_path"]},
            {"source_url": images[1]["source_url"], "local_path": images[1]["local_path"]},
        ])
        self.assertEqual(ReadingListItem.objects.count(), 1)
        self.assertEqual(ReadingListItem.objects.get().catalog_entity_id, entity.pk)

    def test_jd_capture_keeps_platform_source_and_conflicting_value(self):
        amazon_capture = {
            "source_url": "https://www.amazon.com/dp/0763680869",
            "downloaded_assets": [],
            "facts": {"publisher": "Candlewick"},
        }
        jd_capture = {
            "source_url": "https://item.jd.com/123456789.html",
            "downloaded_assets": [],
            "facts": {
                "publisher": "某国内出版社",
                "reading_age": "3-6岁",
                "retailer_category": "Picture Books(绘本)",
            },
        }
        with review_write_transaction():
            apply_amazon_capture(self.subject, amazon_capture, "test-human")
            apply_jd_capture(self.subject, jd_capture, "test-human")
        self.subject.refresh_from_db()
        sources = {link.research_source.source_type for link in self.subject.source_links.select_related("research_source")}
        self.assertEqual(sources, {"amazon_product", "jd_product"})
        self.assertEqual(self.subject.facts_json["publisher"]["value"], "Candlewick")
        self.assertEqual(self.subject.facts_json["jd_publisher"]["value"], "某国内出版社")
        self.assertEqual(self.subject.facts_json["reading_age"]["value"], "3-6岁")
        self.assertEqual(self.subject.facts_json["retailer_category"]["value"], "Picture Books(绘本)")
        material_types = self.subject.ai_inferences_json["classification"]["material_type"]
        self.assertEqual(material_types, [{
            "code": "picture_book",
            "confidence": 1.0,
            "reason": "京东商品详情明确标注“童书类型：Picture Books(绘本)”",
            "source": "jd",
        }])
        self.assertTrue(self.item.action_logs.filter(action="jd_product_captured").exists())

    def test_official_capture_stays_staged_and_preserves_retailer_conflict(self):
        self.subject.facts_json = {
            "publisher": {"value": "Simon Spotlight", "source_ids": [99]},
            "reading_age": {"value": "4 - 6", "source_ids": [99]},
        }
        self.subject.save(update_fields=["facts_json"])
        apply_official_capture(self.subject, {
            "source_url": "https://publisher.example/9781481499842",
            "source_title": "Official publisher page",
            "facts": {
                "publisher": "Simon Spotlight",
                "official_age": "3 - 5",
                "reading_age": "3 - 5",
            },
        })
        self.subject.refresh_from_db()
        source = self.subject.source_links.get(research_source__source_url="https://publisher.example/9781481499842").research_source
        self.assertEqual(source.source_type, "publisher_official")
        self.assertIn(source.pk, self.subject.facts_json["publisher"]["source_ids"])
        self.assertEqual(self.subject.facts_json["official_age"]["value"], "3 - 5")
        self.assertEqual(self.subject.facts_json["official_reading_age"]["value"], "3 - 5")
        self.assertIsNone(self.subject.resolved_catalog_entity_id)

    def test_collection_lexile_range_uses_selected_direct_members(self):
        with review_write_transaction():
            parent = create_research_subject({
                "proposed_entity_type": "set", "proposed_display_title": "Selected set",
                "review_item_id": self.item.pk, "subject_role": "discovered_parent",
            })
            lower = create_research_subject({
                "proposed_entity_type": "book", "proposed_display_title": "Lower member",
                "facts_json": {"lexile": {"value": "BR80L", "source_ids": [11]}},
                "review_item_id": self.item.pk, "subject_role": "discovered_member",
            })
            upper = create_research_subject({
                "proposed_entity_type": "book", "proposed_display_title": "Upper member",
                "facts_json": {"lexile": {"value": "210L", "source_ids": [12]}},
                "review_item_id": self.item.pk, "subject_role": "discovered_member",
            })
            create_research_relation({"parent_subject_id": parent.pk, "member_subject_id": lower.pk})
            create_research_relation({"parent_subject_id": parent.pk, "member_subject_id": upper.pk})
            aggregate_selected_member_lexiles(parent, [lower.pk, upper.pk])
        parent.refresh_from_db()
        self.assertEqual(parent.facts_json["lexile_min"]["value"], 80)
        self.assertEqual(parent.facts_json["lexile_max"]["value"], 210)
        self.assertEqual(parent.facts_json["lexile_range"]["value"], "80–210L")

    def test_official_capture_can_discover_confirmed_direct_structure(self):
        self.subject.proposed_entity_type = "set"
        self.subject.proposed_display_title = "Official boxed set"
        self.subject.save(update_fields=["proposed_entity_type", "proposed_display_title"])
        apply_official_capture(self.subject, {
            "source_url": "https://publisher.example/boxed-set",
            "source_title": "Official boxed set",
            "facts": {"language": "English"},
            "members": [{
                "display_title": "Official member one",
                "entity_type": "book",
                "position": 1,
                "source_url": "https://publisher.example/member-one",
                "facts": {
                    "cover": "https://publisher.example/member-one.jpg",
                    "publisher": "Publisher",
                    "lexile": "120L",
                },
            }],
        })
        relation = self.subject.member_relations.select_related("member_subject").get()
        member = relation.member_subject
        self.assertEqual(relation.evidence_type, "source_fact")
        self.assertEqual(relation.review_status, "confirmed")
        self.assertEqual(float(relation.confidence), 1.0)
        self.assertEqual(member.facts_json["cover"]["value"], "https://publisher.example/member-one.jpg")
        self.assertEqual(member.facts_json["lexile"]["value"], "120L")
        self.assertEqual(member.facts_json["language"]["value"], "en")
        self.assertEqual(member.facts_json["language"]["inherited_from_subject_id"], self.subject.pk)
        self.subject.refresh_from_db()
        self.assertEqual(self.subject.facts_json["language"]["value"], "en")
        self.assertTrue(self.item.subject_links.filter(research_subject=member, subject_role="discovered_member").exists())
        self.assertEqual(CatalogEntity.objects.count(), 0)

    def test_amazon_boxed_set_title_extracts_direct_members(self):
        self.assertEqual(
            _member_titles_from_product_title(
                "The Adventures of Otto Collector's Set (Boxed Set): See Otto; See Pip Point; Go, Otto, Go!"
            ),
            ["See Otto", "See Pip Point", "Go, Otto, Go!"],
        )

    def test_structure_needs_explicit_identity_choice(self):
        self.research()
        with review_write_transaction():
            parent = create_research_subject({"proposed_entity_type": "series", "proposed_display_title": "Test parent", "review_item_id": self.item.pk, "subject_role": "discovered_parent"})
        with self.assertRaises(ReviewDomainError):
            self.decide(include_structure_subject_ids=[parent.pk])
        self.assertEqual(CatalogEntity.objects.count(), 0)

    def test_api_submission_and_read_only_formal_results(self):
        self.research()
        admin = get_user_model().objects.create_superuser(email="review-test@example.com", password="test-only-password")
        client = APIClient()
        client.force_login(admin)
        response = client.post(f"/api/review/items/{self.item.pk}/decision", {
            "decision": "create_new", "expected_version": self.item.lock_version,
            "include_structure_subject_ids": [], "structure_decisions": [],
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        entity_id = response.data["resolved_catalog_entity_id"]
        recommendation_id = response.data["committed_reading_list_item_id"]
        for model, pk in [("catalogentity", entity_id), ("readinglistitem", recommendation_id)]:
            url = f"/django-admin/catalog/{model}/{pk}/change/"
            self.assertEqual(client.get(url).status_code, 200)
            self.assertEqual(client.post(url, {}).status_code, 403)
        self.assertEqual(ReadingListItem.objects.count(), 1)

    def test_original_file_reader_permissions_content_and_path_boundary(self):
        url = f"/api/review/batches/{self.batch.pk}/source"
        client = APIClient()
        self.assertIn(client.get(url).status_code, [401, 403])
        reader = get_user_model().objects.create_user(email="source-reader@example.com", is_staff=False)
        client.force_login(reader)
        self.assertEqual(client.get(url).status_code, 403)
        reader.is_staff = True
        reader.save(update_fields=["is_staff"])
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["document"]["creator"]["name"], "香蕉妈妈")
        self.assertEqual(len(response.data["document"]["items"]), 7)
        self.assertEqual(response.data["document"]["items"][4], self.item.raw_payload)
        self.assertTrue(response.data["matches_import"])
        self.assertIn('"schema_version"', response.data["raw_text"])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.batch.source_content_sha256 = "changed"
        self.batch.save(update_fields=["source_content_sha256"])
        self.assertFalse(client.get(url).data["matches_import"])
        self.batch.source_file_path = "../backend/config/settings.py"
        self.batch.save(update_fields=["source_file_path"])
        self.assertEqual(client.get(url).status_code, 400)
        self.assertEqual(CatalogEntity.objects.count(), 0)
