from __future__ import annotations

import math
import re
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q

from .models import (
    ALLOWED_ENTITY_TYPES, COLLECTION_ENTITY_TYPES, CatalogEntity, CatalogGraphLock,
    BookEdition, CatalogCategory, CatalogEntityCategory, CatalogIsbn, CatalogSourceStat, ChildEntityAnnotation, Collection,
    CollectionItem, ReadingListItem, Work,
    normalize_search_text,
)


class CatalogDomainError(ValidationError):
    """A user-correctable Catalog invariant, shared by API, Admin and Research."""


def normalize_isbn(value: str | None) -> tuple[int | None, str | None]:
    normalized = re.sub(r"[^0-9Xx]", "", value or "").upper()
    if len(normalized) == 10 and re.fullmatch(r"[0-9]{9}[0-9X]", normalized):
        return 10, normalized
    if len(normalized) == 13 and normalized.isdigit():
        return 13, normalized
    return None, None


def equivalent_isbns(value: str | None) -> set[str]:
    """Recognize a valid ISBN-10 / 978 ISBN-13 pair for one physical version."""
    kind, normalized = normalize_isbn(value)
    if kind is None:
        return set()
    result = {normalized}
    if kind == 10:
        check = 10 if normalized[-1] == "X" else int(normalized[-1])
        if (sum((10 - index) * int(digit) for index, digit in enumerate(normalized[:9])) + check) % 11:
            return result
        body = "978" + normalized[:9]
        checksum = (10 - sum((1 if index % 2 == 0 else 3) * int(digit) for index, digit in enumerate(body)) % 10) % 10
        result.add(body + str(checksum))
    elif normalized.startswith("978"):
        if sum((1 if index % 2 == 0 else 3) * int(digit) for index, digit in enumerate(normalized)) % 10:
            return result
        body = normalized[3:12]
        checksum = (11 - sum((10 - index) * int(digit) for index, digit in enumerate(body)) % 11) % 11
        result.add(body + ("X" if checksum == 10 else str(checksum)))
    return result


@transaction.atomic
def create_catalog_entity(**values) -> CatalogEntity:
    entity_type = values.get("entity_type")
    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise CatalogDomainError(f"Unsupported entity_type: {entity_type}")
    work_values = values.pop("work", None)
    volume_count = values.pop("volume_count", None)
    lexile_min = values.pop("lexile_min", None)
    lexile_max = values.pop("lexile_max", None)
    if work_values is not None and entity_type != "book":
        raise CatalogDomainError("Only a book can have Work fields")
    if volume_count is not None and entity_type not in COLLECTION_ENTITY_TYPES:
        raise CatalogDomainError("Only a collection can have volume_count")
    if (lexile_min is not None or lexile_max is not None) and entity_type not in COLLECTION_ENTITY_TYPES:
        raise CatalogDomainError("Only a collection can have a Lexile range")
    if lexile_min is not None and lexile_max is not None and lexile_min > lexile_max:
        raise CatalogDomainError("Lexile minimum cannot exceed maximum")
    entity = CatalogEntity.objects.create(**values)
    if work_values:
        work = entity.work
        for field, value in work_values.items():
            setattr(work, field, value)
        work.full_clean()
        work.save()
    if entity_type in COLLECTION_ENTITY_TYPES and any(value is not None for value in (volume_count, lexile_min, lexile_max)):
        collection = entity.collection
        collection.volume_count = volume_count
        collection.lexile_min = lexile_min
        collection.lexile_max = lexile_max
        collection.full_clean()
        collection.save()
    return entity


def entity_queryset():
    return CatalogEntity.objects.select_related("work", "collection").prefetch_related(
        "work__editions__isbns", "categories__category", "reading_pens__reading_pen_model"
    )


def search_catalog(query: str, entity_type: str | None = None):
    normalized = normalize_search_text(query)
    if not normalized:
        return CatalogEntity.objects.none()
    result = entity_queryset().filter(search_text__contains=normalized)
    if entity_type:
        result = result.filter(entity_type=entity_type)
    return result.order_by("display_title", "id")


def amazon_rating_count_points(rating_count: int | None) -> float:
    count = int(rating_count or 0)
    if count <= 0:
        return 0.0
    if count < 10:
        return 1.0
    if count < 100:
        return 3.0
    if count < 1000:
        return 5.0
    if count < 10000:
        return 8.0
    return 10.0


def calculate_recommendation_score(
    *, has_current_stage_recommendation: bool, strong_now: bool,
    strong_in_scope: bool, creator_count: int, list_count: int,
) -> float | None:
    if not has_current_stage_recommendation:
        return None
    score = 1.0
    if strong_now:
        score += 0.50
    elif strong_in_scope:
        score += 0.20
    if creator_count > 1:
        score += 0.22 * math.log2(creator_count)
    if list_count > 1:
        score += 0.08 * math.log2(list_count)
    return round(score, 4)


def calculate_importance_score(
    recommendation_score: float,
    amazon_rating: Decimal | float | None = None,
    amazon_rating_max: Decimal | float | None = None,
    amazon_rating_count: int | None = None,
    my_rating: Decimal | float | None = None,
) -> float:
    rating = float(amazon_rating) if amazon_rating is not None else 0.0
    rating_max = float(amazon_rating_max) if amazon_rating_max is not None else 0.0
    amazon_points = rating / rating_max * 15.0 if rating_max > 0 else 0.0
    mine_points = float(my_rating) / 5.0 * 15.0 if my_rating is not None else 0.0
    score = (
        recommendation_score * 22.0
        + amazon_points
        + amazon_rating_count_points(amazon_rating_count)
        + mine_points
    )
    return round(min(100.0, max(0.0, score)), 1)


def assign_importance_levels(rows: list[dict]) -> list[dict]:
    """Assign the three fixed display tiers from the current stage only."""
    ranked = sorted(rows, key=lambda row: (-row["importance_score"], row["catalog_entity_id"]))
    count = len(ranked)
    if count <= 6:
        featured_count, normal_count = min(1, count), max(0, count - 1)
    elif count <= 15:
        featured_count, normal_count = 2, math.floor(count * 0.40 + 0.5)
    elif count <= 30:
        featured_count, normal_count = 3, math.floor(count * 0.35 + 0.5)
    else:
        featured_count, normal_count = 5, math.floor(count * 0.30 + 0.5)
    normal_count = min(normal_count, max(0, count - featured_count))
    for index, row in enumerate(ranked):
        tier = "featured" if index < featured_count else "normal" if index < featured_count + normal_count else "compact"
        row["importance_level"] = ranked[index - 1]["importance_level"] if index and row["importance_score"] == ranked[index - 1]["importance_score"] else tier
    return rows


def _stage_items(stage_label: str):
    inherited_stage = Q(stage_label__isnull=True) | Q(stage_label="")
    return ReadingListItem.objects.filter(
        Q(stage_label=stage_label) | (inherited_stage & Q(reading_list__stage_label=stage_label))
    ).select_related(
        "reading_list__creator", "catalog_entity__work", "catalog_entity__collection"
    ).prefetch_related(
        "catalog_entity__work__editions__isbns", "catalog_entity__categories__category",
        "catalog_entity__reading_pens__reading_pen_model",
    )


def aggregate_stage_entities(
    stage_label: str,
    *,
    creator_id: int | None = None,
    reading_list_id: int | None = None,
    owned_only: bool = False,
    query: str = "",
    my_rating_by_entity: dict[int, Decimal | float] | None = None,
    sort: str = "comprehensive",
) -> list[dict]:
    """Calculate non-persistent importance inside one filtered stage context."""
    items = _stage_items(stage_label)
    if creator_id is not None:
        items = items.filter(reading_list__creator_id=creator_id)
    if reading_list_id is not None:
        items = items.filter(reading_list_id=reading_list_id)
    if owned_only:
        items = items.filter(catalog_entity__bookshelf_visible=True)
    normalized_query = normalize_search_text(query)
    if normalized_query:
        items = items.filter(catalog_entity__search_text__contains=normalized_query)

    grouped: dict[int, list[ReadingListItem]] = defaultdict(list)
    for item in items.order_by("position", "sub_position", "id"):
        grouped[item.catalog_entity_id].append(item)
    if not grouped:
        return []

    # Stage membership determines inclusion. Only after that do we load all
    # recommendations in the selected map/list/creator scope, in one query.
    scope_items = ReadingListItem.objects.filter(catalog_entity_id__in=grouped).select_related(
        "reading_list__creator"
    )
    if creator_id is not None:
        scope_items = scope_items.filter(reading_list__creator_id=creator_id)
    if reading_list_id is not None:
        scope_items = scope_items.filter(reading_list_id=reading_list_id)
    scope_by_entity: dict[int, list[ReadingListItem]] = defaultdict(list)
    for relation in scope_items.order_by("reading_list_id", "position", "id"):
        scope_by_entity[relation.catalog_entity_id].append(relation)

    amazon_by_entity = {}
    amazon_rows = CatalogSourceStat.objects.filter(
        catalog_entity_id__in=grouped, source_name__iexact="amazon"
    ).order_by("catalog_entity_id", "-fetched_at", "-id")
    for stat in amazon_rows:
        amazon_by_entity.setdefault(stat.catalog_entity_id, stat)

    my_ratings = my_rating_by_entity or {}
    result = []
    for entity_id, relations in grouped.items():
        all_relations = scope_by_entity[entity_id]
        strong_now = any(row.is_strong_recommendation for row in relations)
        strong_in_scope = any(row.is_strong_recommendation for row in all_relations)
        creator_count = len({row.reading_list.creator_id for row in all_relations})
        list_count = len({row.reading_list_id for row in all_relations})
        recommendation_score = calculate_recommendation_score(
            has_current_stage_recommendation=True, strong_now=strong_now,
            strong_in_scope=strong_in_scope, creator_count=creator_count, list_count=list_count,
        )
        amazon = amazon_by_entity.get(entity_id)
        my_rating = my_ratings.get(entity_id)
        position = min((row.position for row in relations if row.position is not None), default=None)
        score = calculate_importance_score(
            recommendation_score,
            amazon.rating if amazon else None,
            amazon.rating_max if amazon else None,
            amazon.rating_count if amazon else None,
            my_rating,
        )
        entity = relations[0].catalog_entity
        result.append({
            "catalog_entity_id": entity_id,
            "entity": entity,
            "recommendation_score": recommendation_score,
            "recommendation_meta": {
                "strong_now": strong_now, "strong_in_scope": strong_in_scope,
                "creator_count": creator_count, "list_count": list_count,
            },
            "creator_count": creator_count,
            "position": position,
            "amazon_rating": float(amazon.rating) if amazon and amazon.rating is not None else None,
            "amazon_rating_max": float(amazon.rating_max) if amazon and amazon.rating_max is not None else None,
            "amazon_rating_count": amazon.rating_count if amazon else None,
            "my_rating": float(my_rating) if my_rating is not None else None,
            "importance_score": score,
            "recommendations": [{
                "reading_list_item_id": row.pk,
                "reading_list_id": row.reading_list_id,
                "reading_list_title": row.reading_list.title,
                "creator_id": row.reading_list.creator_id,
                "creator_name": row.reading_list.creator.name,
                "position": row.position,
                "stage_label": row.stage_label or row.reading_list.stage_label,
                "creator_avatar_url": row.reading_list.creator.avatar_url,
                "is_strong_recommendation": row.is_strong_recommendation,
                "recommendation_emphasis_text": row.recommendation_emphasis_text,
                "comment": row.comment,
                "note": row.note,
            } for row in all_relations],
        })

    assign_importance_levels(result)
    if sort == "creator":
        key = lambda row: (-row["recommendation_score"], row["position"] is None, row["position"] or 0, row["catalog_entity_id"])
    elif sort == "amazon":
        key = lambda row: (row["amazon_rating"] is None, -(row["amazon_rating"] or 0), -(row["amazon_rating_count"] or 0), row["catalog_entity_id"])
    elif sort == "mine":
        key = lambda row: (row["my_rating"] is None, -(row["my_rating"] or 0), row["catalog_entity_id"])
    elif sort == "title":
        key = lambda row: (normalize_search_text(row["entity"].display_title), row["catalog_entity_id"])
    else:
        key = lambda row: (-row["importance_score"], row["position"] is None, row["position"] or 0, row["catalog_entity_id"])
    return sorted(result, key=key)


@transaction.atomic
def add_isbn(work_entity_id: int, raw_isbn: str, edition_id: int | None = None) -> CatalogIsbn:
    isbn_type, isbn_val = normalize_isbn(raw_isbn)
    if isbn_type is None:
        raise CatalogDomainError("Invalid ISBN")
    work = Work.objects.filter(pk=work_entity_id).first()
    if work is None:
        raise CatalogDomainError("ISBN can only be attached to a book Work")
    edition = BookEdition.objects.filter(pk=edition_id, work=work).first() if edition_id else work.editions.order_by("pk").first()
    if edition_id and edition is None:
        raise CatalogDomainError("Edition must belong to this Work")
    if edition is None:
        edition = BookEdition.objects.create(work=work)
    existing = CatalogIsbn.objects.filter(isbn_type=isbn_type, isbn_val=isbn_val).first()
    if existing:
        if existing.edition.work_id != work_entity_id:
            raise CatalogDomainError("ISBN already belongs to another Work")
        if edition_id and existing.edition_id != edition.pk:
            raise CatalogDomainError("ISBN already belongs to another Edition")
        return existing
    return CatalogIsbn.objects.create(edition=edition, isbn_type=isbn_type, isbn_val=isbn_val)


def find_by_isbn(raw_isbn: str) -> CatalogEntity | None:
    isbn_type, isbn_val = normalize_isbn(raw_isbn)
    if isbn_type is None:
        raise CatalogDomainError("Invalid ISBN")
    return entity_queryset().filter(work__editions__isbns__isbn_type=isbn_type, work__editions__isbns__isbn_val=isbn_val).first()


@transaction.atomic
def assign_entity_categories(entity: CatalogEntity, assignments: list[dict]) -> list[CatalogEntityCategory]:
    """Add human-confirmed controlled categories without deleting existing formal facts."""
    category_ids = [row["category_id"] for row in assignments]
    if len(category_ids) != len(set(category_ids)):
        raise CatalogDomainError("A category can only be selected once")
    categories = {row.pk: row for row in CatalogCategory.objects.filter(pk__in=category_ids)}
    if len(categories) != len(category_ids):
        raise CatalogDomainError("One or more selected categories do not exist")

    primary_types = [categories[row["category_id"]].category_type for row in assignments if row.get("is_primary")]
    if len(primary_types) != len(set(primary_types)):
        raise CatalogDomainError("Only one primary category is allowed per category type")

    results = []
    for row in assignments:
        category = categories[row["category_id"]]
        is_primary = bool(row.get("is_primary"))
        if is_primary:
            CatalogEntityCategory.objects.filter(
                catalog_entity=entity,
                category__category_type=category.category_type,
                is_primary=True,
            ).exclude(category=category).update(is_primary=False)
        link, _ = CatalogEntityCategory.objects.update_or_create(
            catalog_entity=entity,
            category=category,
            defaults={"is_primary": is_primary},
        )
        results.append(link)
    return results


def lock_collection_graph():
    # Call inside atomic(). One global row avoids a concurrent A→B / B→A write skew.
    CatalogGraphLock.objects.get_or_create(key="collection-membership")
    CatalogGraphLock.objects.select_for_update().get(key="collection-membership")


def _collection_reaches(start_collection_id: int, target_entity_id: int) -> bool:
    pending, seen = [start_collection_id], set()
    while pending:
        collection_id = pending.pop()
        if collection_id in seen:
            continue
        seen.add(collection_id)
        members = list(CollectionItem.objects.filter(collection_id=collection_id).values_list("member_entity_id", flat=True))
        if target_entity_id in members:
            return True
        pending.extend(Collection.objects.filter(pk__in=members).values_list("pk", flat=True))
    return False


def validate_collection_membership(collection_id: int, member_entity_id: int):
    if not Collection.objects.filter(pk=collection_id).exists():
        raise CatalogDomainError("Collection not found")
    if not CatalogEntity.objects.filter(pk=member_entity_id).exists():
        raise CatalogDomainError("Member entity not found")
    if collection_id == member_entity_id:
        raise CatalogDomainError("A collection cannot contain itself")
    if Collection.objects.filter(pk=member_entity_id).exists() and _collection_reaches(member_entity_id, collection_id):
        raise CatalogDomainError("Collection membership would create a cycle")


@transaction.atomic
def add_collection_item(collection_id: int, member_entity_id: int, position: int | None = None) -> CollectionItem:
    lock_collection_graph()
    validate_collection_membership(collection_id, member_entity_id)
    item, _ = CollectionItem.objects.update_or_create(collection_id=collection_id, member_entity_id=member_entity_id, defaults={"position": position})
    return item


def expand_collection(collection_id: int) -> dict:
    if not Collection.objects.filter(pk=collection_id).exists():
        raise CatalogDomainError("Collection not found")

    def expand(entity_id, path):
        entity = CatalogEntity.objects.get(pk=entity_id)
        node = {"id": entity.id, "entity_type": entity.entity_type, "display_title": entity.display_title, "children": []}
        if entity.id in path or entity.entity_type not in COLLECTION_ENTITY_TYPES:
            return node
        rows = CollectionItem.objects.filter(collection_id=entity.id).order_by(F("position").asc(nulls_last=True), "id")
        node["children"] = [expand(row.member_entity_id, path | {entity.id}) for row in rows]
        return node

    return expand(collection_id, frozenset())


def effective_independent_reading(child_id: int, catalog_entity_id: int) -> tuple[bool | None, str]:
    annotation = ChildEntityAnnotation.objects.filter(child_id=child_id, catalog_entity_id=catalog_entity_id).first()
    if annotation and annotation.independent_reading_override is not None:
        return annotation.independent_reading_override, "child_override"
    try:
        entity = CatalogEntity.objects.get(pk=catalog_entity_id)
    except CatalogEntity.DoesNotExist:
        raise CatalogDomainError("Catalog entity not found")
    return entity.independent_reading_suitable, "catalog"


def resolve_source_rows(rows: list[dict]) -> dict:
    """Read-only source reconciliation: ambiguity never manufactures a Catalog entity."""
    resolved, unresolved = [], []
    for row in rows:
        candidates = list(search_catalog(row.get("raw_title") or row.get("title") or ""))
        if len(candidates) == 1:
            resolved.append({**row, "catalog_entity_id": candidates[0].id})
        else:
            unresolved.append({**row, "reason": "no catalog candidate" if not candidates else "multiple catalog candidates"})
    return {"resolved": resolved, "unresolved": unresolved}
