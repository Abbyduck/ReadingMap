"""Data migration regression for legacy Book physical facts."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class BookEditionMigrationTests(TransactionTestCase):
    serialized_rollback = True
    migrate_from = [("catalog", "0010_recommendation_facts"), ("reviews", "0001_initial")]
    migrate_to = [("catalog", "0011_book_editions_and_admin_identity"), ("reviews", "0002_edition_drafts_and_guide_material")]

    def test_legacy_book_keeps_all_isbns_in_one_edition(self):
        executor = MigrationExecutor(connection)
        try:
            executor.migrate(self.migrate_from)
            old_apps = executor.loader.project_state(self.migrate_from).apps
            Entity = old_apps.get_model("catalog", "CatalogEntity")
            Work = old_apps.get_model("catalog", "Work")
            Isbn = old_apps.get_model("catalog", "CatalogIsbn")
            entity = Entity.objects.create(
                entity_type="book", display_title="Legacy Book",
                cover_local_path="research_data/legacy.jpg",
                detail_images=[{"source_url": "https://example.com/interior.jpg", "local_path": "research_data/interior.jpg"}],
            )
            Work.objects.create(catalog_entity_id=entity.pk, page_count=32)
            Isbn.objects.create(work_entity_id=entity.pk, isbn_type=13, isbn_val="9780763680862")
            Isbn.objects.create(work_entity_id=entity.pk, isbn_type=10, isbn_val="0763680869")

            executor = MigrationExecutor(connection)
            executor.migrate(self.migrate_to)
            new_apps = executor.loader.project_state(self.migrate_to).apps
            Edition = new_apps.get_model("catalog", "BookEdition")
            migrated_work = new_apps.get_model("catalog", "Work").objects.get(pk=entity.pk)
            edition = Edition.objects.get(work_id=entity.pk)
            self.assertEqual(edition.page_count, 32)
            self.assertEqual(edition.cover_local_path, "research_data/legacy.jpg")
            self.assertEqual(set(edition.isbns.values_list("isbn_val", flat=True)), {"9780763680862", "0763680869"})
            self.assertEqual(migrated_work.detail_images, ["research_data/interior.jpg"])
        finally:
            MigrationExecutor(connection).migrate(self.migrate_to)
