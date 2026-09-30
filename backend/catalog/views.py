from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from . import models as m, serializers as s, services
from . import admin_capture


class PublicReadStaffWrite(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS or bool(request.user and request.user.is_authenticated and request.user.is_staff)


class PublicCatalogView(APIView):
    permission_classes = [PublicReadStaffWrite]


class CatalogAssetView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, asset_path):
        root = (Path(settings.BASE_DIR).parent / "research_data").resolve()
        target = (root / asset_path).resolve()
        if not target.is_relative_to(root) or not target.is_file() or target.suffix.casefold() not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            raise Http404
        response = FileResponse(target.open("rb"))
        response["Cache-Control"] = "private, no-store"
        return response


def validated(serializer_class, data, **kwargs):
    serializer = serializer_class(data=data, **kwargs)
    serializer.is_valid(raise_exception=True)
    return serializer


def get_entity(entity_id):
    return get_object_or_404(services.entity_queryset(), pk=entity_id)


def reading_list_queryset():
    items = m.ReadingListItem.objects.select_related("catalog_entity__work", "catalog_entity__collection", "recommended_edition").prefetch_related("catalog_entity__work__editions__isbns", "catalog_entity__categories__category", "catalog_entity__reading_pens__reading_pen_model")
    return m.ReadingList.objects.select_related("creator").prefetch_related(Prefetch("items", queryset=items))


class HealthView(PublicCatalogView):
    def get(self, request):
        return Response({"status": "ok", "schema": "catalog-v1", "framework": "django-drf"})


class CatalogEntitiesView(PublicCatalogView):
    def get(self, request):
        limit = serializers.IntegerField(min_value=1, max_value=500).run_validation(request.query_params.get("limit", 100))
        entities = services.entity_queryset()
        if request.query_params.get("entity_type"):
            entity_type = serializers.ChoiceField(choices=m.ENTITY_CHOICES).run_validation(request.query_params["entity_type"])
            entities = entities.filter(entity_type=entity_type)
        return Response(s.CatalogEntitySerializer(entities[:limit], many=True).data)

    def post(self, request):
        entity = validated(s.CatalogEntityCreateSerializer, request.data).save()
        return Response(s.CatalogEntitySerializer(get_entity(entity.pk)).data, status=status.HTTP_201_CREATED)


class CatalogEntityView(PublicCatalogView):
    def get(self, request, entity_id):
        return Response(s.CatalogEntitySerializer(get_entity(entity_id)).data)

    def patch(self, request, entity_id):
        values = validated(s.CatalogEntityEditSerializer, request.data).validated_data
        with transaction.atomic():
            entity = get_object_or_404(m.CatalogEntity.objects.select_for_update(), pk=entity_id)
            work_values = values.pop("work", None)
            volume_count = values.pop("volume_count", serializers.empty)
            categories = values.pop("category_decisions", None)
            for key, value in values.items():
                setattr(entity, key, value)
            if values:
                entity.save(update_fields=list(values))
            if work_values is not None:
                if entity.entity_type != "book":
                    raise serializers.ValidationError({"work": "Only a Book has Work fields"})
                work = entity.work
                for key, value in work_values.items():
                    setattr(work, key, value)
                work.full_clean()
                work.save()
            if volume_count is not serializers.empty:
                if entity.entity_type not in m.COLLECTION_ENTITY_TYPES:
                    raise serializers.ValidationError({"volume_count": "Only a Collection has volume_count"})
                entity.collection.volume_count = volume_count
                entity.collection.save(update_fields=["volume_count", "updated_at"])
            if categories is not None:
                choices = s.EntityCategorySerializer(data=categories, many=True)
                choices.is_valid(raise_exception=True)
                wanted = {row["category_id"].pk for row in choices.validated_data}
                m.CatalogEntityCategory.objects.filter(catalog_entity=entity).exclude(category_id__in=wanted).delete()
                services.assign_entity_categories(entity, [{"category_id": row["category_id"].pk, "is_primary": row["is_primary"]} for row in choices.validated_data])
        return Response(s.CatalogEntitySerializer(get_entity(entity_id)).data)


class CatalogEditionView(PublicCatalogView):
    def post(self, request, entity_id):
        entity = get_entity(entity_id)
        if entity.entity_type != "book":
            raise serializers.ValidationError("Edition requires a Book")
        serializer = validated(s.BookEditionSerializer, request.data)
        with transaction.atomic():
            edition = serializer.save(work=entity.work)
        return Response(s.BookEditionSerializer(edition).data, status=201)

    def patch(self, request, entity_id, edition_id):
        edition = get_object_or_404(m.BookEdition, pk=edition_id, work_id=entity_id)
        serializer = validated(s.BookEditionSerializer, request.data, instance=edition, partial=True)
        with transaction.atomic():
            edition = serializer.save()
        return Response(s.BookEditionSerializer(edition).data)


class CatalogSearchView(PublicCatalogView):
    def get(self, request):
        query = serializers.CharField(max_length=500, allow_blank=True).run_validation(request.query_params.get("q", ""))
        entity_type = request.query_params.get("entity_type")
        if entity_type:
            serializers.ChoiceField(choices=m.ENTITY_CHOICES).run_validation(entity_type)
        return Response(s.CatalogEntitySerializer(services.search_catalog(query, entity_type)[:500], many=True).data)


class IsbnAttachView(PublicCatalogView):
    def post(self, request, entity_id):
        get_entity(entity_id)
        isbn = serializers.CharField(max_length=100).run_validation(request.query_params.get("isbn") or request.data.get("isbn"))
        edition_id = request.data.get("edition_id")
        services.add_isbn(entity_id, isbn, serializers.IntegerField(min_value=1).run_validation(edition_id) if edition_id else None)
        return Response(s.CatalogEntitySerializer(get_entity(entity_id)).data)


class IsbnLookupView(PublicCatalogView):
    def get(self, request, isbn):
        entity = services.find_by_isbn(isbn)
        if entity is None:
            return Response({"detail": "Catalog entity not found"}, status=404)
        return Response(s.CatalogEntitySerializer(entity).data)


class CollectionView(PublicCatalogView):
    def get(self, request, collection_id):
        get_object_or_404(m.Collection, pk=collection_id)
        return Response(services.expand_collection(collection_id))


class CollectionItemsView(PublicCatalogView):
    def post(self, request, collection_id):
        get_object_or_404(m.Collection, pk=collection_id)
        data = validated(s.CollectionItemSerializer, request.data).validated_data
        services.add_collection_item(collection_id, data["member_entity_id"].pk, data["position"])
        return Response(services.expand_collection(collection_id))

    def delete(self, request, collection_id):
        member_id = serializers.IntegerField(min_value=1).run_validation(request.data.get("member_entity_id"))
        get_object_or_404(m.CollectionItem, collection_id=collection_id, member_entity_id=member_id).delete()
        return Response(status=204)


class CatalogAdminAPI(APIView):
    permission_classes = [permissions.IsAdminUser]

    def handle_exception(self, exc):
        if isinstance(exc, services.CatalogDomainError):
            converted = APIException(str(exc))
            converted.status_code = 400
            exc = converted
        return super().handle_exception(exc)


class CatalogAdminSearch(CatalogAdminAPI):
    def post(self, request, entity_id):
        entity = get_entity(entity_id)
        provider = serializers.ChoiceField(choices=["amazon", "jd", "official"]).run_validation(request.data.get("provider"))
        query = serializers.CharField(max_length=500).run_validation(request.data.get("query") or entity.title_en or entity.display_title)
        return Response(admin_capture.search(provider, query))


class CatalogAdminCapture(CatalogAdminAPI):
    def post(self, request, entity_id):
        entity = get_entity(entity_id)
        provider = serializers.ChoiceField(choices=["amazon", "jd", "official"]).run_validation(request.data.get("provider"))
        scope = serializers.ChoiceField(choices=["page", "edition", "structure"]).run_validation(request.data.get("scope"))
        try:
            return Response(admin_capture.capture_candidate(entity, provider, scope))
        except Exception as error:
            if isinstance(error, services.CatalogDomainError):
                raise
            raise APIException(f"Capture failed: {error}") from error


class CatalogAdminConfirm(CatalogAdminAPI):
    def post(self, request, entity_id):
        entity = get_entity(entity_id)
        token = serializers.CharField().run_validation(request.data.get("token"))
        selected_fields = serializers.ListField(child=serializers.CharField(), allow_empty=True).run_validation(request.data.get("selected_fields", []))
        edition_id = request.data.get("edition_id")
        if edition_id is not None:
            edition_id = serializers.IntegerField(min_value=1).run_validation(edition_id)
        members = serializers.ListField(child=serializers.DictField(), required=False).run_validation(request.data.get("members", []))
        admin_capture.confirm_candidate(entity, token, selected_fields, edition_id, members, request.data.get("guide_markdown"))
        return Response(s.CatalogEntitySerializer(get_entity(entity_id)).data)


class CatalogAdminGuideMaterial(CatalogAdminAPI):
    def post(self, request, entity_id):
        entity = get_entity(entity_id)
        raw = serializers.CharField(max_length=50000).run_validation(request.data.get("raw_content"))
        title = serializers.CharField(max_length=1000, allow_blank=True).run_validation(request.data.get("source_title", ""))
        return Response(admin_capture.add_guide_material(entity, raw, title))


class CreatorsView(PublicCatalogView):
    def get(self, request):
        return Response(s.CreatorSerializer(m.ReadingListCreator.objects.all(), many=True).data)

    def post(self, request):
        item = validated(s.CreatorSerializer, request.data).save()
        return Response(s.CreatorSerializer(item).data, status=201)


class ReadingListsView(PublicCatalogView):
    def get(self, request):
        items = reading_list_queryset()
        if request.query_params.get("creator_id"):
            creator_id = serializers.IntegerField(min_value=1).run_validation(request.query_params["creator_id"])
            items = items.filter(creator_id=creator_id)
        return Response(s.ReadingListSerializer(items, many=True).data)

    def post(self, request):
        item = validated(s.ReadingListSerializer, request.data).save()
        return Response(s.ReadingListSerializer(item).data, status=201)


class ReadingListView(PublicCatalogView):
    def get(self, request, list_id):
        return Response(s.ReadingListSerializer(get_object_or_404(reading_list_queryset(), pk=list_id)).data)


class ReadingListItemsView(PublicCatalogView):
    def post(self, request, list_id):
        item = get_object_or_404(m.ReadingList, pk=list_id)
        validated(s.ReadingListItemSerializer, request.data).save(reading_list=item)
        return Response(s.ReadingListSerializer(get_object_or_404(reading_list_queryset(), pk=list_id)).data)


class ReadingMapStageEntitiesView(PublicCatalogView):
    """One response-time aggregation for both organic and grid layouts."""

    def get(self, request):
        stage_label = serializers.CharField(max_length=255).run_validation(request.query_params.get("stage_label"))
        sort_key = serializers.ChoiceField(
            choices=["comprehensive", "creator", "amazon", "mine", "title"]
        ).run_validation(request.query_params.get("sort", "comprehensive"))
        creator_id = request.query_params.get("creator_id")
        reading_list_id = request.query_params.get("reading_list_id")
        creator_id = serializers.IntegerField(min_value=1).run_validation(creator_id) if creator_id else None
        reading_list_id = serializers.IntegerField(min_value=1).run_validation(reading_list_id) if reading_list_id else None
        owned_only = serializers.BooleanField().run_validation(request.query_params.get("owned_only", False))
        query = serializers.CharField(max_length=500, allow_blank=True).run_validation(request.query_params.get("q", ""))

        rows = services.aggregate_stage_entities(
            stage_label,
            creator_id=creator_id,
            reading_list_id=reading_list_id,
            owned_only=owned_only,
            query=query,
            # The current schema has no user-rating persistence.  The scorer
            # accepts a per-user mapping without inventing a second rating model.
            my_rating_by_entity={},
            sort=sort_key,
        )
        entities = []
        for row in rows:
            entity = row.pop("entity")
            entities.append({**row, "entity": s.CatalogEntitySerializer(entity).data})
        return Response({
            "stage_label": stage_label,
            "sort": sort_key,
            "total": len(entities),
            "entities": entities,
        })


class CategoriesView(PublicCatalogView):
    def get(self, request):
        items = m.CatalogCategory.objects.all()
        if request.query_params.get("category_type"):
            items = items.filter(category_type=request.query_params["category_type"])
        return Response(s.CategorySerializer(items, many=True).data)

    def post(self, request):
        item = validated(s.CategorySerializer, request.data).save()
        return Response(s.CategorySerializer(item).data, status=201)


class EntityCategoryView(PublicCatalogView):
    def post(self, request, entity_id):
        entity = get_entity(entity_id)
        data = validated(s.EntityCategorySerializer, request.data).validated_data
        services.assign_entity_categories(entity, [{
            "category_id": data["category_id"].pk,
            "is_primary": data["is_primary"],
        }])
        return Response(s.CatalogEntitySerializer(get_entity(entity_id)).data)


class WorkProfileView(PublicCatalogView):
    serializer_class = s.DifficultyProfileSerializer
    model = m.WorkDifficultyProfile

    def get(self, request, entity_id):
        get_object_or_404(m.Work, pk=entity_id)
        item = self.model.objects.filter(pk=entity_id).first() or self.model(work_entity_id=entity_id)
        return Response(self.serializer_class(item).data)

    def put(self, request, entity_id):
        work = get_object_or_404(m.Work, pk=entity_id)
        with transaction.atomic():
            item = self.model.objects.select_for_update().filter(pk=entity_id).first()
            serializer = validated(self.serializer_class, request.data, instance=item)
            item = serializer.save(work_entity=work)
        return Response(self.serializer_class(item).data)


class WorkRequirementView(WorkProfileView):
    serializer_class = s.AbilityRequirementSerializer
    model = m.WorkAbilityRequirement


class ChildrenView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(s.ChildSerializer(m.ChildProfile.objects.filter(owner=request.user), many=True).data)

    def post(self, request):
        item = validated(s.ChildSerializer, request.data).save(owner=request.user)
        return Response(s.ChildSerializer(item).data, status=201)


def owned_child(request, child_id):
    # Even staff use the same product-facing ownership boundary. Admin has its own surface.
    return get_object_or_404(m.ChildProfile, pk=child_id, owner=request.user)


class ChildView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, child_id):
        return Response(s.ChildSerializer(owned_child(request, child_id)).data)

    def patch(self, request, child_id):
        child = owned_child(request, child_id)
        item = validated(s.ChildSerializer, request.data, instance=child, partial=True).save()
        return Response(s.ChildSerializer(item).data)


class ChildAbilitiesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, child_id):
        child = owned_child(request, child_id)
        return Response(s.ChildAbilitySerializer(child.ability_profiles.order_by("language_code"), many=True).data)


class ChildAbilityView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, child_id, language_code):
        child = owned_child(request, child_id)
        item = child.ability_profiles.filter(language_code=language_code).first() or m.ChildAbilityProfile(child=child, language_code=language_code)
        return Response(s.ChildAbilitySerializer(item).data)

    def put(self, request, child_id, language_code):
        child = owned_child(request, child_id)
        language_code = serializers.RegexField(r"^[A-Za-z][A-Za-z0-9-]{0,49}$").run_validation(language_code)
        with transaction.atomic():
            # Lock parent for concurrent first creation as well as existing profile updates.
            m.ChildProfile.objects.select_for_update().get(pk=child.pk)
            item = child.ability_profiles.filter(language_code=language_code).first()
            item = validated(s.ChildAbilitySerializer, request.data, instance=item).save(child=child, language_code=language_code)
        return Response(s.ChildAbilitySerializer(item).data)


class ChildAnnotationsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, child_id):
        child = owned_child(request, child_id)
        rows = child.entity_annotations.select_related("catalog_entity__work", "catalog_entity__collection").prefetch_related("catalog_entity__work__isbns", "catalog_entity__categories__category", "catalog_entity__reading_pens__reading_pen_model").order_by("id")
        return Response(s.ChildAnnotationSerializer(rows, many=True).data)


class ChildAnnotationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, child_id, entity_id):
        child = owned_child(request, child_id)
        entity = get_entity(entity_id)
        item = child.entity_annotations.filter(catalog_entity=entity).first() or m.ChildEntityAnnotation(child=child, catalog_entity=entity)
        return Response(s.ChildAnnotationSerializer(item).data)

    def put(self, request, child_id, entity_id):
        child = owned_child(request, child_id)
        entity = get_entity(entity_id)
        with transaction.atomic():
            m.ChildProfile.objects.select_for_update().get(pk=child.pk)
            item = child.entity_annotations.filter(catalog_entity=entity).first()
            item = validated(s.ChildAnnotationSerializer, request.data, instance=item).save(child=child, catalog_entity=entity)
        return Response(s.ChildAnnotationSerializer(item).data)


class SourceStatsView(PublicCatalogView):
    def get(self, request, entity_id):
        entity = get_entity(entity_id)
        return Response(s.SourceStatSerializer(entity.source_stats.order_by("id"), many=True).data)

    def post(self, request, entity_id):
        entity = get_entity(entity_id)
        item = validated(s.SourceStatSerializer, request.data).save(catalog_entity=entity)
        return Response(s.SourceStatSerializer(item).data, status=201)
