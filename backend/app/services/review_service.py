from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterator

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.catalog import (
    ALLOWED_ENTITY_TYPES,
    CatalogEntity,
    CatalogEntityReadingPen,
    CatalogIsbn,
    ReadingList,
    ReadingListItem,
    ReadingPenModel,
    Work,
    normalize_search_text,
)
from app.models.review import (
    ResearchCatalogCandidate,
    ResearchSource,
    ResearchSubject,
    ResearchSubjectRelation,
    ResearchSubjectSource,
    ReviewActionLog,
    ReviewBatch,
    ReviewDataConflict,
    ReviewItem,
    ReviewItemSubject,
)
from app.services.catalog_service import CatalogDomainError, add_collection_item, add_isbn, create_catalog_entity


SOURCE_ROOT = Path(__file__).resolve().parents[3] / "source_data"
TERMINAL_ITEM_STATUSES = frozenset({"resolved", "ignored"})
STRONG_MATCH_SCORE = Decimal("0.9200")


class ReviewDomainError(ValueError):
    pass


class StaleReviewError(ReviewDomainError):
    pass


class DuplicateCandidateError(ReviewDomainError):
    def __init__(self, candidates: list[ResearchCatalogCandidate]):
        self.candidate_ids = [row.catalog_entity_id for row in candidates]
        super().__init__(f"Strong Catalog candidate appeared; review again: {self.candidate_ids}")


def _plain_title(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split())


def _source_path(relative_path: str) -> Path:
    normalized = relative_path.replace("\\", "/")
    if normalized.startswith("source_data/"):
        normalized = normalized[len("source_data/") :]
    candidate = (SOURCE_ROOT / normalized).resolve()
    try:
        candidate.relative_to(SOURCE_ROOT.resolve())
    except ValueError as error:
        raise ReviewDomainError("source_file_path must stay inside source_data") from error
    if not candidate.is_file() or candidate.suffix.lower() != ".json":
        raise ReviewDomainError("Source JSON file not found")
    return candidate


def _extract_isbns(row: dict) -> list[str]:
    values: list[str] = []
    extracted = row.get("extracted") or {}
    other = extracted.get("other_info") or row.get("other_info") or {}
    raw_import = other.get("raw_import") or {}
    edition = other.get("edition") or {}
    for value in (raw_import.get("raw_isbn"), edition.get("isbn10"), edition.get("isbn13")):
        if value and str(value) not in values:
            values.append(str(value))
    for identifier in other.get("identifiers") or []:
        if isinstance(identifier, dict) and str(identifier.get("type", "")).lower() in {"isbn", "isbn10", "isbn13"}:
            value = identifier.get("value")
            if value and str(value) not in values:
                values.append(str(value))
    return values


def _proposed_type(row: dict) -> str | None:
    value = ((row.get("analysis") or {}).get("possible_entity_type") or "").lower()
    if value in ALLOWED_ENTITY_TYPES:
        return value
    extracted = row.get("extracted") or {}
    other = extracted.get("other_info") or row.get("other_info") or {}
    legacy = str(other.get("legacy_item_type") or (other.get("raw_import") or {}).get("raw_metadata", {}).get("item_type") or "").lower()
    aliases = {"collection": "series", "graded_reader": "series", "video": "animation"}
    value = aliases.get(legacy, legacy)
    return value if value in ALLOWED_ENTITY_TYPES else None


def _age_months(age: dict | None, which: str) -> int | None:
    if not age:
        return None
    value = age.get(which)
    if value is None:
        return None
    multiplier = 12 if age.get("unit") == "years" else 1
    return round(float(value) * multiplier)


STRONG_RECOMMENDATION_PATTERN = re.compile(r"强烈推荐|重点推荐|非常推荐|必读|首推|这个阶段一定要读|这个阶段最推荐")


def parse_recommendation_emphasis(value) -> tuple[bool, str | None]:
    if value is None:
        return False, None
    candidates = value if isinstance(value, (list, tuple)) else [value]
    for raw_candidate in candidates:
        candidate = str(raw_candidate).strip()
        for match in STRONG_RECOMMENDATION_PATTERN.finditer(candidate):
            prefix = candidate[max(0, match.start() - 8):match.start()]
            if not re.search(r"(?:不|非|未|没有|并非)(?:是|属于|算|算作)?\s*$", prefix):
                return True, match.group(0)
    return False, None


def _recommendation_emphasis_fields(extracted: dict, raw_import: dict) -> tuple[bool, str | None]:
    other = extracted.get("other_info") or {}
    if "is_strong_recommendation" in extracted:
        strong = bool(extracted["is_strong_recommendation"])
        text = str(extracted.get("recommendation_emphasis_text") or "").strip() or None
        return strong, text if strong else None
    explicit_strength = extracted.get("recommendation_strength")
    explicit_text = extracted.get("recommendation_emphasis_text") or extracted.get("recommendation_strength_text")
    if explicit_strength is None and isinstance(other, dict):
        explicit_strength = other.get("recommendation_strength")
    if explicit_text is None and isinstance(other, dict):
        explicit_text = other.get("recommendation_strength_text")
    text_value = str(explicit_text).strip() if explicit_text is not None else None
    text_value = text_value or None
    if explicit_strength is not None:
        strong = str(explicit_strength) == "3"
        if strong and not text_value:
            for source_value in (extracted.get("note"), extracted.get("comment")):
                _, matched = parse_recommendation_emphasis(source_value)
                if matched:
                    text_value = matched
                    break
        return strong, text_value if strong else None
    if text_value:
        strong, _ = parse_recommendation_emphasis(text_value)
        if strong:
            return True, text_value
    if text_value is None:
        for source_value in (
            extracted.get("comment"), extracted.get("note"),
            other.get("emphasis") if isinstance(other, dict) else None,
            raw_import.get("manual_note") if isinstance(raw_import, dict) else None,
        ):
            strong, matched = parse_recommendation_emphasis(source_value)
            if strong:
                return True, matched
    return False, None


def extract_review_payload(row: dict) -> dict:
    extracted = row.get("extracted") or {}
    other = extracted.get("other_info") or {}
    raw_import = other.get("raw_import") or {}
    age = extracted.get("recommended_age") or {}
    stage = other.get("stage") or {}
    minimum = stage.get("recommended_age_min_months")
    maximum = stage.get("recommended_age_max_months")
    is_strong_recommendation, recommendation_emphasis_text = _recommendation_emphasis_fields(extracted, raw_import)
    return {
        "normalized_title": _plain_title(extracted.get("title") or row.get("raw_title")),
        "proposed_entity_type": _proposed_type(row),
        "recommended_age_min_months": minimum if minimum is not None else _age_months(age, "min"),
        "recommended_age_max_months": maximum if maximum is not None else _age_months(age, "max"),
        "source_ar_text": extracted.get("ar") or raw_import.get("raw_ar"),
        "source_lexile_text": extracted.get("lexile") or raw_import.get("raw_lexile"),
        "source_level_text": extracted.get("level") or raw_import.get("raw_level"),
        "is_strong_recommendation": is_strong_recommendation,
        "recommendation_emphasis_text": recommendation_emphasis_text,
        "comment": extracted.get("comment"),
        "note": extracted.get("note") or raw_import.get("manual_note"),
        "isbns": _extract_isbns(row),
    }


def research_fingerprint(title: str, entity_type: str | None, isbns: list[str] | None = None, parent_context: str | None = None) -> str:
    identity = {
        "title": normalize_search_text(title),
        "entity_type": entity_type,
        "isbns": sorted(isbns or []),
        "parent_context": normalize_search_text(parent_context),
    }
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _find_reusable_subject(db: Session, fingerprint: str) -> ResearchSubject | None:
    rows = list(db.scalars(select(ResearchSubject).where(ResearchSubject.research_fingerprint == fingerprint)).all())
    if not rows:
        return None
    return min(rows, key=lambda row: (row.resolved_catalog_entity_id is None, row.research_status != "ready", row.id))


def import_source_file(db: Session, source_file_path: str, target_reading_list_id: int | None = None) -> tuple[ReviewBatch, bool]:
    path = _source_path(source_file_path)
    raw_bytes = path.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    try:
        document = json.loads(raw_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReviewDomainError("Source file is not valid UTF-8 JSON") from error
    if not isinstance(document, dict) or not isinstance(document.get("items"), list):
        raise ReviewDomainError("Source JSON must contain an items array")
    source_type = str(document.get("document_type") or "other")
    if target_reading_list_id is not None:
        if source_type != "reading_list":
            raise ReviewDomainError("Only reading-list imports can target a reading list")
        if db.get(ReadingList, target_reading_list_id) is None:
            raise ReviewDomainError("Target reading list not found")
    relative = path.relative_to(SOURCE_ROOT).as_posix()
    import_key = hashlib.sha256(f"{relative}|{sha256}|{source_type}|{target_reading_list_id or '-'}".encode()).hexdigest()
    existing = db.scalar(select(ReviewBatch).where(ReviewBatch.import_key == import_key))
    if existing:
        return existing, False

    source_name = ((document.get("list") or {}).get("title") or (document.get("source") or {}).get("name") or path.stem)
    batch = ReviewBatch(
        source_type=source_type,
        source_name=str(source_name),
        source_file_path=relative,
        source_content_sha256=sha256,
        import_key=import_key,
        target_reading_list_id=target_reading_list_id,
        status="researching",
    )
    db.add(batch)
    db.flush()
    touched_subject_ids: set[int] = set()
    for index, raw_row in enumerate(document["items"], 1):
        if not isinstance(raw_row, dict):
            raw_row = {"raw_value": raw_row}
        extracted = extract_review_payload(raw_row)
        item = ReviewItem(
            batch_id=batch.id,
            source_item_key=f"row:{index}",
            position=raw_row.get("position") if isinstance(raw_row.get("position"), int) else index,
            raw_payload=raw_row,
            extracted_payload=extracted,
            status="ready",
        )
        db.add(item)
        db.flush()
        fingerprint = research_fingerprint(
            extracted["normalized_title"], extracted["proposed_entity_type"], extracted["isbns"]
        )
        subject = _find_reusable_subject(db, fingerprint)
        if subject is None:
            subject = ResearchSubject(
                proposed_entity_type=extracted["proposed_entity_type"],
                proposed_display_title=extracted["normalized_title"],
                research_fingerprint=fingerprint,
                research_status="pending",
            )
            db.add(subject)
            db.flush()
        db.add(ReviewItemSubject(review_item_id=item.id, research_subject_id=subject.id, subject_role="primary"))
        touched_subject_ids.add(subject.id)

    db.flush()
    for subject_id in touched_subject_ids:
        refresh_catalog_candidates(db, db.get(ResearchSubject, subject_id))
    batch.total_items = len(document["items"])
    batch.status = "ready"
    return batch, True


def _fact_entry(facts: dict | list | None, key: str) -> dict | None:
    if not isinstance(facts, dict):
        return None
    value = facts.get(key)
    return value if isinstance(value, dict) and "value" in value else None


def _fact_value(facts: dict | list | None, key: str, require_source: bool = False):
    entry = _fact_entry(facts, key)
    if entry is None or (require_source and not entry.get("source_ids")):
        return None
    return entry.get("value")


def _objective_fact_value(db: Session, subject: ResearchSubject, key: str):
    entry = _fact_entry(subject.facts_json, key)
    if entry is None or not entry.get("source_ids"):
        return None
    linked_ids = set(
        db.scalars(
            select(ResearchSubjectSource.research_source_id).where(
                ResearchSubjectSource.research_subject_id == subject.id,
                ResearchSubjectSource.research_source_id.in_(entry["source_ids"]),
            )
        ).all()
    )
    return entry.get("value") if linked_ids else None


def _entity_identity_values(entity: CatalogEntity) -> list[str]:
    return [entity.display_title, entity.title_zh or "", entity.title_en or "", *(entity.aliases or [])]


def refresh_catalog_candidates(db: Session, subject: ResearchSubject | None) -> list[ResearchCatalogCandidate]:
    if subject is None:
        raise ReviewDomainError("Research subject not found")
    db.execute(delete(ResearchCatalogCandidate).where(ResearchCatalogCandidate.research_subject_id == subject.id))
    title = normalize_search_text(subject.proposed_display_title)
    facts = subject.facts_json
    isbns = _fact_value(facts, "isbns") or _fact_value(facts, "isbn") or []
    if isinstance(isbns, str):
        isbns = [isbns]
    isbn_values = {"".join(ch for ch in str(value).upper() if ch.isdigit() or ch == "X") for value in isbns}
    entities = list(
        db.scalars(
            select(CatalogEntity).options(selectinload(CatalogEntity.work).selectinload(Work.isbns))
        ).unique().all()
    )
    scored: list[tuple[Decimal, CatalogEntity, list[str]]] = []
    for entity in entities:
        reasons: list[str] = []
        normalized_values = [normalize_search_text(value) for value in _entity_identity_values(entity) if value]
        similarity = max((SequenceMatcher(None, title, value).ratio() for value in normalized_values), default=0.0)
        if title and title in normalized_values:
            score = Decimal("0.9600")
            reasons.append("标题或别名精确匹配")
        elif title and any(title in value or value in title for value in normalized_values):
            score = Decimal("0.8200")
            reasons.append("标题包含匹配")
        else:
            score = Decimal(str(round(similarity * 0.78, 4)))
            if similarity >= 0.55:
                reasons.append("标题相似")
        entity_isbns = {row.isbn_val for row in (entity.work.isbns if entity.work else [])}
        if isbn_values & entity_isbns:
            score = Decimal("1.0000")
            reasons.insert(0, "ISBN 精确匹配")
        if subject.resolved_catalog_entity_id == entity.id:
            score = Decimal("1.0000")
            reasons.insert(0, "此前已人工确认")
        if subject.proposed_entity_type:
            if entity.entity_type == subject.proposed_entity_type:
                score = min(Decimal("1.0000"), score + Decimal("0.0300"))
                reasons.append("Entity Type 一致")
            else:
                score = max(Decimal("0"), score - Decimal("0.1200"))
                reasons.append("Entity Type 不同")
        if score >= Decimal("0.4000"):
            scored.append((score, entity, reasons))
    scored.sort(key=lambda row: (-row[0], row[1].id))
    rows: list[ResearchCatalogCandidate] = []
    for rank, (score, entity, reasons) in enumerate(scored[:10], 1):
        candidate = ResearchCatalogCandidate(
            research_subject_id=subject.id,
            catalog_entity_id=entity.id,
            match_score=score,
            match_reasons=reasons,
            rank_no=rank,
        )
        db.add(candidate)
        rows.append(candidate)
    db.flush()
    return rows


def create_research_subject(db: Session, values: dict) -> ResearchSubject:
    review_item_id = values.pop("review_item_id", None)
    role = values.pop("subject_role", "discovered_member")
    title = values.get("proposed_display_title")
    values["research_fingerprint"] = research_fingerprint(
        title, values.get("proposed_entity_type"), _fact_value(values.get("facts_json"), "isbns") or []
    )
    subject = ResearchSubject(**values)
    db.add(subject)
    db.flush()
    if review_item_id is not None:
        if db.get(ReviewItem, review_item_id) is None:
            raise ReviewDomainError("Review item not found")
        if role == "primary" and db.scalar(
            select(ReviewItemSubject).where(
                ReviewItemSubject.review_item_id == review_item_id,
                ReviewItemSubject.subject_role == "primary",
            )
        ):
            raise ReviewDomainError("A review item can only have one primary subject")
        db.add(ReviewItemSubject(review_item_id=review_item_id, research_subject_id=subject.id, subject_role=role))
    refresh_catalog_candidates(db, subject)
    return subject


def update_research_subject(db: Session, subject: ResearchSubject, values: dict) -> ResearchSubject:
    sources = values.pop("sources", None)
    for key, value in values.items():
        if value is not None or key in {"facts_json", "ai_inferences_json", "manual_note"}:
            setattr(subject, key, value)
    if sources is not None:
        for source_values in sources:
            source = db.scalar(
                select(ResearchSource).where(
                    ResearchSource.source_url == source_values["source_url"],
                    ResearchSource.source_title == source_values.get("source_title"),
                )
            )
            if source is None:
                source = ResearchSource(**source_values)
                db.add(source)
                db.flush()
            if db.get(ResearchSubjectSource, (subject.id, source.id)) is None:
                db.add(ResearchSubjectSource(research_subject_id=subject.id, research_source_id=source.id))
    subject.research_fingerprint = research_fingerprint(
        subject.proposed_display_title or "",
        subject.proposed_entity_type,
        _fact_value(subject.facts_json, "isbns") or [],
    )
    refresh_catalog_candidates(db, subject)
    return subject


def _relation_reaches(db: Session, start_id: int, target_id: int) -> bool:
    pending = [start_id]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        children = list(
            db.scalars(
                select(ResearchSubjectRelation.member_subject_id).where(
                    ResearchSubjectRelation.parent_subject_id == current,
                    ResearchSubjectRelation.relation_type == "contains",
                    ResearchSubjectRelation.review_status != "rejected",
                )
            )
        )
        if target_id in children:
            return True
        pending.extend(children)
    return False


def create_research_relation(db: Session, values: dict) -> ResearchSubjectRelation:
    parent_id = values["parent_subject_id"]
    member_id = values["member_subject_id"]
    if db.get(ResearchSubject, parent_id) is None or db.get(ResearchSubject, member_id) is None:
        raise ReviewDomainError("Research subject not found")
    if values.get("relation_type", "contains") == "contains" and _relation_reaches(db, member_id, parent_id):
        raise ReviewDomainError("Research relation would create a cycle")
    existing = db.scalar(
        select(ResearchSubjectRelation).where(
            ResearchSubjectRelation.parent_subject_id == parent_id,
            ResearchSubjectRelation.member_subject_id == member_id,
            ResearchSubjectRelation.relation_type == values.get("relation_type", "contains"),
        )
    )
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        return existing
    relation = ResearchSubjectRelation(**values)
    db.add(relation)
    db.flush()
    return relation


def _primary_subject(db: Session, item_id: int) -> ResearchSubject:
    links = list(
        db.scalars(
            select(ReviewItemSubject).where(
                ReviewItemSubject.review_item_id == item_id,
                ReviewItemSubject.subject_role == "primary",
            )
        ).all()
    )
    if len(links) != 1:
        raise ReviewDomainError("Review item must have exactly one primary subject")
    subject = db.get(ResearchSubject, links[0].research_subject_id)
    if subject is None:
        raise ReviewDomainError("Primary research subject not found")
    return subject


def _json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def _record_conflict(db: Session, item: ReviewItem, subject: ResearchSubject, entity: CatalogEntity, field: str, existing, proposed) -> None:
    duplicate = db.scalar(
        select(ReviewDataConflict).where(
            ReviewDataConflict.review_item_id == item.id,
            ReviewDataConflict.field_path == field,
            ReviewDataConflict.status == "pending",
        )
    )
    if duplicate is None:
        db.add(
            ReviewDataConflict(
                review_item_id=item.id,
                research_subject_id=subject.id,
                catalog_entity_id=entity.id,
                field_path=field,
                existing_value=_json_value(existing),
                proposed_value=_json_value(proposed),
            )
        )


def _set_or_conflict(db: Session, item: ReviewItem, subject: ResearchSubject, entity: CatalogEntity, target, attribute: str, field_path: str, proposed) -> None:
    if proposed is None:
        return
    existing = getattr(target, attribute)
    comparable_existing = str(existing) if isinstance(existing, Decimal) else existing
    comparable_proposed = str(proposed) if isinstance(existing, Decimal) else proposed
    if existing is None:
        setattr(target, attribute, proposed)
    elif comparable_existing != comparable_proposed:
        _record_conflict(db, item, subject, entity, field_path, existing, proposed)


def _apply_objective_facts(db: Session, item: ReviewItem, subject: ResearchSubject, entity: CatalogEntity) -> None:
    facts = subject.facts_json
    _set_or_conflict(db, item, subject, entity, entity, "description", "catalog.description", _objective_fact_value(db, subject, "description"))
    _set_or_conflict(db, item, subject, entity, entity, "cover_url", "catalog.cover_url", _objective_fact_value(db, subject, "cover"))
    if entity.work:
        mappings = {
            "author": ("author_text", "work.author_text"),
            "language": ("language_code", "work.language_code"),
            "page_count": ("page_count", "work.page_count"),
            "word_count": ("word_count", "work.word_count"),
            "headwords": ("headword_count", "work.headword_count"),
            "ar": ("ar_level", "work.ar_level"),
            "lexile": ("lexile_code", "work.lexile_code"),
        }
        for fact_key, (attribute, field_path) in mappings.items():
            _set_or_conflict(
                db, item, subject, entity, entity.work, attribute, field_path, _objective_fact_value(db, subject, fact_key)
            )
    pen_names = _objective_fact_value(db, subject, "reading_pens") or []
    if isinstance(pen_names, str):
        pen_names = [pen_names]
    for name in pen_names:
        normalized = normalize_search_text(str(name))
        if not normalized:
            continue
        pen = db.scalar(select(ReadingPenModel).where(ReadingPenModel.normalized_name == normalized))
        if pen is None:
            pen = ReadingPenModel(name=str(name), normalized_name=normalized)
            db.add(pen)
            db.flush()
        if db.get(CatalogEntityReadingPen, (entity.id, pen.id)) is None:
            db.add(CatalogEntityReadingPen(catalog_entity_id=entity.id, reading_pen_model_id=pen.id))
    isbn_values = _objective_fact_value(db, subject, "isbns") or _objective_fact_value(db, subject, "isbn") or []
    if isinstance(isbn_values, str):
        isbn_values = [isbn_values]
    for isbn in isbn_values:
        if not entity.work:
            _record_conflict(db, item, subject, entity, "work.isbn", None, isbn)
            continue
        try:
            add_isbn(db, entity.id, str(isbn))
        except CatalogDomainError:
            _record_conflict(db, item, subject, entity, "work.isbn", None, isbn)


def _create_entity_from_subject(db: Session, item: ReviewItem, subject: ResearchSubject) -> CatalogEntity:
    entity_type = subject.proposed_entity_type
    title = _plain_title(subject.proposed_display_title)
    if entity_type not in ALLOWED_ENTITY_TYPES or not title:
        raise ReviewDomainError("A title and valid Entity Type are required before creating Catalog data")
    entity = create_catalog_entity(
        db,
        entity_type=entity_type,
        display_title=title,
        title_zh=subject.proposed_title_zh,
        title_en=subject.proposed_title_en,
        aliases=subject.proposed_aliases,
    )
    _apply_objective_facts(db, item, subject, entity)
    subject.resolution_status = "created"
    subject.resolved_catalog_entity_id = entity.id
    return entity


def _bind_subject(subject: ResearchSubject, entity: CatalogEntity, status: str) -> None:
    if subject.resolved_catalog_entity_id is not None and subject.resolved_catalog_entity_id != entity.id:
        raise ReviewDomainError("This research subject has a different prior human resolution")
    subject.resolution_status = status
    subject.resolved_catalog_entity_id = entity.id


def _resolve_structure(db: Session, item: ReviewItem, selected_ids: set[int]) -> dict[int, CatalogEntity]:
    resolved: dict[int, CatalogEntity] = {}
    for subject_id in selected_ids:
        subject = db.get(ResearchSubject, subject_id)
        if subject is None:
            raise ReviewDomainError(f"Research subject not found: {subject_id}")
        if subject.resolved_catalog_entity_id:
            entity = db.get(CatalogEntity, subject.resolved_catalog_entity_id)
            if entity:
                resolved[subject.id] = entity
                continue
        candidates = refresh_catalog_candidates(db, subject)
        strong = [row for row in candidates if row.match_score is not None and row.match_score >= STRONG_MATCH_SCORE]
        if len(strong) > 1:
            raise DuplicateCandidateError(strong)
        if strong:
            entity = db.get(CatalogEntity, strong[0].catalog_entity_id)
            _bind_subject(subject, entity, "matched")
        else:
            entity = _create_entity_from_subject(db, item, subject)
        resolved[subject.id] = entity
    relations = list(
        db.scalars(
            select(ResearchSubjectRelation).where(
                ResearchSubjectRelation.parent_subject_id.in_(selected_ids),
                ResearchSubjectRelation.member_subject_id.in_(selected_ids),
                ResearchSubjectRelation.relation_type == "contains",
                ResearchSubjectRelation.review_status != "rejected",
            )
        ).all()
    )
    for relation in relations:
        parent = resolved[relation.parent_subject_id]
        member = resolved[relation.member_subject_id]
        add_collection_item(db, parent.id, member.id, relation.position)
        relation.review_status = "accepted"
    return resolved


def _commit_source_relation(db: Session, item: ReviewItem, entity: CatalogEntity) -> None:
    if item.committed_reading_list_item_id is not None:
        return
    batch = item.batch
    if batch.source_type != "reading_list" or batch.target_reading_list_id is None:
        return
    if db.get(ReadingList, batch.target_reading_list_id) is None:
        raise ReviewDomainError("Target reading list no longer exists")
    extracted = item.extracted_payload if isinstance(item.extracted_payload, dict) else {}
    relation = ReadingListItem(
        reading_list_id=batch.target_reading_list_id,
        catalog_entity_id=entity.id,
        position=item.position,
        stage_label=(item.raw_payload.get("extracted", {}).get("other_info", {}).get("stage", {}).get("title") if isinstance(item.raw_payload, dict) else None),
        recommended_age_min_months=extracted.get("recommended_age_min_months"),
        recommended_age_max_months=extracted.get("recommended_age_max_months"),
        source_ar_text=str(extracted.get("source_ar_text")) if extracted.get("source_ar_text") is not None else None,
        source_lexile_text=str(extracted.get("source_lexile_text")) if extracted.get("source_lexile_text") is not None else None,
        source_level_text=str(extracted.get("source_level_text")) if extracted.get("source_level_text") is not None else None,
        is_strong_recommendation=extracted.get("is_strong_recommendation", False),
        recommendation_emphasis_text=extracted.get("recommendation_emphasis_text"),
        comment=extracted.get("comment"),
        note=extracted.get("note"),
    )
    db.add(relation)
    db.flush()
    item.committed_reading_list_item_id = relation.id


def _recount_batch(db: Session, batch: ReviewBatch) -> None:
    resolved = db.scalar(
        select(func.count(ReviewItem.id)).where(
            ReviewItem.batch_id == batch.id,
            ReviewItem.status.in_(TERMINAL_ITEM_STATUSES),
        )
    ) or 0
    batch.resolved_items = resolved
    if batch.total_items and resolved >= batch.total_items:
        batch.status = "completed"
    elif resolved:
        batch.status = "reviewing"
    else:
        batch.status = "ready"


def resolve_review_item(db: Session, item_id: int, values: dict) -> ReviewItem:
    item = db.scalar(select(ReviewItem).where(ReviewItem.id == item_id).with_for_update())
    if item is None:
        raise ReviewDomainError("Review item not found")
    decision = values["decision"]
    if item.status in TERMINAL_ITEM_STATUSES:
        if item.decision == decision and (
            decision != "match_existing" or item.resolved_catalog_entity_id == values.get("catalog_entity_id")
        ):
            return item
        raise ReviewDomainError("Review item is already resolved")
    if item.lock_version != values["expected_version"]:
        raise StaleReviewError("Review item changed; reload before submitting")
    subject = _primary_subject(db, item.id)
    entity: CatalogEntity | None = None
    if decision == "ignore":
        item.status = "ignored"
    elif decision == "match_existing":
        entity = db.get(CatalogEntity, values["catalog_entity_id"])
        if entity is None:
            raise ReviewDomainError("Catalog entity not found")
        _bind_subject(subject, entity, "matched")
        _apply_objective_facts(db, item, subject, entity)
        item.status = "resolved"
    else:
        candidates = refresh_catalog_candidates(db, subject)
        strong = [row for row in candidates if row.match_score is not None and row.match_score >= STRONG_MATCH_SCORE]
        if strong:
            raise DuplicateCandidateError(strong)
        entity = _create_entity_from_subject(db, item, subject)
        item.status = "resolved"

    if entity is not None:
        item.resolved_catalog_entity_id = entity.id
        selected = set(values.get("include_structure_subject_ids") or []) | {subject.id}
        if len(selected) > 1:
            _resolve_structure(db, item, selected)
        _commit_source_relation(db, item, entity)
    item.decision = decision
    item.manual_note = values.get("manual_note")
    item.lock_version += 1
    item.resolved_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(
        ReviewActionLog(
            review_item_id=item.id,
            action=decision,
            actor=values.get("actor"),
            details_json={
                "catalog_entity_id": entity.id if entity else None,
                "included_structure_subject_ids": values.get("include_structure_subject_ids") or [],
            },
        )
    )
    db.flush()
    _recount_batch(db, item.batch)
    return item


@contextmanager
def catalog_creation_lock(db: Session, subject: ResearchSubject | None) -> Iterator[None]:
    if subject is None or db.bind is None or db.bind.dialect.name != "mysql":
        yield
        return
    digest = (subject.research_fingerprint or hashlib.sha256(str(subject.id).encode()).hexdigest())[:48]
    name = f"reading-map-review:{digest}"
    acquired = db.scalar(text("SELECT GET_LOCK(:name, 10)"), {"name": name})
    if acquired != 1:
        raise ReviewDomainError("Could not acquire Catalog creation lock")
    try:
        yield
    finally:
        db.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": name})


def resolve_conflict(db: Session, conflict: ReviewDataConflict, status: str, actor: str | None, note: str | None) -> ReviewDataConflict:
    if conflict.status != "pending":
        raise ReviewDomainError("Conflict is already resolved")
    if status == "use_proposed":
        entity = conflict.catalog_entity
        mappings = {
            "catalog.description": (entity, "description"),
            "catalog.cover_url": (entity, "cover_url"),
            "work.author_text": (entity.work, "author_text"),
            "work.language_code": (entity.work, "language_code"),
            "work.page_count": (entity.work, "page_count"),
            "work.word_count": (entity.work, "word_count"),
            "work.headword_count": (entity.work, "headword_count"),
            "work.ar_level": (entity.work, "ar_level"),
            "work.lexile_code": (entity.work, "lexile_code"),
        }
        target = mappings.get(conflict.field_path)
        if target is None or target[0] is None:
            raise ReviewDomainError("This conflict field cannot be applied automatically")
        setattr(target[0], target[1], conflict.proposed_value)
    conflict.status = status
    conflict.manual_note = note
    if conflict.review_item_id:
        db.add(
            ReviewActionLog(
                review_item_id=conflict.review_item_id,
                action=f"conflict_{status}",
                actor=actor,
                details_json={"conflict_id": conflict.id, "field_path": conflict.field_path},
            )
        )
    return conflict


def subject_to_dict(db: Session, subject: ResearchSubject) -> dict:
    source_links = list(
        db.scalars(
            select(ResearchSubjectSource)
            .where(ResearchSubjectSource.research_subject_id == subject.id)
            .options(selectinload(ResearchSubjectSource.research_source))
        ).all()
    )
    candidates = list(
        db.scalars(
            select(ResearchCatalogCandidate)
            .where(ResearchCatalogCandidate.research_subject_id == subject.id)
            .options(selectinload(ResearchCatalogCandidate.catalog_entity))
            .order_by(ResearchCatalogCandidate.rank_no)
        ).all()
    )
    relations = list(
        db.scalars(
            select(ResearchSubjectRelation)
            .where(
                or_(
                    ResearchSubjectRelation.parent_subject_id == subject.id,
                    ResearchSubjectRelation.member_subject_id == subject.id,
                )
            )
            .options(
                selectinload(ResearchSubjectRelation.parent_subject),
                selectinload(ResearchSubjectRelation.member_subject),
            )
        ).all()
    )
    return {
        "id": subject.id,
        "proposed_entity_type": subject.proposed_entity_type,
        "proposed_display_title": subject.proposed_display_title,
        "proposed_title_zh": subject.proposed_title_zh,
        "proposed_title_en": subject.proposed_title_en,
        "proposed_aliases": subject.proposed_aliases,
        "facts_json": subject.facts_json,
        "ai_inferences_json": subject.ai_inferences_json,
        "research_status": subject.research_status,
        "resolution_status": subject.resolution_status,
        "resolved_catalog_entity_id": subject.resolved_catalog_entity_id,
        "manual_note": subject.manual_note,
        "research_version": subject.research_version,
        "researched_at": subject.researched_at,
        "sources": [
            {
                "id": link.research_source.id,
                "source_type": link.research_source.source_type,
                "source_url": link.research_source.source_url,
                "source_title": link.research_source.source_title,
                "fetched_at": link.research_source.fetched_at,
            }
            for link in source_links
        ],
        "candidates": [
            {
                "id": row.id,
                "catalog_entity_id": row.catalog_entity_id,
                "display_title": row.catalog_entity.display_title,
                "entity_type": row.catalog_entity.entity_type,
                "match_score": float(row.match_score) if row.match_score is not None else None,
                "match_reasons": row.match_reasons,
                "rank_no": row.rank_no,
            }
            for row in candidates
        ],
        "relations": [
            {
                "id": row.id,
                "parent_subject_id": row.parent_subject_id,
                "parent_title": row.parent_subject.proposed_display_title,
                "member_subject_id": row.member_subject_id,
                "member_title": row.member_subject.proposed_display_title,
                "relation_type": row.relation_type,
                "position": row.position,
                "evidence_type": row.evidence_type,
                "confidence": float(row.confidence) if row.confidence is not None else None,
                "review_status": row.review_status,
            }
            for row in relations
        ],
    }


def review_item_to_dict(db: Session, item: ReviewItem) -> dict:
    links = list(
        db.scalars(
            select(ReviewItemSubject)
            .where(ReviewItemSubject.review_item_id == item.id)
            .options(selectinload(ReviewItemSubject.research_subject))
        ).all()
    )
    subjects = []
    for link in sorted(links, key=lambda row: (row.subject_role != "primary", row.research_subject_id)):
        value = subject_to_dict(db, link.research_subject)
        value["subject_role"] = link.subject_role
        subjects.append(value)
    return {
        "id": item.id,
        "batch_id": item.batch_id,
        "source_item_key": item.source_item_key,
        "position": item.position,
        "raw_payload": item.raw_payload,
        "extracted_payload": item.extracted_payload,
        "status": item.status,
        "decision": item.decision,
        "resolved_catalog_entity_id": item.resolved_catalog_entity_id,
        "committed_reading_list_item_id": item.committed_reading_list_item_id,
        "manual_note": item.manual_note,
        "lock_version": item.lock_version,
        "resolved_at": item.resolved_at,
        "subjects": subjects,
    }
