from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.catalog import (
    ALLOWED_ENTITY_TYPES,
    COLLECTION_ENTITY_TYPES,
    CatalogEntity,
    CatalogIsbn,
    ChildEntityAnnotation,
    Collection,
    CollectionItem,
    Work,
    normalize_search_text,
)


class CatalogDomainError(ValueError):
    pass


def normalize_isbn(value: str | None) -> tuple[int | None, str | None]:
    normalized = re.sub(r"[^0-9Xx]", "", value or "").upper()
    if len(normalized) == 10 and re.fullmatch(r"[0-9]{9}[0-9X]", normalized):
        return 10, normalized
    if len(normalized) == 13 and normalized.isdigit():
        return 13, normalized
    return None, None


def create_catalog_entity(db: Session, **values) -> CatalogEntity:
    entity_type = values.get("entity_type")
    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise CatalogDomainError(f"Unsupported entity_type: {entity_type}")
    entity = CatalogEntity(**values)
    if entity_type == "book":
        entity.work = Work()
    elif entity_type in COLLECTION_ENTITY_TYPES:
        entity.collection = Collection()
    db.add(entity)
    db.flush()
    return entity


def search_catalog(db: Session, query: str, entity_type: str | None = None) -> list[CatalogEntity]:
    normalized = normalize_search_text(query)
    if not normalized:
        return []
    statement = select(CatalogEntity).where(CatalogEntity.search_text.contains(normalized))
    if entity_type:
        statement = statement.where(CatalogEntity.entity_type == entity_type)
    return list(db.scalars(statement.order_by(CatalogEntity.display_title, CatalogEntity.id)).all())


def add_isbn(db: Session, work_entity_id: int, raw_isbn: str) -> CatalogIsbn:
    isbn_type, isbn_val = normalize_isbn(raw_isbn)
    if isbn_type is None or isbn_val is None:
        raise CatalogDomainError("Invalid ISBN")
    if db.get(Work, work_entity_id) is None:
        raise CatalogDomainError("ISBN can only be attached to a book Work")
    existing = db.scalar(select(CatalogIsbn).where(CatalogIsbn.isbn_type == isbn_type, CatalogIsbn.isbn_val == isbn_val))
    if existing:
        if existing.work_entity_id != work_entity_id:
            raise CatalogDomainError("ISBN already belongs to another Work")
        return existing
    item = CatalogIsbn(work_entity_id=work_entity_id, isbn_type=isbn_type, isbn_val=isbn_val)
    db.add(item)
    db.flush()
    return item


def find_by_isbn(db: Session, raw_isbn: str) -> CatalogEntity | None:
    isbn_type, isbn_val = normalize_isbn(raw_isbn)
    if isbn_type is None or isbn_val is None:
        raise CatalogDomainError("Invalid ISBN")
    return db.scalar(
        select(CatalogEntity)
        .join(Work, Work.catalog_entity_id == CatalogEntity.id)
        .join(CatalogIsbn, CatalogIsbn.work_entity_id == Work.catalog_entity_id)
        .where(CatalogIsbn.isbn_type == isbn_type, CatalogIsbn.isbn_val == isbn_val)
    )


def _collection_reaches(db: Session, start_collection_id: int, target_entity_id: int) -> bool:
    pending = [start_collection_id]
    seen: set[int] = set()
    while pending:
        collection_id = pending.pop()
        if collection_id in seen:
            continue
        seen.add(collection_id)
        member_ids = list(db.scalars(select(CollectionItem.member_entity_id).where(CollectionItem.collection_id == collection_id)))
        if target_entity_id in member_ids:
            return True
        if member_ids:
            pending.extend(db.scalars(select(Collection.catalog_entity_id).where(Collection.catalog_entity_id.in_(member_ids))))
    return False


def add_collection_item(db: Session, collection_id: int, member_entity_id: int, position: int | None = None) -> CollectionItem:
    if db.get(Collection, collection_id) is None:
        raise CatalogDomainError("Collection not found")
    if db.get(CatalogEntity, member_entity_id) is None:
        raise CatalogDomainError("Member entity not found")
    if collection_id == member_entity_id:
        raise CatalogDomainError("A collection cannot contain itself")
    if db.get(Collection, member_entity_id) and _collection_reaches(db, member_entity_id, collection_id):
        raise CatalogDomainError("Collection membership would create a cycle")
    existing = db.scalar(select(CollectionItem).where(CollectionItem.collection_id == collection_id, CollectionItem.member_entity_id == member_entity_id))
    if existing:
        existing.position = position
        return existing
    item = CollectionItem(collection_id=collection_id, member_entity_id=member_entity_id, position=position)
    db.add(item)
    db.flush()
    return item


def expand_collection(db: Session, collection_id: int) -> dict:
    if db.get(Collection, collection_id) is None:
        raise CatalogDomainError("Collection not found")

    def expand(entity_id: int, path: frozenset[int]) -> dict:
        entity = db.get(CatalogEntity, entity_id)
        if entity is None:
            raise CatalogDomainError("Collection contains a missing entity")
        node = {"id": entity.id, "entity_type": entity.entity_type, "display_title": entity.display_title, "children": []}
        if entity.id in path or entity.entity_type not in COLLECTION_ENTITY_TYPES:
            return node
        rows = db.scalars(
            select(CollectionItem)
            .where(CollectionItem.collection_id == entity.id)
            .options(selectinload(CollectionItem.member_entity))
            .order_by(CollectionItem.position.is_(None), CollectionItem.position, CollectionItem.id)
        ).all()
        node["children"] = [expand(row.member_entity_id, path | {entity.id}) for row in rows]
        return node

    return expand(collection_id, frozenset())


def effective_independent_reading(db: Session, child_id: int, catalog_entity_id: int) -> tuple[bool | None, str]:
    annotation = db.get(ChildEntityAnnotation, (child_id, catalog_entity_id))
    if annotation and annotation.independent_reading_override is not None:
        return annotation.independent_reading_override, "child_override"
    entity = db.get(CatalogEntity, catalog_entity_id)
    if entity is None:
        raise CatalogDomainError("Catalog entity not found")
    return entity.independent_reading_suitable, "catalog"
