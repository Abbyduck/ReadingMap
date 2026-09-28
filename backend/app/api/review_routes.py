from __future__ import annotations

from contextlib import ExitStack

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.review import ResearchSubject, ReviewBatch, ReviewDataConflict, ReviewItem, ReviewItemSubject
from app.schemas.review import (
    BulkMatchWrite,
    ConflictResolveWrite,
    ResearchRelationCreate,
    ResearchSubjectCreate,
    ResearchSubjectUpdate,
    ReviewBatchImport,
    ReviewBatchRead,
    ReviewDecisionWrite,
)
from app.services.catalog_service import CatalogDomainError
from app.services.review_service import (
    DuplicateCandidateError,
    ReviewDomainError,
    StaleReviewError,
    catalog_creation_lock,
    create_research_relation,
    create_research_subject,
    import_source_file,
    refresh_catalog_candidates,
    resolve_conflict,
    resolve_review_item,
    review_item_to_dict,
    subject_to_dict,
    update_research_subject,
)


router = APIRouter(prefix="/review", tags=["review"])


def _batch_read(batch: ReviewBatch) -> ReviewBatchRead:
    return ReviewBatchRead.model_validate(batch, from_attributes=True)


def _review_error(error: Exception) -> HTTPException:
    if isinstance(error, (StaleReviewError, DuplicateCandidateError)):
        return HTTPException(status_code=409, detail=str(error))
    return HTTPException(status_code=400, detail=str(error))


@router.get("/batches", response_model=list[ReviewBatchRead])
def list_review_batches(status: str | None = None, db: Session = Depends(get_db)):
    statement = select(ReviewBatch).order_by(ReviewBatch.id.desc())
    if status:
        statement = statement.where(ReviewBatch.status == status)
    return [_batch_read(row) for row in db.scalars(statement).all()]


@router.post("/batches/import")
def import_review_batch(payload: ReviewBatchImport, db: Session = Depends(get_db)):
    try:
        batch, created = import_source_file(db, payload.source_file_path, payload.target_reading_list_id)
        db.commit()
        db.refresh(batch)
    except (ReviewDomainError, CatalogDomainError, IntegrityError) as error:
        db.rollback()
        raise _review_error(error) from error
    return {"created": created, "batch": _batch_read(batch)}


@router.get("/items")
def list_review_items(
    batch_id: int | None = None,
    status: str | None = None,
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    statement = select(ReviewItem).order_by(ReviewItem.batch_id.desc(), ReviewItem.position, ReviewItem.id).limit(limit)
    if batch_id is not None:
        statement = statement.where(ReviewItem.batch_id == batch_id)
    if status:
        statement = statement.where(ReviewItem.status == status)
    return [review_item_to_dict(db, row) for row in db.scalars(statement).all()]


@router.get("/items/{item_id}")
def get_review_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ReviewItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Review item not found")
    return review_item_to_dict(db, item)


@router.post("/subjects")
def post_research_subject(payload: ResearchSubjectCreate, db: Session = Depends(get_db)):
    try:
        subject = create_research_subject(db, payload.model_dump())
        db.commit()
    except (ReviewDomainError, CatalogDomainError, IntegrityError) as error:
        db.rollback()
        raise _review_error(error) from error
    return subject_to_dict(db, subject)


@router.put("/subjects/{subject_id}")
def put_research_subject(subject_id: int, payload: ResearchSubjectUpdate, db: Session = Depends(get_db)):
    subject = db.get(ResearchSubject, subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Research subject not found")
    try:
        subject = update_research_subject(db, subject, payload.model_dump(exclude_unset=True))
        db.commit()
    except (ReviewDomainError, CatalogDomainError, IntegrityError) as error:
        db.rollback()
        raise _review_error(error) from error
    return subject_to_dict(db, subject)


@router.post("/subjects/{subject_id}/candidates")
def post_refresh_candidates(subject_id: int, db: Session = Depends(get_db)):
    subject = db.get(ResearchSubject, subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Research subject not found")
    refresh_catalog_candidates(db, subject)
    db.commit()
    return subject_to_dict(db, subject)


@router.post("/relations")
def post_research_relation(payload: ResearchRelationCreate, db: Session = Depends(get_db)):
    try:
        relation = create_research_relation(db, payload.model_dump())
        db.commit()
        db.refresh(relation)
    except (ReviewDomainError, CatalogDomainError, IntegrityError) as error:
        db.rollback()
        raise _review_error(error) from error
    return {
        "id": relation.id,
        "parent_subject_id": relation.parent_subject_id,
        "member_subject_id": relation.member_subject_id,
        "relation_type": relation.relation_type,
        "position": relation.position,
        "review_status": relation.review_status,
    }


def _primary_subject_for_item(db: Session, item_id: int) -> ResearchSubject | None:
    link = db.scalar(
        select(ReviewItemSubject).where(
            ReviewItemSubject.review_item_id == item_id,
            ReviewItemSubject.subject_role == "primary",
        )
    )
    return db.get(ResearchSubject, link.research_subject_id) if link else None


@router.post("/items/{item_id}/decision")
def post_review_decision(item_id: int, payload: ReviewDecisionWrite, db: Session = Depends(get_db)):
    subject = _primary_subject_for_item(db, item_id)
    try:
        lock_subjects = [row for row in [subject, *(db.get(ResearchSubject, subject_id) for subject_id in payload.include_structure_subject_ids)] if row]
        lock_subjects = sorted({row.id: row for row in lock_subjects}.values(), key=lambda row: (row.research_fingerprint or "", row.id))
        with ExitStack() as stack:
            for lock_subject in lock_subjects:
                stack.enter_context(catalog_creation_lock(db, lock_subject))
            item = resolve_review_item(db, item_id, payload.model_dump())
            db.commit()
    except (ReviewDomainError, CatalogDomainError, IntegrityError) as error:
        db.rollback()
        raise _review_error(error) from error
    return review_item_to_dict(db, item)


@router.post("/items/bulk-match")
def post_bulk_match(payload: BulkMatchWrite, db: Session = Depends(get_db)):
    resolved: list[int] = []
    try:
        for entry in payload.entries:
            item = resolve_review_item(
                db,
                entry.review_item_id,
                {
                    "decision": "match_existing",
                    "catalog_entity_id": entry.catalog_entity_id,
                    "expected_version": entry.expected_version,
                    "actor": payload.actor,
                    "manual_note": None,
                    "include_structure_subject_ids": [],
                },
            )
            resolved.append(item.id)
        db.commit()
    except (ReviewDomainError, CatalogDomainError, IntegrityError) as error:
        db.rollback()
        raise _review_error(error) from error
    return {"resolved_item_ids": resolved}


@router.get("/conflicts")
def list_conflicts(status: str | None = "pending", db: Session = Depends(get_db)):
    statement = select(ReviewDataConflict).order_by(ReviewDataConflict.id.desc())
    if status:
        statement = statement.where(ReviewDataConflict.status == status)
    return [
        {
            "id": row.id,
            "review_item_id": row.review_item_id,
            "research_subject_id": row.research_subject_id,
            "catalog_entity_id": row.catalog_entity_id,
            "field_path": row.field_path,
            "existing_value": row.existing_value,
            "proposed_value": row.proposed_value,
            "status": row.status,
            "manual_note": row.manual_note,
        }
        for row in db.scalars(statement).all()
    ]


@router.post("/conflicts/{conflict_id}/resolve")
def post_resolve_conflict(conflict_id: int, payload: ConflictResolveWrite, db: Session = Depends(get_db)):
    conflict = db.get(ReviewDataConflict, conflict_id)
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    try:
        resolve_conflict(db, conflict, payload.status, payload.actor, payload.manual_note)
        db.commit()
    except (ReviewDomainError, CatalogDomainError, IntegrityError) as error:
        db.rollback()
        raise _review_error(error) from error
    return {"id": conflict.id, "status": conflict.status}
