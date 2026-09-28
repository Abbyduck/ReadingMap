from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from .models import (
    ResearchCatalogCandidate, ResearchSource, ResearchSubject, ResearchSubjectRelation,
    ResearchSubjectSource, ReviewActionLog, ReviewBatch, ReviewDataConflict, ReviewItem, ReviewItemSubject,
)
from .services import ReviewDomainError, resolve_conflict, review_write_transaction


class AuditReadOnlyAdmin(admin.ModelAdmin):
    """Decisions must use transactional services, never editable status drop-downs."""
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReviewBatch)
class ReviewBatchAdmin(AuditReadOnlyAdmin):
    list_display = ["id", "source_name", "source_type", "status", "total_items", "resolved_items"]
    list_filter = ["status", "source_type"]
    search_fields = ["source_name", "source_file_path"]


@admin.register(ReviewItem)
class ReviewItemAdmin(AuditReadOnlyAdmin):
    list_display = ["id", "batch", "source_item_key", "status", "decision", "resolved_catalog_entity", "lock_version"]
    list_filter = ["status", "decision", "batch"]
    list_select_related = ["batch", "resolved_catalog_entity"]


@admin.register(ResearchSubject)
class ResearchSubjectAdmin(AuditReadOnlyAdmin):
    list_display = ["id", "proposed_display_title", "proposed_entity_type", "research_status", "resolution_status"]
    list_filter = ["research_status", "resolution_status", "proposed_entity_type"]
    search_fields = ["proposed_display_title", "proposed_title_zh", "proposed_title_en"]


@admin.register(ReviewDataConflict)
class ConflictAdmin(AuditReadOnlyAdmin):
    list_display = ["id", "catalog_entity", "field_path", "status", "updated_at"]
    list_filter = ["status"]
    actions = ["keep_existing", "use_proposed", "ignore_conflict"]

    def _resolve(self, request, queryset, status):
        try:
            with review_write_transaction():
                for conflict in queryset.select_for_update().order_by("pk"):
                    resolve_conflict(conflict, status, f"{request.user.pk}:{request.user.get_username()}", "Django Admin")
        except (ReviewDomainError, ValidationError) as error:
            self.message_user(request, str(error), messages.ERROR)
            return
        self.message_user(request, "冲突已处理并记录操作者。", messages.SUCCESS)

    @admin.action(description="保留正式 Catalog 当前值", permissions=["view"])
    def keep_existing(self, request, queryset):
        self._resolve(request, queryset, "keep_existing")

    @admin.action(description="采用资料提出的新值", permissions=["view"])
    def use_proposed(self, request, queryset):
        self._resolve(request, queryset, "use_proposed")

    @admin.action(description="忽略所选冲突", permissions=["view"])
    def ignore_conflict(self, request, queryset):
        self._resolve(request, queryset, "ignored")


@admin.register(ReviewActionLog)
class ReviewActionLogAdmin(AuditReadOnlyAdmin):
    list_display = ["id", "review_item_id", "action", "actor", "created_at"]
    list_filter = ["action"]
    search_fields = ["actor"]


for model in (ResearchSource, ResearchSubjectRelation, ResearchCatalogCandidate, ResearchSubjectSource, ReviewItemSubject):
    admin.site.register(model, AuditReadOnlyAdmin)
