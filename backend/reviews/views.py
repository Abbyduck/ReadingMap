from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ResearchSubject, ReviewBatch, ReviewDataConflict, ReviewEditionDraft, ReviewItem
from .amazon_assist import AmazonAssistError, amazon_browser_status, capture_amazon_product, open_amazon_search
from .jd_assist import JdAssistError, capture_jd_product, jd_browser_status, open_jd_search
from .official_assist import (
    OfficialAssistError, capture_current_official, capture_official_subjects,
    official_browser_status, open_official_search,
)
from .serializers import (
    BulkMatchSerializer, ConflictResolveSerializer, EditionDraftDecisionSerializer, GuideDraftSerializer, GuideMaterialSerializer,
    ResearchRelationSerializer, ResearchSubjectDraftSerializer, ResearchSubjectSerializer,
    ParentStructureCreateSerializer, ProductImageSelectionSerializer, ReviewBatchImportSerializer, ReviewBatchSerializer,
    ReviewDataConflictSerializer, ReviewDecisionSerializer, ReviewItemSourceCopySerializer,
    SelectedStructureResearchSerializer,
)
from .services import (
    DuplicateCandidateError, ReviewDomainError, StaleReviewError, create_research_relation, delete_research_relation,
    create_research_subject, import_source_file, refresh_catalog_candidates, resolve_conflict,
    aggregate_selected_member_lexiles, apply_amazon_capture, apply_jd_capture, apply_official_capture, resolve_review_item, review_item_to_dict, review_write_transaction, subject_to_dict,
    update_product_image_selection, update_research_subject, update_review_subject_draft, read_batch_source, stage_parent_structure,
    stage_detected_parent_hierarchy, stage_edition_capture, stage_structure_capture, stage_guide_material,
    summarize_description_classification, update_review_item_source_copy,
)


from .structure_extractors import PageSnapshot, extract_structure, extract_url_list
from .structure_extractors.image import analyze_image
from .structure_staging import stage_structure_candidates
from .browser_structure import snapshot_current_page, start_region_selection, poll_region_selection, list_target_pages
from .serializers import StructurePreviewInputSerializer, StructureStageInputSerializer


class ReviewAPI(APIView):
    permission_classes = [IsAdminUser]

    def handle_exception(self, exc):
        if isinstance(exc, (ReviewDomainError, DjangoValidationError, IntegrityError)):
            message = "This operation conflicts with existing data" if isinstance(exc, IntegrityError) else str(exc)
            converted = APIException(message)
            converted.status_code = 409 if isinstance(exc, (StaleReviewError, DuplicateCandidateError)) else 400
            exc = converted
        return super().handle_exception(exc)

    def validated(self, serializer_class, **kwargs):
        serializer = serializer_class(data=self.request.data, **kwargs)
        serializer.is_valid(raise_exception=True)
        return dict(serializer.validated_data)

    def actor(self):
        return str(self.request.user.pk) + ":" + self.request.user.get_username()


class BatchList(ReviewAPI):
    def get(self, request):
        batches = ReviewBatch.objects.order_by("-id")
        if request.query_params.get("status"):
            batches = batches.filter(status=request.query_params["status"])
        return Response(ReviewBatchSerializer(batches, many=True).data)


class BatchImport(ReviewAPI):
    def post(self, request):
        values = self.validated(ReviewBatchImportSerializer)
        with review_write_transaction():
            batch, created = import_source_file(**values)
        return Response({"created": created, "batch": ReviewBatchSerializer(batch).data})


class BatchSource(ReviewAPI):
    def get(self, request, batch_id):
        batch = get_object_or_404(ReviewBatch, pk=batch_id)
        return Response(read_batch_source(batch), headers={"Cache-Control": "private, no-store"})


class ItemList(ReviewAPI):
    def get(self, request):
        items = ReviewItem.objects.order_by("-batch_id", "position", "id")
        try:
            limit = int(request.query_params.get("limit", 200))
            if not 1 <= limit <= 500:
                raise ValueError
            if request.query_params.get("batch_id"):
                items = items.filter(batch_id=int(request.query_params["batch_id"]))
        except ValueError as exc:
            raise ReviewDomainError("Invalid batch_id or limit (1–500)") from exc
        if request.query_params.get("status"):
            items = items.filter(status=request.query_params["status"])
        return Response([review_item_to_dict(item) for item in items[:limit]])


class ItemDetail(ReviewAPI):
    def get(self, request, item_id):
        return Response(review_item_to_dict(get_object_or_404(ReviewItem, pk=item_id)))

    def patch(self, request, item_id):
        values = self.validated(ReviewItemSourceCopySerializer)
        with review_write_transaction():
            item = get_object_or_404(ReviewItem.objects.select_for_update(), pk=item_id)
            update_review_item_source_copy(item, values, self.actor())
        return Response(review_item_to_dict(item))


def _subject_search_values(subject: ResearchSubject, override: str = "") -> tuple[str, list[str]]:
    values = [
        override,
        subject.proposed_title_en,
        subject.proposed_display_title,
        subject.proposed_title_zh,
        *(subject.proposed_aliases or []),
    ]
    normalized = []
    for value in values:
        text = " ".join(str(value or "").split())
        if text and text not in normalized:
            normalized.append(text)
    if not normalized:
        raise ReviewDomainError("当前审核对象没有可搜索的名称")
    return normalized[0], normalized[1:]


def _primary_subject(item_id: int) -> ResearchSubject:
    item = get_object_or_404(ReviewItem, pk=item_id)
    primary = item.subject_links.filter(subject_role="primary").select_related("research_subject").first()
    if primary is None:
        raise ReviewDomainError("当前审核项没有主 Research Subject")
    return primary.research_subject


class BrowserSessionStatus(ReviewAPI):
    def get(self, request):
        try:
            item_id = int(request.query_params.get("item_id", ""))
        except ValueError as error:
            raise ReviewDomainError("请提供有效的 item_id") from error
        provider = request.query_params.get("provider", "amazon").casefold()
        if provider not in {"amazon", "jd", "official"}:
            raise ReviewDomainError("provider 必须是 amazon、jd 或 official")
        subject = _primary_subject(item_id)
        query, alternates = _subject_search_values(subject)
        if provider == "official":
            return Response(official_browser_status(query, alternates))
        if provider == "jd":
            return Response(jd_browser_status(query, alternates))
        return Response(amazon_browser_status(query))


class ItemAmazonSearch(ReviewAPI):
    def post(self, request, item_id):
        subject = _primary_subject(item_id)
        title, _ = _subject_search_values(subject, request.data.get("query", ""))
        try:
            result = open_amazon_search(title)
        except AmazonAssistError as error:
            raise ReviewDomainError(str(error)) from error
        return Response(result)


class ItemAmazonCapture(ReviewAPI):
    def post(self, request, item_id):
        item = get_object_or_404(ReviewItem, pk=item_id)
        primary = item.subject_links.filter(subject_role="primary").select_related("research_subject").first()
        if primary is None:
            raise ReviewDomainError("当前审核项没有主 Research Subject")
        title, _ = _subject_search_values(primary.research_subject)
        try:
            capture = capture_amazon_product(title)
        except AmazonAssistError as error:
            raise ReviewDomainError(str(error)) from error
        with review_write_transaction():
            subject = get_object_or_404(ResearchSubject.objects.select_for_update(), pk=primary.research_subject_id)
            apply_amazon_capture(subject, capture, self.actor())
        item.refresh_from_db()
        return Response({
            "capture": {
                "source_url": capture.get("source_url"),
                "identifier": capture.get("asin"),
                "title": capture.get("title"),
                "image_count": len(capture.get("downloaded_assets") or []),
            },
            "item": review_item_to_dict(item),
        })


class ItemJdSearch(ReviewAPI):
    def post(self, request, item_id):
        subject = _primary_subject(item_id)
        title, _ = _subject_search_values(subject, request.data.get("query", ""))
        try:
            result = open_jd_search(title)
        except JdAssistError as error:
            raise ReviewDomainError(str(error)) from error
        return Response(result)


class ItemJdCapture(ReviewAPI):
    def post(self, request, item_id):
        item = get_object_or_404(ReviewItem, pk=item_id)
        primary = item.subject_links.filter(subject_role="primary").select_related("research_subject").first()
        if primary is None:
            raise ReviewDomainError("当前审核项没有主 Research Subject")
        subject = primary.research_subject
        title, alternate_titles = _subject_search_values(subject)
        try:
            capture = capture_jd_product(title, alternate_titles)
        except JdAssistError as error:
            raise ReviewDomainError(str(error)) from error
        with review_write_transaction():
            subject = get_object_or_404(ResearchSubject.objects.select_for_update(), pk=primary.research_subject_id)
            apply_jd_capture(subject, capture, self.actor())
        item.refresh_from_db()
        return Response({
            "capture": {
                "source_url": capture.get("source_url"),
                "identifier": capture.get("sku"),
                "title": capture.get("title"),
                "image_count": len(capture.get("downloaded_assets") or []),
            },
            "item": review_item_to_dict(item),
        })


class ItemOfficialSearch(ReviewAPI):
    def post(self, request, item_id):
        subject = _primary_subject(item_id)
        title, _ = _subject_search_values(subject, request.data.get("query", ""))
        try:
            result = open_official_search(title)
        except OfficialAssistError as error:
            raise ReviewDomainError(str(error)) from error
        return Response(result)


class ItemOfficialCapture(ReviewAPI):
    def post(self, request, item_id):
        item = get_object_or_404(ReviewItem, pk=item_id)
        primary = item.subject_links.filter(subject_role="primary").select_related("research_subject").first()
        if primary is None:
            raise ReviewDomainError("当前审核项没有主 Research Subject")
        subject = primary.research_subject
        title, alternate_titles = _subject_search_values(subject)
        try:
            capture = capture_current_official(subject, title, alternate_titles)
        except OfficialAssistError as error:
            raise ReviewDomainError(str(error)) from error
        with review_write_transaction():
            subject = get_object_or_404(ResearchSubject.objects.select_for_update(), pk=primary.research_subject_id)
            apply_official_capture(subject, capture, self.actor())
        item.refresh_from_db()
        return Response({
            "capture": {
                "source_url": capture.get("source_url"),
                "title": capture.get("source_title"),
                "fact_count": len(capture.get("facts") or {}),
            },
            "item": review_item_to_dict(item),
        })


def _capture_selected_page(subject, provider):
    title, alternate_titles = _subject_search_values(subject)
    try:
        if provider == "amazon":
            return capture_amazon_product(title)
        if provider == "jd":
            return capture_jd_product(title, alternate_titles)
        if provider == "official":
            return capture_current_official(subject, title, alternate_titles)
    except (AmazonAssistError, JdAssistError, OfficialAssistError) as error:
        raise ReviewDomainError(str(error)) from error
    raise ReviewDomainError("provider 必须是 amazon、jd 或 official")


class ItemScopedCapture(ReviewAPI):
    def post(self, request, item_id, scope):
        if scope not in {"edition", "structure"}:
            raise ReviewDomainError("Unknown capture scope")
        provider = request.data.get("provider")
        item = get_object_or_404(ReviewItem, pk=item_id)
        subject_id = request.data.get("subject_id")
        subject = get_object_or_404(ResearchSubject, pk=subject_id) if subject_id else _primary_subject(item_id)
        capture = _capture_selected_page(subject, provider)
        with review_write_transaction():
            item = get_object_or_404(ReviewItem.objects.select_for_update(), pk=item_id)
            subject = get_object_or_404(ResearchSubject.objects.select_for_update(), pk=subject.pk)
            if scope == "edition":
                draft = stage_edition_capture(item, subject, capture, provider)
                result = {"edition_draft_id": draft.pk}
            else:
                result = {"relation_ids": stage_structure_capture(item, subject, capture, provider, self.actor())}
        item.refresh_from_db()
        return Response({**result, "item": review_item_to_dict(item)})


class ItemEditionDraft(ReviewAPI):
    def patch(self, request, item_id, draft_id):
        values = self.validated(EditionDraftDecisionSerializer)
        with review_write_transaction():
            draft = get_object_or_404(ReviewEditionDraft.objects.select_for_update(), pk=draft_id, review_item_id=item_id)
            if draft.review_item.status in {"resolved", "ignored"}:
                raise ReviewDomainError("Cannot change an Edition after Review commit")
            matched_id = values.get("matched_catalog_edition_id")
            if matched_id is not None:
                from catalog.models import BookEdition
                draft.matched_catalog_edition = get_object_or_404(BookEdition, pk=matched_id)
            if "proposed_data" in values:
                draft.proposed_data = {**draft.proposed_data, **values["proposed_data"]}
            draft.review_status = values["review_status"]
            draft.save()
        return Response(review_item_to_dict(draft.review_item))


class SubjectGuideMaterial(ReviewAPI):
    def post(self, request, item_id, subject_id):
        values = self.validated(GuideMaterialSerializer)
        with review_write_transaction():
            item = get_object_or_404(ReviewItem.objects.select_for_update(), pk=item_id)
            subject = get_object_or_404(ResearchSubject.objects.select_for_update(), pk=subject_id)
            stage_guide_material(item, subject, **values)
        item.refresh_from_db()
        return Response(review_item_to_dict(item))


class SubjectGuideDraft(ReviewAPI):
    def put(self, request, item_id, subject_id):
        values = self.validated(GuideDraftSerializer)
        with review_write_transaction():
            item = get_object_or_404(ReviewItem.objects.select_for_update(), pk=item_id)
            subject = get_object_or_404(ResearchSubject.objects.select_for_update(), pk=subject_id)
            if item.status in {"resolved", "ignored"} or not item.subject_links.filter(research_subject=subject).exists():
                raise ReviewDomainError("Guide Draft is not editable for this review item")
            subject.guide_markdown_draft = values["guide_markdown_draft"]
            subject.save(update_fields=["guide_markdown_draft", "updated_at"])
        return Response(review_item_to_dict(item))


class ItemStructureResearch(ReviewAPI):
    def post(self, request, item_id):
        values = self.validated(SelectedStructureResearchSerializer)
        item = get_object_or_404(ReviewItem, pk=item_id)
        primary_link = item.subject_links.filter(subject_role="primary").first()
        if primary_link is None:
            raise ReviewDomainError("当前审核项没有主 Research Subject")
        selected_ids = values["member_subject_ids"]
        direct_ids = set(ResearchSubject.objects.get(pk=primary_link.research_subject_id).member_relations.filter(
            relation_type="contains", member_subject_id__in=selected_ids,
        ).values_list("member_subject_id", flat=True))
        if direct_ids != set(selected_ids):
            raise ReviewDomainError("只能 Research 当前对象的直接结构成员")
        subjects = list(ResearchSubject.objects.filter(pk__in=selected_ids).order_by("pk"))
        try:
            captures, capture_errors = capture_official_subjects(subjects)
        except OfficialAssistError as error:
            raise ReviewDomainError(str(error)) from error
        with review_write_transaction():
            parent = get_object_or_404(ResearchSubject.objects.select_for_update(), pk=primary_link.research_subject_id)
            for subject_id, capture in captures.items():
                member = get_object_or_404(ResearchSubject.objects.select_for_update(), pk=subject_id)
                apply_official_capture(member, capture, self.actor())
            aggregate_selected_member_lexiles(parent, selected_ids, self.actor())
        item.refresh_from_db()
        return Response({
            "item": review_item_to_dict(item),
            "captured_subject_ids": sorted(captures),
            "capture_errors": capture_errors,
        })


class ItemParentStructure(ReviewAPI):
    def post(self, request, item_id):
        values = self.validated(ParentStructureCreateSerializer)
        with review_write_transaction():
            item = get_object_or_404(ReviewItem.objects.select_for_update(), pk=item_id)
            parent, relation = stage_parent_structure(item, values)
        item.refresh_from_db()
        return Response({
            "parent_subject_id": parent.pk,
            "relation_id": relation.pk,
            "item": review_item_to_dict(item),
        }, status=201)


class ItemParentResearch(ReviewAPI):
    def post(self, request, item_id):
        with review_write_transaction():
            item = get_object_or_404(ReviewItem.objects.select_for_update(), pk=item_id)
            subject_ids, relation_ids = stage_detected_parent_hierarchy(item, self.actor())
        item.refresh_from_db()
        return Response({
            "subject_ids": subject_ids,
            "relation_ids": relation_ids,
            "item": review_item_to_dict(item),
        })


class SubjectCreate(ReviewAPI):
    def post(self, request):
        values = self.validated(ResearchSubjectSerializer)
        sources = values.pop("sources", None)
        with review_write_transaction():
            subject = create_research_subject(values)
            if sources is not None:
                update_research_subject(subject, {"sources": sources})
        return Response(subject_to_dict(subject), status=201)


class SubjectUpdate(ReviewAPI):
    def get(self, request, subject_id):
        return Response(subject_to_dict(get_object_or_404(ResearchSubject, pk=subject_id)))

    def put(self, request, subject_id):
        values = self.validated(ResearchSubjectSerializer, partial=True)
        values.pop("review_item_id", None)
        values.pop("subject_role", None)
        with review_write_transaction():
            subject = get_object_or_404(ResearchSubject.objects.select_for_update(), pk=subject_id)
            subject = update_research_subject(subject, values)
        return Response(subject_to_dict(subject))


class SubjectDraftUpdate(ReviewAPI):
    def put(self, request, item_id, subject_id):
        values = self.validated(ResearchSubjectDraftSerializer)
        with review_write_transaction():
            item = get_object_or_404(ReviewItem.objects.select_for_update(), pk=item_id)
            subject = get_object_or_404(ResearchSubject.objects.select_for_update(), pk=subject_id)
            update_review_subject_draft(item, subject, values, self.actor())
        item.refresh_from_db()
        return Response(review_item_to_dict(item))


class SubjectProductImages(ReviewAPI):
    def put(self, request, subject_id):
        values = self.validated(ProductImageSelectionSerializer)
        with review_write_transaction():
            subject = get_object_or_404(ResearchSubject.objects.select_for_update(), pk=subject_id)
            subject = update_product_image_selection(
                subject,
                values["selected_source_urls"],
                values.get("cover_source_url"),
            )
        return Response(subject_to_dict(subject))


class CandidateRefresh(ReviewAPI):
    def post(self, request, subject_id):
        with review_write_transaction():
            subject = get_object_or_404(ResearchSubject.objects.select_for_update(), pk=subject_id)
            refresh_catalog_candidates(subject)
        return Response(subject_to_dict(subject))


class SubjectClassificationSummary(ReviewAPI):
    def post(self, request, subject_id):
        with review_write_transaction():
            subject = get_object_or_404(ResearchSubject.objects.select_for_update(), pk=subject_id)
            summarize_description_classification(subject)
        return Response(subject_to_dict(subject))


class RelationCreate(ReviewAPI):
    def post(self, request):
        values = self.validated(ResearchRelationSerializer)
        with review_write_transaction():
            relation = create_research_relation(values)
        return Response({key: getattr(relation, key) for key in ["id", "parent_subject_id", "member_subject_id", "relation_type", "position", "review_status"]}, status=201)


class RelationDetail(ReviewAPI):
    def delete(self, request, relation_id):
        from .models import ResearchSubjectRelation
        with review_write_transaction():
            relation = get_object_or_404(ResearchSubjectRelation.objects.select_for_update(), pk=relation_id)
            delete_research_relation(relation)
        return Response(status=204)


class ItemDecision(ReviewAPI):
    def post(self, request, item_id):
        values = self.validated(ReviewDecisionSerializer)
        values["actor"] = self.actor()
        with review_write_transaction():
            item = resolve_review_item(item_id, values)
        return Response(review_item_to_dict(item))


class BulkMatch(ReviewAPI):
    def post(self, request):
        values = self.validated(BulkMatchSerializer)
        resolved = []
        with review_write_transaction():
            for entry in sorted(values["entries"], key=lambda row: row["review_item_id"]):
                item_id = entry.pop("review_item_id")
                item = resolve_review_item(item_id, {**entry, "decision": "match_existing", "actor": self.actor()})
                resolved.append(item.pk)
        return Response({"resolved_item_ids": resolved})


class ConflictList(ReviewAPI):
    def get(self, request):
        conflicts = ReviewDataConflict.objects.order_by("-id")
        status = request.query_params.get("status", "pending")
        if status:
            conflicts = conflicts.filter(status=status)
        return Response(ReviewDataConflictSerializer(conflicts, many=True).data)


class ConflictResolve(ReviewAPI):
    def post(self, request, conflict_id):
        values = self.validated(ConflictResolveSerializer)
        with review_write_transaction():
            conflict = get_object_or_404(ReviewDataConflict.objects.select_for_update(), pk=conflict_id)
            resolve_conflict(conflict, values["status"], self.actor(), values.get("manual_note"))
        return Response({"id": conflict.pk, "status": conflict.status})


class ItemStructurePreview(ReviewAPI):
    """Parse Structure evidence. No database writes until explicit stage."""
    def post(self, request, item_id):
        values = self.validated(StructurePreviewInputSerializer)
        subject = _primary_subject(item_id)
        kind = values["input_kind"]
        try:
            if kind == "browser":
                snapshot = snapshot_current_page(subject.proposed_display_title or "", values.get("target_url"))
                result = extract_structure(snapshot)
            elif kind == "html":
                snapshot = PageSnapshot(url=values["base_url"], title=subject.proposed_display_title or "",
                                        html="")
                result = extract_structure(snapshot, html_fragment=values["html"])
            else:
                result = extract_url_list(values["urls"])
        except ValueError as error:
            raise ReviewDomainError(str(error)) from error
        return Response(result)


class ItemStructureStage(ReviewAPI):
    """Review-side candidate staging; does not commit any Catalog relationship."""
    def post(self, request, item_id):
        values = self.validated(StructureStageInputSerializer)
        with review_write_transaction():
            item = get_object_or_404(ReviewItem.objects.select_for_update(), pk=item_id)
            subject = _primary_subject(item_id)
            result = stage_structure_candidates(
                item=item, parent=subject, actor=self.actor(), **values)
        item.refresh_from_db()
        return Response({**result, "item": review_item_to_dict(item)})


class ItemStructureRegionStart(ReviewAPI):
    def post(self, request, item_id):
        subject = _primary_subject(item_id)
        try:
            return Response(start_region_selection(subject.proposed_display_title or "", request.data.get("target_url")))
        except ValueError as error:
            raise ReviewDomainError(str(error)) from error


class ItemStructureRegionPoll(ReviewAPI):
    def get(self, request, item_id):
        subject = _primary_subject(item_id)
        try:
            response = poll_region_selection(subject.proposed_display_title or "", request.query_params.get("target_url"))
        except ValueError as error:
            raise ReviewDomainError(str(error)) from error
        region = response.get("region")
        if not region:
            return Response({"ready": False})
        snapshot = PageSnapshot(url=region["url"], title=region["title"], html="")
        return Response({"ready": True, "preview": extract_structure(snapshot, html_fragment=region["html"])})


class ItemStructureImagePreview(ReviewAPI):
    def post(self, request, item_id):
        _primary_subject(item_id)  # enforce the review-item scope
        uploaded = request.FILES.get("image")
        if uploaded is None or uploaded.size > 10 * 1024 * 1024:
            raise ReviewDomainError("请上传 10MB 以内的 PNG / JPG / WebP 图片")
        if uploaded.content_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise ReviewDomainError("只支持 PNG / JPG / WebP")
        try:
            preview = analyze_image(uploaded.read())
        except ValueError as error:
            raise ReviewDomainError(str(error)) from error
        return Response(preview)


class ItemStructureTabs(ReviewAPI):
    def get(self, request, item_id):
        subject = _primary_subject(item_id)
        try:
            tabs = list_target_pages(subject.proposed_display_title or "")
        except ValueError as error:
            raise ReviewDomainError(str(error)) from error
        return Response({"tabs": tabs})
