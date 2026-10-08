"""Database regressions for human-confirmed Structure staging."""
from django.test import TestCase

from .models import (
    ReviewBatch, ReviewItem, ResearchSubject, ReviewItemSubject, ResearchSubjectRelation,
)
from .services import review_write_transaction
from .structure_staging import stage_structure_candidates
from .official_assist import _official_source


class StructureStagingTests(TestCase):
    def setUp(self):
        self.batch = ReviewBatch.objects.create(source_type="manual", import_key="structure-stage-fixture")
        self.item = ReviewItem.objects.create(batch=self.batch, source_item_key="fixture:1", raw_payload={})
        self.parent = ResearchSubject.objects.create(
            proposed_entity_type="series", proposed_display_title="Flubby",
            facts_json={"description": {"value": "Existing Draft"}})
        ReviewItemSubject.objects.create(review_item=self.item, research_subject=self.parent,
                                         subject_role="primary")

    def stage(self, members, declared_count=None):
        with review_write_transaction():
            result = stage_structure_candidates(
                item=self.item, parent=self.parent, members=members,
                declared_count=declared_count, actor="test")
        self.parent.refresh_from_db()
        return result

    def test_only_direct_review_relations_are_staged(self):
        result = self.stage([
            {"title": "Book A", "url": "https://example.org/books/a", "confidence": .8},
            {"title": "Book B", "url": "https://example.org/books/b", "confidence": .8},
        ], declared_count=6)
        self.assertEqual(len(result["relation_ids"]), 2)
        self.assertEqual(ResearchSubjectRelation.objects.count(), 2)
        self.assertEqual(self.parent.facts_json["description"]["value"], "Existing Draft")
        self.assertEqual(self.parent.facts_json["volume_count"]["value"], 6)
        self.assertEqual(self.parent.member_relations.filter(relation_type="contains").count(), 2)

    def test_repeated_staging_does_not_duplicate_relations(self):
        member = [{"title": "Book A", "url": "https://example.org/books/a", "confidence": .8}]
        first = self.stage(member)
        second = self.stage(member)
        self.assertEqual(first["relation_ids"], second["relation_ids"])
        self.assertEqual(ResearchSubjectRelation.objects.count(), 1)

    def test_same_title_different_urls_remain_distinct(self):
        first = [{"title": "Book A", "url": "https://example.org/books/a1"}]
        second = [{"title": "Book A", "url": "https://example.org/books/a2"}]
        self.stage(first)
        self.stage(second)
        self.assertEqual(ResearchSubjectRelation.objects.count(), 2)

    def test_declared_total_never_derived_from_recognized_members(self):
        self.stage([{"title": "Book A"}], declared_count=36)
        self.assertEqual(self.parent.facts_json["volume_count"]["value"], 36)
        self.stage([{"title": "Book B"}], declared_count=36)
        self.assertEqual(self.parent.facts_json["volume_count"]["value"], 36)
        self.assertEqual(self.parent.member_relations.count(), 2)

    def test_confirmed_member_url_is_available_for_optional_enrichment(self):
        result = self.stage([{"title": "Book A", "url": "https://publisher.example/books/a"}])
        relation = ResearchSubjectRelation.objects.get(pk=result["relation_ids"][0])
        source = _official_source(relation.member_subject)
        self.assertIsNotNone(source)
        self.assertEqual(source.source_url, "https://publisher.example/books/a")

    def test_retailer_member_url_is_not_mislabeled_as_official(self):
        result = self.stage([{"title": "Book A", "url": "https://www.amazon.com/dp/B000000"}])
        relation = ResearchSubjectRelation.objects.get(pk=result["relation_ids"][0])
        self.assertIsNone(_official_source(relation.member_subject))
