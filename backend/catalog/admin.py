"""Inspect committed Catalog results without bypassing the review workflow."""
from django.contrib import admin
from .models import CatalogEntity, Work, Collection, CollectionItem, ReadingListCreator, ReadingList, ReadingListItem


class CatalogReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CatalogEntity)
class CatalogEntityAdmin(CatalogReadOnlyAdmin):
    list_display = ["id", "display_title", "entity_type", "updated_at"]
    search_fields = ["display_title", "title_zh", "title_en"]
    list_filter = ["entity_type"]


@admin.register(ReadingListCreator)
class CreatorAdmin(CatalogReadOnlyAdmin):
    list_display = ["id", "name", "tagline"]
    search_fields = ["name"]


@admin.register(ReadingList)
class ReadingListAdmin(CatalogReadOnlyAdmin):
    list_display = ["id", "title", "creator"]
    list_select_related = ["creator"]


@admin.register(ReadingListItem)
class ReadingListItemAdmin(CatalogReadOnlyAdmin):
    list_display = ["id", "reading_list", "catalog_entity", "position", "is_strong_recommendation", "recommendation_emphasis_text", "source_ar_text", "source_lexile_text"]
    list_filter = ["reading_list", "is_strong_recommendation"]
    list_select_related = ["reading_list", "catalog_entity"]


for model in (Work, Collection, CollectionItem):
    admin.site.register(model, CatalogReadOnlyAdmin)
