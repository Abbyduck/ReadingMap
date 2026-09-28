from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.catalog import (
    CatalogCategory,
    CatalogEntity,
    CatalogEntityCategory,
    CatalogEntityReadingPen,
    CatalogSourceStat,
    ChildAbilityProfile,
    ChildEntityAnnotation,
    ChildProfile,
    ReadingList,
    ReadingListCreator,
    ReadingListItem,
    Work,
    WorkAbilityRequirement,
    WorkDifficultyProfile,
)
from app.schemas.catalog import (
    AbilityRequirementRead,
    AbilityRequirementWrite,
    CatalogEntityCreate,
    CatalogEntityRead,
    CategoryCreate,
    CategoryRead,
    ChildAbilityRead,
    ChildAbilityWrite,
    ChildAnnotationRead,
    ChildAnnotationWrite,
    ChildCreate,
    ChildRead,
    CollectionItemCreate,
    CollectionNode,
    CreatorCreate,
    CreatorRead,
    DifficultyProfileRead,
    DifficultyProfileWrite,
    EntityCategoryCreate,
    ReadingListCreate,
    ReadingListItemCreate,
    ReadingListItemRead,
    ReadingListRead,
    SourceStatCreate,
    SourceStatRead,
    WorkFields,
)
from app.services.catalog_service import (
    CatalogDomainError,
    add_collection_item,
    add_isbn,
    create_catalog_entity,
    effective_independent_reading,
    expand_collection,
    find_by_isbn,
    search_catalog,
)


router = APIRouter()


def _domain_error(error: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


def _entity_read(entity: CatalogEntity) -> CatalogEntityRead:
    work = entity.work
    return CatalogEntityRead(
        id=entity.id,
        entity_type=entity.entity_type,
        display_title=entity.display_title,
        title_zh=entity.title_zh,
        title_en=entity.title_en,
        aliases=entity.aliases,
        description=entity.description,
        cover_url=entity.cover_url,
        independent_reading_suitable=entity.independent_reading_suitable,
        work=WorkFields.model_validate(work, from_attributes=True) if work else None,
        volume_count=entity.collection.volume_count if entity.collection else None,
        isbns=list(work.isbns) if work else [],
        categories=[link.category for link in entity.categories],
        reading_pens=[{"id": link.reading_pen.id, "name": link.reading_pen.name} for link in entity.reading_pens],
    )


def _entity_query():
    return select(CatalogEntity).options(
        selectinload(CatalogEntity.work).selectinload(Work.isbns),
        selectinload(CatalogEntity.collection),
        selectinload(CatalogEntity.categories).selectinload(CatalogEntityCategory.category),
        selectinload(CatalogEntity.reading_pens).selectinload(CatalogEntityReadingPen.reading_pen),
    )


def _get_entity(db: Session, entity_id: int) -> CatalogEntity:
    entity = db.scalar(_entity_query().where(CatalogEntity.id == entity_id))
    if entity is None:
        raise HTTPException(status_code=404, detail="Catalog entity not found")
    return entity


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "schema": "catalog-v1"}


@router.get("/catalog/entities", response_model=list[CatalogEntityRead])
def list_entities(entity_type: str | None = None, limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    statement = _entity_query().order_by(CatalogEntity.id.desc()).limit(limit)
    if entity_type:
        statement = statement.where(CatalogEntity.entity_type == entity_type)
    return [_entity_read(item) for item in db.scalars(statement).all()]


@router.post("/catalog/entities", response_model=CatalogEntityRead, status_code=201)
def create_entity(payload: CatalogEntityCreate, db: Session = Depends(get_db)):
    values = payload.model_dump(exclude={"work", "volume_count"})
    values["cover_local_path"] = None
    try:
        entity = create_catalog_entity(db, **values)
        if entity.work and payload.work:
            for key, value in payload.work.model_dump().items():
                setattr(entity.work, key, value)
        if entity.collection:
            entity.collection.volume_count = payload.volume_count
        db.commit()
    except (CatalogDomainError, IntegrityError) as error:
        db.rollback()
        raise _domain_error(error) from error
    return _entity_read(_get_entity(db, entity.id))


@router.get("/catalog/entities/{entity_id}", response_model=CatalogEntityRead)
def get_entity(entity_id: int, db: Session = Depends(get_db)):
    return _entity_read(_get_entity(db, entity_id))


@router.get("/catalog/search", response_model=list[CatalogEntityRead])
def catalog_search(q: str, entity_type: str | None = None, db: Session = Depends(get_db)):
    ids = [item.id for item in search_catalog(db, q, entity_type)]
    if not ids:
        return []
    entities = db.scalars(_entity_query().where(CatalogEntity.id.in_(ids))).all()
    by_id = {item.id: item for item in entities}
    return [_entity_read(by_id[item_id]) for item_id in ids]


@router.post("/catalog/entities/{entity_id}/isbns", response_model=CatalogEntityRead)
def attach_isbn(entity_id: int, isbn: str, db: Session = Depends(get_db)):
    try:
        add_isbn(db, entity_id, isbn)
        db.commit()
    except (CatalogDomainError, IntegrityError) as error:
        db.rollback()
        raise _domain_error(error) from error
    return _entity_read(_get_entity(db, entity_id))


@router.get("/catalog/isbn/{isbn}", response_model=CatalogEntityRead)
def lookup_isbn(isbn: str, db: Session = Depends(get_db)):
    try:
        entity = find_by_isbn(db, isbn)
    except CatalogDomainError as error:
        raise _domain_error(error) from error
    if entity is None:
        raise HTTPException(status_code=404, detail="Catalog entity not found")
    return _entity_read(_get_entity(db, entity.id))


@router.post("/collections/{collection_id}/items", response_model=CollectionNode)
def create_collection_member(collection_id: int, payload: CollectionItemCreate, db: Session = Depends(get_db)):
    try:
        add_collection_item(db, collection_id, payload.member_entity_id, payload.position)
        db.commit()
        return expand_collection(db, collection_id)
    except (CatalogDomainError, IntegrityError) as error:
        db.rollback()
        raise _domain_error(error) from error


@router.get("/collections/{collection_id}", response_model=CollectionNode)
def get_collection_tree(collection_id: int, db: Session = Depends(get_db)):
    try:
        return expand_collection(db, collection_id)
    except CatalogDomainError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/creators", response_model=list[CreatorRead])
def list_creators(db: Session = Depends(get_db)):
    return list(db.scalars(select(ReadingListCreator).order_by(ReadingListCreator.name)).all())


@router.post("/creators", response_model=CreatorRead, status_code=201)
def create_creator(payload: CreatorCreate, db: Session = Depends(get_db)):
    creator = ReadingListCreator(**payload.model_dump())
    db.add(creator)
    db.commit()
    db.refresh(creator)
    return creator


def _list_read(item: ReadingList) -> ReadingListRead:
    return ReadingListRead(
        id=item.id,
        creator_id=item.creator_id,
        creator_name=item.creator.name,
        title=item.title,
        age_min_months=item.age_min_months,
        age_max_months=item.age_max_months,
        stage_label=item.stage_label,
        material_type=item.material_type,
        description=item.description,
        items=[ReadingListItemRead(id=row.id, entity=_entity_read(row.catalog_entity), **{key: getattr(row, key) for key in ReadingListItemCreate.model_fields}) for row in item.items],
    )


def _reading_list_query():
    return select(ReadingList).options(
        selectinload(ReadingList.creator),
        selectinload(ReadingList.items).selectinload(ReadingListItem.catalog_entity).selectinload(CatalogEntity.work).selectinload(Work.isbns),
        selectinload(ReadingList.items).selectinload(ReadingListItem.catalog_entity).selectinload(CatalogEntity.collection),
        selectinload(ReadingList.items).selectinload(ReadingListItem.catalog_entity).selectinload(CatalogEntity.categories).selectinload(CatalogEntityCategory.category),
    )


@router.get("/reading-lists", response_model=list[ReadingListRead])
def list_reading_lists(creator_id: int | None = None, db: Session = Depends(get_db)):
    statement = _reading_list_query().order_by(ReadingList.id.desc())
    if creator_id:
        statement = statement.where(ReadingList.creator_id == creator_id)
    return [_list_read(item) for item in db.scalars(statement).unique().all()]


@router.post("/reading-lists", response_model=ReadingListRead, status_code=201)
def create_reading_list(payload: ReadingListCreate, db: Session = Depends(get_db)):
    if db.get(ReadingListCreator, payload.creator_id) is None:
        raise HTTPException(status_code=404, detail="Creator not found")
    item = ReadingList(**payload.model_dump())
    db.add(item)
    db.commit()
    return _list_read(db.scalar(_reading_list_query().where(ReadingList.id == item.id)))


@router.get("/reading-lists/{list_id}", response_model=ReadingListRead)
def get_reading_list(list_id: int, db: Session = Depends(get_db)):
    item = db.scalar(_reading_list_query().where(ReadingList.id == list_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Reading list not found")
    return _list_read(item)


@router.post("/reading-lists/{list_id}/items", response_model=ReadingListRead)
def create_reading_list_item(list_id: int, payload: ReadingListItemCreate, db: Session = Depends(get_db)):
    if db.get(ReadingList, list_id) is None:
        raise HTTPException(status_code=404, detail="Reading list not found")
    if db.get(CatalogEntity, payload.catalog_entity_id) is None:
        raise HTTPException(status_code=404, detail="Catalog entity not found")
    item = ReadingListItem(reading_list_id=list_id, **payload.model_dump())
    db.add(item)
    db.commit()
    return get_reading_list(list_id, db)


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(category_type: str | None = None, db: Session = Depends(get_db)):
    statement = select(CatalogCategory).order_by(CatalogCategory.category_type, CatalogCategory.sort_order, CatalogCategory.id)
    if category_type:
        statement = statement.where(CatalogCategory.category_type == category_type)
    return list(db.scalars(statement).all())


@router.post("/categories", response_model=CategoryRead, status_code=201)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)):
    if payload.parent_id and db.get(CatalogCategory, payload.parent_id) is None:
        raise HTTPException(status_code=404, detail="Parent category not found")
    item = CatalogCategory(**payload.model_dump())
    db.add(item)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _domain_error(error) from error
    db.refresh(item)
    return item


@router.post("/catalog/entities/{entity_id}/categories", response_model=CatalogEntityRead)
def attach_category(entity_id: int, payload: EntityCategoryCreate, db: Session = Depends(get_db)):
    _get_entity(db, entity_id)
    if db.get(CatalogCategory, payload.category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found")
    link = db.get(CatalogEntityCategory, (entity_id, payload.category_id))
    if link:
        link.is_primary = payload.is_primary
    else:
        db.add(CatalogEntityCategory(catalog_entity_id=entity_id, **payload.model_dump()))
    db.commit()
    return _entity_read(_get_entity(db, entity_id))


def _require_work(db: Session, entity_id: int) -> None:
    if db.get(Work, entity_id) is None:
        raise HTTPException(status_code=404, detail="Work not found")


@router.put("/works/{entity_id}/difficulty", response_model=DifficultyProfileRead)
def put_difficulty(entity_id: int, payload: DifficultyProfileWrite, db: Session = Depends(get_db)):
    _require_work(db, entity_id)
    item = db.get(WorkDifficultyProfile, entity_id) or WorkDifficultyProfile(work_entity_id=entity_id)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.add(item)
    db.commit()
    return DifficultyProfileRead(work_entity_id=entity_id, **payload.model_dump())


@router.put("/works/{entity_id}/ability-requirement", response_model=AbilityRequirementRead)
def put_ability_requirement(entity_id: int, payload: AbilityRequirementWrite, db: Session = Depends(get_db)):
    _require_work(db, entity_id)
    item = db.get(WorkAbilityRequirement, entity_id) or WorkAbilityRequirement(work_entity_id=entity_id)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.add(item)
    db.commit()
    return AbilityRequirementRead(work_entity_id=entity_id, **payload.model_dump())


@router.get("/children", response_model=list[ChildRead])
def list_children(db: Session = Depends(get_db)):
    return list(db.scalars(select(ChildProfile).order_by(ChildProfile.id)).all())


@router.post("/children", response_model=ChildRead, status_code=201)
def create_child(payload: ChildCreate, db: Session = Depends(get_db)):
    item = ChildProfile(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/children/{child_id}/abilities/{language_code}", response_model=ChildAbilityRead)
def put_child_ability(child_id: int, language_code: str, payload: ChildAbilityWrite, db: Session = Depends(get_db)):
    if db.get(ChildProfile, child_id) is None:
        raise HTTPException(status_code=404, detail="Child not found")
    item = db.get(ChildAbilityProfile, (child_id, language_code)) or ChildAbilityProfile(child_id=child_id, language_code=language_code)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.add(item)
    db.commit()
    return ChildAbilityRead(child_id=child_id, language_code=language_code, **payload.model_dump())


@router.put("/children/{child_id}/entities/{entity_id}", response_model=ChildAnnotationRead)
def put_child_annotation(child_id: int, entity_id: int, payload: ChildAnnotationWrite, db: Session = Depends(get_db)):
    if db.get(ChildProfile, child_id) is None:
        raise HTTPException(status_code=404, detail="Child not found")
    _get_entity(db, entity_id)
    item = db.get(ChildEntityAnnotation, (child_id, entity_id)) or ChildEntityAnnotation(child_id=child_id, catalog_entity_id=entity_id)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.add(item)
    db.commit()
    effective, source = effective_independent_reading(db, child_id, entity_id)
    return ChildAnnotationRead(child_id=child_id, catalog_entity_id=entity_id, effective_independent_reading=effective, effective_source=source, **payload.model_dump())


@router.get("/children/{child_id}/entities/{entity_id}", response_model=ChildAnnotationRead)
def get_child_annotation(child_id: int, entity_id: int, db: Session = Depends(get_db)):
    if db.get(ChildProfile, child_id) is None:
        raise HTTPException(status_code=404, detail="Child not found")
    entity = _get_entity(db, entity_id)
    item = db.get(ChildEntityAnnotation, (child_id, entity_id))
    effective, source = effective_independent_reading(db, child_id, entity_id)
    return ChildAnnotationRead(
        child_id=child_id,
        catalog_entity_id=entity_id,
        independent_reading_override=item.independent_reading_override if item else None,
        retry_after_date=item.retry_after_date if item else None,
        note=item.note if item else None,
        effective_independent_reading=effective,
        effective_source=source,
    )


@router.get("/catalog/entities/{entity_id}/source-stats", response_model=list[SourceStatRead])
def list_source_stats(entity_id: int, db: Session = Depends(get_db)):
    _get_entity(db, entity_id)
    return list(db.scalars(select(CatalogSourceStat).where(CatalogSourceStat.catalog_entity_id == entity_id)).all())


@router.post("/catalog/entities/{entity_id}/source-stats", response_model=SourceStatRead, status_code=201)
def create_source_stat(entity_id: int, payload: SourceStatCreate, db: Session = Depends(get_db)):
    _get_entity(db, entity_id)
    item = CatalogSourceStat(catalog_entity_id=entity_id, **payload.model_dump())
    db.add(item)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _domain_error(error) from error
    db.refresh(item)
    return item
