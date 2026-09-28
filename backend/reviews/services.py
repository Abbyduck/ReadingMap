"""Review staging, provenance and human-only Catalog commit workflow."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from contextlib import contextmanager
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import F, Q
from django.utils import timezone

from catalog.models import (
    ALLOWED_ENTITY_TYPES, COLLECTION_ENTITY_TYPES, CatalogCategory, CatalogEntity, CatalogEntityReadingPen, ReadingList,
    ReadingListItem, ReadingPenModel, normalize_search_text,
)
from catalog.services import CatalogDomainError, assign_entity_categories, add_collection_item, add_isbn, create_catalog_entity
from .models import (
    ResearchCatalogCandidate, ResearchSource, ResearchSubject, ResearchSubjectRelation,
    ResearchSubjectSource, ReviewActionLog, ReviewBatch, ReviewDataConflict, ReviewItem, ReviewItemSubject,
)

SOURCE_ROOT = Path(settings.BASE_DIR).parent / "source_data"
TERMINAL_ITEM_STATUSES = frozenset({"resolved", "ignored"})
STRONG_MATCH_SCORE = Decimal("0.9200")


class ReviewDomainError(ValueError):
    pass


class StaleReviewError(ReviewDomainError):
    pass


class DuplicateCandidateError(ReviewDomainError):
    def __init__(self, candidates):
        self.candidate_ids = [row.catalog_entity_id for row in candidates]
        super().__init__(f"Strong Catalog candidate appeared; review again: {self.candidate_ids}")


@contextmanager
def review_write_transaction():
    """Serialize review writes across MySQL processes and release only after commit.

    One lock also covers aliases and changed fingerprints: identity is deliberately
    not a unique Catalog title. Row locks protect the committed records themselves.
    Call this outermost, not from an already-open application transaction.
    """
    name = "reading-map:review-mutation-v2"
    acquired = False
    if connection.vendor == "mysql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 10)", [name])
            acquired = cursor.fetchone()[0] == 1
        if not acquired:
            raise ReviewDomainError("Review is busy; retry shortly")
    try:
        with transaction.atomic():
            yield
    finally:
        if acquired:
            with connection.cursor() as cursor:
                cursor.execute("SELECT RELEASE_LOCK(%s)", [name])


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


def read_batch_source(batch):
    """Read the batch's original file, never reconstruct it from researched items."""
    if not batch.source_file_path:
        raise ReviewDomainError("此批次没有关联原始 JSON 文件")
    path = _source_path(batch.source_file_path)
    try:
        raw_bytes = path.read_bytes()
        raw_text = raw_bytes.decode("utf-8-sig")
        document = json.loads(raw_text)
    except (OSError, UnicodeError, ValueError) as error:
        raise ReviewDomainError("原始 JSON 文件无法读取或格式无效") from error
    current_hash = hashlib.sha256(raw_bytes).hexdigest()
    return {
        "batch_id": batch.pk, "filename": path.name,
        "source_file_path": batch.source_file_path,
        "matches_import": current_hash == batch.source_content_sha256 if batch.source_content_sha256 else None,
        "document": document, "raw_text": raw_text,
    }


def _proposed_type(row: dict) -> str | None:
    value = ((row.get("analysis") or {}).get("possible_entity_type") or "").lower()
    if value in ALLOWED_ENTITY_TYPES:
        return value
    extracted = row.get("extracted") or {}
    other = extracted.get("other_info") or row.get("other_info") or {}
    legacy = str(other.get("legacy_item_type") or (other.get("raw_import") or {}).get("raw_metadata", {}).get("item_type") or "").lower()
    aliases = {"collection": "series", "graded_reader": "series", "video": "animation"}
    value = aliases.get(legacy, legacy)
    if value in ALLOWED_ENTITY_TYPES:
        return value
    title = _plain_title(extracted.get("title") or row.get("raw_title"))
    if re.fullmatch(r"[^()（）]{2,100}(?:系列|series)", title, re.IGNORECASE):
        return "series"
    return None


def _age_months(age: dict | None, which: str) -> int | None:
    if not age:
        return None
    value = age.get(which)
    if value is None:
        return None
    multiplier = 12 if age.get("unit") == "years" else 1
    return round(float(value) * multiplier)


def _source_measure_text(value):
    if isinstance(value, dict):
        value = value.get("raw")
    return None if value is None or str(value).strip().lower() in {"", "none", "null"} else str(value)


STRONG_RECOMMENDATION_PATTERN = re.compile(
    r"强烈推荐|重点推荐|非常推荐|必读|首推|这个阶段一定要读|这个阶段最推荐"
)


def parse_recommendation_emphasis(value) -> tuple[bool, str | None]:
    """Only source-explicit emphasis is strong; a list occurrence is ordinary."""
    if value is None:
        return False, None
    if isinstance(value, (list, tuple)):
        candidates = [str(part).strip() for part in value if str(part).strip()]
    else:
        candidates = [str(value).strip()]
    for candidate in candidates:
        for match in STRONG_RECOMMENDATION_PATTERN.finditer(candidate):
            prefix = candidate[max(0, match.start() - 8):match.start()]
            if not re.search(r"(?:不|非|未|没有|并非)(?:是|属于|算|算作)?\s*$", prefix):
                return True, match.group(0)
    return False, None


def _recommendation_emphasis_fields(extracted: dict, raw_import: dict) -> tuple[bool, str | None]:
    if "is_strong_recommendation" in extracted:
        strong = bool(extracted["is_strong_recommendation"])
        text = str(extracted.get("recommendation_emphasis_text") or "").strip() or None
        return strong, text if strong else None
    explicit_strength = extracted.get("recommendation_strength")
    explicit_text = extracted.get("recommendation_emphasis_text") or extracted.get("recommendation_strength_text")
    other = extracted.get("other_info") or {}
    if explicit_text is None and isinstance(other, dict):
        explicit_text = other.get("recommendation_strength_text")
    if explicit_strength is None and isinstance(other, dict):
        explicit_strength = other.get("recommendation_strength")

    text = str(explicit_text).strip() if explicit_text is not None else None
    text = text or None
    if explicit_strength is not None:
        strong = str(explicit_strength) == "3"
        if strong and not text:
            for source_value in (extracted.get("note"), extracted.get("comment")):
                _, matched = parse_recommendation_emphasis(source_value)
                if matched:
                    text = matched
                    break
        return strong, text if strong else None
    if text:
        strong, matched = parse_recommendation_emphasis(text)
        if strong:
            return True, text or matched

    if text is None:
        for source_value in (
            extracted.get("comment"),
            extracted.get("note"),
            other.get("emphasis") if isinstance(other, dict) else None,
            raw_import.get("manual_note") if isinstance(raw_import, dict) else None,
        ):
            strong, matched_text = parse_recommendation_emphasis(source_value)
            if strong:
                return True, matched_text
    return False, None


SOURCE_LOCATION_NOTE = re.compile(
    r"^(?:原图|来源(?:原图|图片)?)\s*[：:]?\s*第?\s*\d+\s*(?:页|行)(?:\s*第?\s*\d+\s*行)?$",
    re.IGNORECASE,
)


def clean_source_note(value):
    """Remove import coordinates while preserving meaningful reviewer notes."""
    if value is None:
        return None
    parts = [part.strip() for part in re.split(r"[；;]", str(value))]
    cleaned = "；".join(part for part in parts if part and not SOURCE_LOCATION_NOTE.fullmatch(part))
    return cleaned or None


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
        "source_ar_text": _source_measure_text(extracted.get("ar") or raw_import.get("raw_ar")),
        "source_lexile_text": _source_measure_text(extracted.get("lexile") or raw_import.get("raw_lexile")),
        "source_level_text": _source_measure_text(extracted.get("level") or raw_import.get("raw_level")),
        "is_strong_recommendation": is_strong_recommendation,
        "recommendation_emphasis_text": recommendation_emphasis_text,
        "comment": extracted.get("comment"),
        "note": clean_source_note(extracted.get("note") or raw_import.get("manual_note")),
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



def _find_reusable_subject(fingerprint):
    return sorted(
        ResearchSubject.objects.filter(research_fingerprint=fingerprint),
        key=lambda row: (row.resolved_catalog_entity_id is None, row.research_status != "ready", row.pk),
    )[:1]


def import_source_file(source_file_path, target_reading_list_id=None):
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
        if not ReadingList.objects.filter(pk=target_reading_list_id).exists():
            raise ReviewDomainError("Target reading list not found")
    relative = path.relative_to(SOURCE_ROOT).as_posix()
    import_key = hashlib.sha256(f"{relative}|{sha256}|{source_type}|{target_reading_list_id or '-'}".encode()).hexdigest()
    existing = ReviewBatch.objects.filter(import_key=import_key).first()
    if existing:
        return existing, False
    source_name = ((document.get("list") or {}).get("title") or (document.get("source") or {}).get("name") or path.stem)
    batch = ReviewBatch.objects.create(
        source_type=source_type, source_name=str(source_name), source_file_path=relative,
        source_content_sha256=sha256, import_key=import_key,
        target_reading_list_id=target_reading_list_id, status="researching",
    )
    touched = set()
    for index, raw_row in enumerate(document["items"], 1):
        if not isinstance(raw_row, dict):
            raw_row = {"raw_value": raw_row}
        try:
            extracted = extract_review_payload(raw_row)
        except (TypeError, ValueError, AttributeError) as error:
            raise ReviewDomainError(f"Invalid source item at row {index}") from error
        position = raw_row.get("position")
        item = ReviewItem.objects.create(
            batch=batch, source_item_key=f"row:{index}",
            position=position if isinstance(position, int) and position >= 0 else index,
            raw_payload=raw_row, extracted_payload=extracted, status="pending",
        )
        fingerprint = research_fingerprint(extracted["normalized_title"], extracted["proposed_entity_type"], extracted["isbns"])
        reused = _find_reusable_subject(fingerprint)
        subject = reused[0] if reused else ResearchSubject.objects.create(
            proposed_entity_type=extracted["proposed_entity_type"],
            proposed_display_title=extracted["normalized_title"],
            research_fingerprint=fingerprint,
        )
        ReviewItemSubject.objects.create(review_item=item, research_subject=subject, subject_role="primary")
        item.status = _review_status_for_research(subject.research_status)
        item.save(update_fields=["status"])
        touched.add(subject.pk)
    for subject in ResearchSubject.objects.filter(pk__in=touched):
        refresh_catalog_candidates(subject)
    batch.total_items = len(document["items"])
    _recount_batch(batch)
    return batch, True


def _fact_entry(facts, key):
    if not isinstance(facts, dict):
        return None
    entry = facts.get(key)
    return entry if isinstance(entry, dict) and "value" in entry else None


def _fact_value(facts, key):
    entry = _fact_entry(facts, key)
    return entry.get("value") if entry else None


def _normalized_language_code(value):
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    compact = re.sub(r"[\s_-]+", "", normalized)
    if not normalized:
        return None
    if any(token in normalized for token in ("中英", "双语", "bilingual")) or compact in {"zhen", "enzh"}:
        return "zh-en"
    if normalized in {"en", "eng", "english", "英文", "英语", "英語"}:
        return "en"
    if normalized in {"zh", "zho", "chi", "chinese", "中文", "汉语", "漢語"}:
        return "zh"
    return None


def _ensure_subject_language(subject, *, parent_subject=None, source_id=None):
    """Stage one of the three supported language codes for a discovered subject."""
    if _fact_entry(subject.facts_json, "language"):
        return False
    language = _normalized_language_code(_fact_value(parent_subject.facts_json, "language")) if parent_subject else None
    evidence_note = "继承主 Entity 的语言" if language else None
    if not language:
        title = subject.proposed_display_title or ""
        if subject.proposed_title_en or (re.search(r"[A-Za-z]", title) and not re.search(r"[\u3400-\u9fff]", title)):
            language = "en"
            evidence_note = "成员仅有英文名，保底推断为英文"
        elif subject.proposed_title_zh or re.search(r"[\u3400-\u9fff]", title):
            language = "zh"
            evidence_note = "成员仅有中文名，保底推断为中文"
    if not language or not isinstance(source_id, int):
        return False
    facts = dict(subject.facts_json or {})
    facts["language"] = {
        "value": language,
        "source_ids": [source_id],
        "evidence_note": evidence_note,
        "inherited_from_subject_id": parent_subject.pk if parent_subject and evidence_note.startswith("继承") else None,
    }
    subject.facts_json = facts
    subject.save(update_fields=["facts_json"])
    return True


def _objective_fact_value(subject, key):
    entry = _fact_entry(subject.facts_json, key)
    if not entry:
        return None
    # A human-confirmed Catalog Draft value is allowed to override or complete
    # sourced Research facts.  It remains staged on the ResearchSubject until
    # the final review transaction commits it to Catalog.
    if entry.get("reviewed_by_human") is True:
        return entry.get("value")
    if not isinstance(entry.get("source_ids"), list) or not entry["source_ids"]:
        return None
    ids = entry["source_ids"]
    if any(not isinstance(value, int) or isinstance(value, bool) for value in ids):
        return None
    linked = set(subject.source_links.filter(research_source_id__in=ids).values_list("research_source_id", flat=True))
    return entry.get("value") if linked else None


def _isbn_list(facts):
    values = _fact_value(facts, "isbns") or _fact_value(facts, "isbn") or []
    return [values] if isinstance(values, str) else values if isinstance(values, list) else []


def refresh_catalog_candidates(subject):
    if subject is None:
        raise ReviewDomainError("Research subject not found")
    ResearchCatalogCandidate.objects.filter(research_subject=subject).delete()
    title = normalize_search_text(subject.proposed_display_title)
    isbn_values = {"".join(ch for ch in str(value).upper() if ch.isdigit() or ch == "X") for value in _isbn_list(subject.facts_json)}
    scored = []
    for entity in CatalogEntity.objects.select_related("work").prefetch_related("work__isbns"):
        values = [entity.display_title, entity.title_zh, entity.title_en, *(entity.aliases or [])]
        normalized = [normalize_search_text(value) for value in values if value]
        similarity = max((SequenceMatcher(None, title, value).ratio() for value in normalized), default=0)
        reasons = []
        if title and title in normalized:
            score = Decimal("0.9600")
            reasons.append("标题或别名精确匹配")
        elif title and any(title in value or value in title for value in normalized):
            score = Decimal("0.8200")
            reasons.append("标题包含匹配")
        else:
            score = Decimal(str(round(similarity * 0.78, 4)))
            if similarity >= .55:
                reasons.append("标题相似")
        work = getattr(entity, "work", None)
        if isbn_values & {row.isbn_val for row in work.isbns.all()} if work else False:
            score = Decimal("1.0000")
            reasons.insert(0, "ISBN 精确匹配")
        if subject.resolved_catalog_entity_id == entity.pk:
            score = Decimal("1.0000")
            reasons.insert(0, "此前已人工确认")
        if subject.proposed_entity_type:
            same = entity.entity_type == subject.proposed_entity_type
            score = min(Decimal(1), score + Decimal(".0300")) if same else max(Decimal(0), score - Decimal(".1200"))
            reasons.append("Entity Type 一致" if same else "Entity Type 不同")
        if score >= Decimal(".4000"):
            scored.append((score, entity, reasons))
    scored.sort(key=lambda row: (-row[0], row[1].pk))
    return [
        ResearchCatalogCandidate.objects.create(
            research_subject=subject, catalog_entity=entity, match_score=score, match_reasons=reasons, rank_no=rank,
        )
        for rank, (score, entity, reasons) in enumerate(scored[:10], 1)
    ]


def create_research_subject(values):
    values = dict(values)
    review_item_id = values.pop("review_item_id", None)
    role = values.pop("subject_role", "discovered_member")
    if review_item_id is not None:
        item = ReviewItem.objects.select_for_update().filter(pk=review_item_id).first()
        if not item:
            raise ReviewDomainError("Review item not found")
        if role == "primary" and item.subject_links.filter(subject_role="primary").exists():
            raise ReviewDomainError("A review item can only have one primary subject")
    values["research_fingerprint"] = research_fingerprint(
        values.get("proposed_display_title") or "", values.get("proposed_entity_type"), _isbn_list(values.get("facts_json")),
    )
    subject = ResearchSubject.objects.create(**values)
    if review_item_id is not None:
        ReviewItemSubject.objects.create(review_item_id=review_item_id, research_subject=subject, subject_role=role)
    refresh_catalog_candidates(subject)
    return subject


def stage_parent_structure(item, values):
    """Stage a human-entered parent collection without touching formal Catalog data."""
    if item.status in TERMINAL_ITEM_STATUSES:
        raise ReviewDomainError("Cannot add structure to an already reviewed item")
    child_subject_id = values["child_subject_id"]
    if not item.subject_links.filter(research_subject_id=child_subject_id).exists():
        raise ReviewDomainError("The selected child must belong to this review item")
    entity_type = values["proposed_entity_type"]
    if entity_type not in COLLECTION_ENTITY_TYPES:
        raise ReviewDomainError("A parent structure must be a Reading System, Series, Level, or Set")
    title = _plain_title(values["proposed_display_title"])
    if not title:
        raise ReviewDomainError("A parent structure title is required")

    parent = create_research_subject({
        "proposed_entity_type": entity_type,
        "proposed_display_title": title,
        "proposed_title_zh": values.get("proposed_title_zh") or None,
        "proposed_title_en": values.get("proposed_title_en") or None,
        "research_status": "partial",
        "manual_note": "人工在审核工作台补充的父级结构草稿；最终确认前不写入 Catalog。",
        "review_item_id": item.pk,
        "subject_role": "discovered_parent",
    })
    relation = create_research_relation({
        "parent_subject_id": parent.pk,
        "member_subject_id": child_subject_id,
        "relation_type": "contains",
        "review_status": "proposed",
    })
    return parent, relation


READY_TO_READ_LEVELS = (
    {
        "title": "Ready-to-Read · Ready-to-Go",
        "short_title": "Ready-to-Go",
        "description": "For children beginning to recognize words: about 100 words, sight words, word families, and story guides.",
        "lexile_min": 120,
        "lexile_max": 190,
        "extra_info": "官方级别：Ready-to-Go；Fountas & Pinnell C–F；Lexile AD120L–AD190L。",
    },
    {
        "title": "Ready-to-Read · Pre-Level 1",
        "short_title": "Pre-Level 1",
        "description": "For emerging readers to enjoy shared reading with familiar characters and simple words.",
        "lexile_min": 80,
        "lexile_max": 410,
        "extra_info": "官方级别：Pre-Level 1；Fountas & Pinnell D–I；Lexile BR80L–410L。",
    },
    {
        "title": "Ready-to-Read · Level 1",
        "short_title": "Level 1",
        "description": "For readers starting to read on their own, with high-frequency sight words, simple plots, dialogue, and familiar topics.",
        "lexile_min": 280,
        "lexile_max": 550,
        "extra_info": "官方级别：Level 1；Fountas & Pinnell G–K；Lexile 280L–550L。",
    },
    {
        "title": "Ready-to-Read · Level 2",
        "short_title": "Level 2",
        "description": "For independent readers, with longer sentences, simple chapters, and high-interest vocabulary.",
        "lexile_min": 440,
        "lexile_max": 690,
        "extra_info": "官方级别：Level 2；Fountas & Pinnell I–N；Lexile 440L–690L。",
    },
    {
        "title": "Ready-to-Read · Level 3",
        "short_title": "Level 3",
        "description": "For confident readers, with more complex plots, vocabulary, and sentence structures.",
        "lexile_min": 450,
        "lexile_max": 950,
        "extra_info": "官方级别：Level 3；Fountas & Pinnell L–R；Lexile 450L–950L。",
    },
)


def _research_source(source_url, source_title):
    source = ResearchSource.objects.filter(source_url=source_url).order_by("pk").first()
    if source:
        if not source.source_title:
            source.source_title = source_title
            source.save(update_fields=["source_title"])
        return source
    return ResearchSource.objects.create(
        source_type="publisher_official",
        source_url=source_url,
        source_title=source_title,
        fetched_at=timezone.now(),
    )


def _official_fact(value, source_id, evidence_note=None):
    result = {"value": value, "source_ids": [source_id]}
    if evidence_note:
        result["evidence_note"] = evidence_note
    return result


def _upsert_hierarchy_subject(item, *, entity_type, title, source, facts, aliases=None):
    subject = ResearchSubject.objects.filter(
        item_links__review_item=item,
        proposed_entity_type=entity_type,
        proposed_display_title=title,
    ).order_by("pk").first()
    if subject is None:
        subject = ResearchSubject.objects.create(
            proposed_entity_type=entity_type,
            proposed_display_title=title,
            proposed_title_en=title,
            proposed_aliases=aliases or [],
            research_status="ready",
            research_version="publisher-hierarchy-v1",
            researched_at=timezone.now(),
            manual_note="出版社官网确认的父级体系；最终提交前仍需人工确认新建或关联已有 Catalog。",
        )
        ReviewItemSubject.objects.create(
            review_item=item, research_subject=subject, subject_role="discovered_parent",
        )
    ResearchSubjectSource.objects.get_or_create(research_subject=subject, research_source=source)
    next_facts = dict(subject.facts_json or {})
    next_facts.update({key: _official_fact(value, source.pk) for key, value in facts.items() if value is not None})
    subject.facts_json = next_facts
    subject.research_status = "ready"
    subject.research_version = "publisher-hierarchy-v1"
    subject.researched_at = timezone.now()
    subject.research_fingerprint = research_fingerprint(title, entity_type, [])
    subject.save(update_fields=[
        "facts_json", "research_status", "research_version", "researched_at", "research_fingerprint", "updated_at",
    ])
    refresh_catalog_candidates(subject)
    return subject


def stage_detected_parent_hierarchy(item, actor=None):
    """Research and stage an obvious publisher hierarchy without committing Catalog rows."""
    if item.status in TERMINAL_ITEM_STATUSES:
        raise ReviewDomainError("Cannot research structure for an already reviewed item")
    primary = item.subject_links.filter(subject_role="primary").select_related("research_subject").first()
    if not primary:
        raise ReviewDomainError("Review item must have one primary subject")
    subject = primary.research_subject
    level_value = _plain_title(_fact_value(subject.facts_json, "official_level"))
    series_value = _plain_title(_fact_value(subject.facts_json, "series_name"))
    title_value = _plain_title(subject.proposed_display_title)
    evidence_text = " ".join((level_value, series_value, title_value)).casefold()
    if "ready-to-read" not in evidence_text and "ready to read" not in evidence_text:
        raise ReviewDomainError("当前 Research 没有足够证据自动识别 Ready-to-Read 父级体系")
    if "otto" not in " ".join((series_value, title_value)).casefold():
        raise ReviewDomainError("当前仅支持已由官网识别的 The Adventures of Otto 父级体系")

    program_source = _research_source(
        "https://www.simonandschuster.com/series/Ready-to-Read",
        "Ready-to-Read | Book Series | Simon & Schuster",
    )
    levels_source = _research_source(
        "https://www.simonandschusterpublishing.com/readytoreadnew/levels.html",
        "Ready-to-Read Levels | Simon & Schuster Publishing",
    )
    otto_source = _research_source(
        "https://www.simonandschuster.com/series/The-Adventures-of-Otto",
        "The Adventures of Otto | Book Series | Simon & Schuster",
    )

    program = _upsert_hierarchy_subject(
        item,
        entity_type="reading_system",
        title="Ready-to-Read",
        source=program_source,
        aliases=["Ready to Read"],
        facts={
            "description": "Simon & Schuster's Ready-to-Read program offers five reading levels for children progressing from first word recognition to confident independent reading.",
            "publisher": "Simon Spotlight",
            "language": "en",
            "volume_count": 5,
            "extra_info": "官方分为五级：Ready-to-Go、Pre-Level 1、Level 1、Level 2、Level 3。",
        },
    )
    levels = []
    for level in READY_TO_READ_LEVELS:
        levels.append(_upsert_hierarchy_subject(
            item,
            entity_type="level",
            title=level["title"],
            source=levels_source,
            aliases=[level["short_title"]],
            facts={
                "description": level["description"],
                "language": "en",
                "lexile_min": level["lexile_min"],
                "lexile_max": level["lexile_max"],
                "extra_info": level["extra_info"],
            },
        ))
    otto = _upsert_hierarchy_subject(
        item,
        entity_type="series",
        title="The Adventures of Otto",
        source=otto_source,
        aliases=["Adventures of Otto"],
        facts={
            "description": "An adorable Ready-to-Read series about Otto the robot and his adventures with his family and friends.",
            "author": "David Milgrim",
            "publisher": "Simon Spotlight",
            "language": "en",
        },
    )

    relation_values = [(program, level, position) for position, level in enumerate(levels, 1)]
    relation_values.extend(((program, otto, len(levels) + 1), (otto, subject, 1)))
    relation_ids = []
    for parent, member, position in relation_values:
        relation, _ = ResearchSubjectRelation.objects.update_or_create(
            parent_subject=parent,
            member_subject=member,
            relation_type="contains",
            defaults={
                "position": position,
                "evidence_type": "source_fact",
                "confidence": Decimal("1.000"),
                "review_status": "confirmed",
            },
        )
        relation_ids.append(relation.pk)

    staged_ids = [program.pk, *(level.pk for level in levels), otto.pk]
    _touch_research_items([subject.pk, *staged_ids])
    ReviewActionLog.objects.create(
        review_item=item,
        action="parent_hierarchy_researched",
        actor=actor,
        details_json={"subject_ids": staged_ids, "relation_ids": relation_ids, "provider": "Simon & Schuster"},
    )
    return staged_ids, relation_ids


def _review_status_for_research(status):
    return {"ready": "ready", "partial": "ready", "failed": "failed", "researching": "researching"}.get(status, "pending")


def _touch_research_items(subject_ids):
    item_ids = ReviewItemSubject.objects.filter(research_subject_id__in=subject_ids).values("review_item_id")
    items = ReviewItem.objects.filter(pk__in=item_ids).exclude(status__in=TERMINAL_ITEM_STATUSES)
    batch_ids = set(items.values_list("batch_id", flat=True))
    items.update(lock_version=F("lock_version") + 1, updated_at=timezone.now())
    for item in items:
        primary = item.subject_links.filter(subject_role="primary").select_related("research_subject").first()
        if primary:
            item.status = _review_status_for_research(primary.research_subject.research_status)
            item.save(update_fields=["status", "updated_at"])
    for batch in ReviewBatch.objects.filter(pk__in=batch_ids):
        _recount_batch(batch)


def update_research_subject(subject, values):
    if subject.resolved_catalog_entity_id is not None or subject.item_links.filter(review_item__status__in=TERMINAL_ITEM_STATUSES).exists():
        raise ReviewDomainError("Research cannot modify a resolved subject or an already reviewed item")
    values = dict(values)
    sources = values.pop("sources", None)
    # ``values`` only contains fields that were explicitly supplied by the
    # partial-update serializer.  Apply explicit nulls as well so reviewers
    # can clear optional fields such as the Chinese/English title.
    for key, value in values.items():
        setattr(subject, key, value)
    if sources is not None:
        for source_values in sources:
            source_values = dict(source_values)
            source, _ = ResearchSource.objects.get_or_create(
                source_url=source_values.pop("source_url"),
                source_title=source_values.pop("source_title", None), defaults=source_values,
            )
            ResearchSubjectSource.objects.get_or_create(research_subject=subject, research_source=source)
    subject.research_fingerprint = research_fingerprint(
        subject.proposed_display_title or "", subject.proposed_entity_type, _isbn_list(subject.facts_json),
    )
    subject.full_clean(exclude=["facts_json", "ai_inferences_json", "proposed_aliases"])
    subject.save()
    refresh_catalog_candidates(subject)
    _touch_research_items([subject.pk])
    return subject


def update_review_subject_draft(item, subject, values, actor=None):
    """Merge a human Catalog Draft patch without replacing ``facts_json``.

    The item's lock version protects against a retailer/official capture that
    completed after the browser rendered its draft.  Only explicitly changed
    fact keys are touched; clearing is explicit and is recorded for recovery.
    """
    if item.lock_version != values["expected_version"]:
        raise StaleReviewError("This review changed after it was loaded; reload before saving the draft")
    if item.status in TERMINAL_ITEM_STATUSES or subject.resolved_catalog_entity_id is not None:
        raise ReviewDomainError("Research cannot modify a resolved subject or an already reviewed item")
    if not item.subject_links.filter(research_subject=subject).exists():
        raise ReviewDomainError("Research Subject does not belong to this review item")

    identity_fields = (
        "proposed_entity_type", "proposed_display_title", "proposed_title_zh",
        "proposed_title_en", "proposed_aliases",
    )
    changed_identity = []
    for key in identity_fields:
        if key in values and getattr(subject, key) != values[key]:
            setattr(subject, key, values[key])
            changed_identity.append(key)

    facts = dict(subject.facts_json or {})
    before = {}
    changed_fact_keys = []
    for key, raw_value in dict(values.get("fact_values") or {}).items():
        before[key] = facts.get(key)
        previous = _fact_entry(facts, key) or {}
        next_entry = {**previous, "value": raw_value, "reviewed_by_human": True}
        if facts.get(key) != next_entry:
            facts[key] = next_entry
            changed_fact_keys.append(key)
    cleared_fact_keys = []
    for key in values.get("clear_fact_keys") or []:
        if key in facts:
            before[key] = facts.get(key)
            facts.pop(key, None)
            cleared_fact_keys.append(key)
    subject.facts_json = facts
    subject.research_fingerprint = research_fingerprint(
        subject.proposed_display_title or "", subject.proposed_entity_type, _isbn_list(subject.facts_json),
    )
    subject.full_clean(exclude=["facts_json", "ai_inferences_json", "proposed_aliases"])
    subject.save()
    refresh_catalog_candidates(subject)
    ReviewActionLog.objects.create(
        review_item=item,
        action="catalog_draft_edited",
        actor=actor,
        details_json={
            "subject_id": subject.pk,
            "identity_fields": changed_identity,
            "fact_keys": changed_fact_keys,
            "cleared_fact_keys": cleared_fact_keys,
            "previous_facts": before,
        },
    )
    _touch_research_items([subject.pk])
    return subject


def apply_amazon_capture(subject, capture, actor=None):
    return _apply_product_capture(subject, capture, actor, retailer_code="amazon", retailer_label="Amazon")


def apply_jd_capture(subject, capture, actor=None):
    return _apply_product_capture(subject, capture, actor, retailer_code="jd", retailer_label="京东")


def apply_official_capture(subject, capture, actor=None):
    """Merge a verified official record into review-only research facts."""
    if subject.resolved_catalog_entity_id is not None or subject.item_links.filter(review_item__status__in=TERMINAL_ITEM_STATUSES).exists():
        raise ReviewDomainError("Research cannot modify a resolved subject or an already reviewed item")
    source_url = capture.get("source_url")
    if not source_url:
        raise ReviewDomainError("Official research requires a source URL")
    source_title = capture.get("source_title") or "官方资料"
    source_type = capture.get("source_type") or "publisher_official"
    source, _ = ResearchSource.objects.get_or_create(
        source_url=source_url,
        defaults={"source_type": source_type, "source_title": source_title, "fetched_at": timezone.now()},
    )
    source.source_type = source_type
    source.source_title = source_title
    source.fetched_at = timezone.now()
    source.save(update_fields=["source_type", "source_title", "fetched_at"])
    ResearchSubjectSource.objects.get_or_create(research_subject=subject, research_source=source)

    facts = dict(subject.facts_json or {})
    for key, value in dict(capture.get("facts") or {}).items():
        if value in (None, "", [], {}):
            continue
        if key == "language":
            value = _normalized_language_code(value) or value
        existing = _fact_entry(facts, key)
        if existing is None or existing.get("value") in (None, "", [], {}):
            facts[key] = {"value": value, "source_ids": [source.pk]}
        elif existing.get("value") == value:
            source_ids = list(existing.get("source_ids") or [])
            if source.pk not in source_ids:
                source_ids.append(source.pk)
            facts[key] = {**existing, "source_ids": source_ids}
        elif existing.get("source_ids") == [source.pk]:
            facts[key] = {"value": value, "source_ids": [source.pk]}
        else:
            official_key = key if key.startswith("official_") else f"official_{key}"
            facts[official_key] = {"value": value, "source_ids": [source.pk]}

    subject.facts_json = facts
    type_suggestion = capture.get("entity_type_suggestion")
    if isinstance(type_suggestion, dict) and type_suggestion.get("value") in ALLOWED_ENTITY_TYPES:
        subject.proposed_entity_type = type_suggestion["value"]
        inferences = dict(subject.ai_inferences_json or {})
        inferences["entity_type"] = {
            "value": type_suggestion["value"],
            "confidence": type_suggestion.get("confidence"),
            "reason": type_suggestion.get("reason"),
            "signals": type_suggestion.get("signals") or [],
            "source_id": source.pk,
        }
        subject.ai_inferences_json = inferences
    if subject.research_status not in {"ready", "partial"}:
        subject.research_status = "partial"
    subject.research_version = "official-source-v1"
    subject.researched_at = timezone.now()
    subject.research_fingerprint = research_fingerprint(
        subject.proposed_display_title or "", subject.proposed_entity_type, _isbn_list(subject.facts_json),
    )
    subject.save()
    refresh_catalog_candidates(subject)
    item_ids = list(subject.item_links.values_list("review_item_id", flat=True))
    touched_subject_ids = [subject.pk]

    # An official page may be the first source that exposes the direct
    # collection structure.  Stage that structure immediately as confirmed
    # source evidence, but do not create formal Catalog rows here.
    for direction, rows in (("member", capture.get("members") or []), ("parent", capture.get("parents") or [])):
        if not isinstance(rows, list):
            raise ReviewDomainError(f"Official {direction} structure must be a list")
        for position, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                raise ReviewDomainError("Official structure entries must be objects")
            title = _plain_title(row.get("display_title") or row.get("title"))
            entity_type = row.get("entity_type") or ("book" if direction == "member" else "series")
            if not title or entity_type not in ALLOWED_ENTITY_TYPES:
                raise ReviewDomainError("Official structure requires a title and valid Entity Type")

            relations = subject.member_relations.select_related("member_subject") if direction == "member" else subject.parent_relations.select_related("parent_subject")
            discovered = None
            for relation in relations:
                candidate = relation.member_subject if direction == "member" else relation.parent_subject
                if normalize_search_text(candidate.proposed_display_title) == normalize_search_text(title):
                    discovered = candidate
                    break
            if discovered is None:
                fingerprint = research_fingerprint(title, entity_type, _isbn_list(row.get("facts")))
                reusable = _find_reusable_subject(fingerprint)
                discovered = reusable[0] if reusable else ResearchSubject.objects.create(
                    proposed_entity_type=entity_type,
                    proposed_display_title=title,
                    proposed_title_en=row.get("title_en"),
                    proposed_title_zh=row.get("title_zh"),
                    proposed_aliases=row.get("aliases"),
                    research_fingerprint=fingerprint,
                    research_status="partial",
                    research_version="official-source-v1",
                    researched_at=timezone.now(),
                    manual_note="官网明确给出的直接结构；已作为高可信结构事实进入审核区。",
                )
            for item_id in item_ids:
                ReviewItemSubject.objects.get_or_create(
                    review_item_id=item_id,
                    research_subject=discovered,
                    defaults={"subject_role": "discovered_member" if direction == "member" else "discovered_parent"},
                )

            member_capture = {
                "source_url": row.get("source_url") or source_url,
                "source_title": row.get("source_title") or source_title,
                "source_type": row.get("source_type") or source_type,
                "facts": row.get("facts") or {},
            }
            if discovered.resolved_catalog_entity_id is None:
                apply_official_capture(discovered, member_capture, actor)
                if direction == "member":
                    language_source_id = discovered.source_links.filter(
                        research_source__source_url=member_capture["source_url"],
                    ).values_list("research_source_id", flat=True).first() or source.pk
                    _ensure_subject_language(
                        discovered,
                        parent_subject=subject,
                        source_id=language_source_id,
                    )
            else:
                ResearchSubjectSource.objects.get_or_create(research_subject=discovered, research_source=source)

            if direction == "member":
                parent, member = subject, discovered
            else:
                parent, member = discovered, subject
            relation, _ = ResearchSubjectRelation.objects.get_or_create(
                parent_subject=parent,
                member_subject=member,
                relation_type=row.get("relation_type") or "contains",
                defaults={"position": row.get("position") or position},
            )
            relation.position = row.get("position") or relation.position or position
            relation.evidence_type = "source_fact"
            relation.confidence = Decimal("1.000")
            relation.review_status = "confirmed"
            relation.save(update_fields=["position", "evidence_type", "confidence", "review_status"])
            touched_subject_ids.append(discovered.pk)

    for item_id in item_ids:
        ReviewActionLog.objects.create(
            review_item_id=item_id,
            action="official_source_captured",
            actor=actor,
            details_json={
                "source_url": source_url,
                "source_type": source_type,
                "official_member_count": len(capture.get("members") or []),
                "official_parent_count": len(capture.get("parents") or []),
                "captured_facts": capture.get("facts") or {},
            },
        )
    _touch_research_items(touched_subject_ids)
    return subject


def _lexile_numeric_value(value):
    """Return the sortable number while preserving the original member code."""
    if value in (None, ""):
        return None
    digits = "".join(character for character in str(value) if character.isdigit())
    return int(digits) if digits else None


def aggregate_selected_member_lexiles(parent_subject, member_subject_ids, actor=None):
    """Stage a collection Lexile range derived only from selected direct members."""
    selected_ids = list(dict.fromkeys(member_subject_ids or []))
    if not selected_ids:
        raise ReviewDomainError("至少勾选一个结构成员后才能汇总 Lexile")
    direct_ids = set(parent_subject.member_relations.filter(
        relation_type="contains", member_subject_id__in=selected_ids,
    ).values_list("member_subject_id", flat=True))
    if direct_ids != set(selected_ids):
        raise ReviewDomainError("只能从当前对象的直接结构成员汇总 Lexile")

    members = list(ResearchSubject.objects.filter(pk__in=selected_ids).order_by("pk"))
    values = []
    source_ids = []
    for member in members:
        entry = _fact_entry(member.facts_json, "lexile")
        numeric = _lexile_numeric_value(entry.get("value") if entry else None)
        if numeric is None:
            continue
        values.append(numeric)
        for source_id in entry.get("source_ids") or []:
            if source_id not in source_ids:
                source_ids.append(source_id)
    if not values:
        raise ReviewDomainError("所选结构成员还没有可汇总的 Lexile")

    facts = dict(parent_subject.facts_json or {})
    minimum, maximum = min(values), max(values)
    evidence = {
        "source_ids": source_ids,
        "derived_from_subject_ids": selected_ids,
        "reviewed_by_human": True,
    }
    facts["lexile_min"] = {"value": minimum, **evidence}
    facts["lexile_max"] = {"value": maximum, **evidence}
    facts["lexile_range"] = {"value": f"{minimum}–{maximum}L", **evidence}
    parent_subject.facts_json = facts
    parent_subject.research_status = "partial" if parent_subject.research_status == "pending" else parent_subject.research_status
    parent_subject.save(update_fields=["facts_json", "research_status", "updated_at"])

    for item_id in parent_subject.item_links.values_list("review_item_id", flat=True):
        ReviewActionLog.objects.create(
            review_item_id=item_id,
            action="collection_lexile_aggregated",
            actor=actor,
            details_json={"member_subject_ids": selected_ids, "lexile_min": minimum, "lexile_max": maximum},
        )
    _touch_research_items([parent_subject.pk])
    return parent_subject


def _retailer_material_type(value):
    """Map explicit retailer labels to the controlled Catalog vocabulary."""
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold().replace("_", " ")
    rules = (
        (("picture book", "绘本"), "picture_book"),
        (("graded reader", "分级读物", "分级阅读"), "graded_reader"),
        (("early reader", "初级自主阅读"), "early_reader"),
        (("chapter book", "章节书"), "chapter_book"),
        (("comic", "graphic novel", "漫画"), "comic"),
        (("reference", "百科", "工具书"), "reference"),
        (("poetry", "nursery rhyme", "诗歌", "童谣"), "poetry"),
    )
    return next((code for labels, code in rules if any(label in normalized for label in labels)), None)


def _stage_retailer_classification(subject, retailer_code, retailer_label, category_value):
    code = _retailer_material_type(category_value)
    if not code:
        return
    inferences = dict(subject.ai_inferences_json or {})
    classification = dict(inferences.get("classification") or {})
    proposals = [
        dict(row) for row in classification.get("material_type") or []
        if isinstance(row, dict) and row.get("source") != retailer_code
    ]
    proposals.append({
        "code": code,
        "confidence": 1.0,
        "reason": f"{retailer_label}商品详情明确标注“童书类型：{category_value}”",
        "source": retailer_code,
    })
    classification["material_type"] = proposals
    inferences["classification"] = classification
    subject.ai_inferences_json = inferences


DESCRIPTION_CLASSIFICATION_RULES = {
    "genre": (
        ("nonfiction", ("nonfiction", "non-fiction", "facts", "fact book", "真实故事", "科普")),
        ("fiction", ("fiction", "fictional", "story", "stories", "tale", "故事")),
        ("adventure", ("adventure", "adventures", "journey", "quest", "冒险")),
        ("fantasy", ("fantasy", "magic", "magical", "dragon", "fairy", "wizard", "奇幻", "魔法")),
        ("humor", ("funny", "humorous", "hilarious", "laugh", "幽默", "搞笑")),
        ("mystery", ("mystery", "detective", "clue", "悬疑", "侦探", "谜题")),
        ("biography", ("biography", "memoir", "life of", "传记")),
        ("poetry_rhyme", ("poetry", "poems", "verse", "rhyming text", "诗歌", "韵文")),
    ),
    "theme": (
        ("daily_life", ("daily life", "everyday life", "日常生活")),
        ("family", ("family", "parent", "parents", "mother", "father", "sister", "brother", "家庭", "家人")),
        ("friendship", ("friend", "friends", "friendship", "友情", "朋友")),
        ("school", ("school", "classroom", "teacher", "学校", "课堂", "老师")),
        ("growth", ("growing up", "coming of age", "成长")),
        ("courage", ("courage", "brave", "bravery", "勇气", "勇敢")),
        ("problem_solving", ("solve a problem", "problem-solving", "problem solving", "解决问题")),
        ("independence", ("independent", "independence", "on their own", "独立")),
        ("sharing", ("sharing", "share with", "分享")),
        ("cooperation", ("cooperation", "work together", "teamwork", "合作")),
        ("confidence", ("confidence", "self-confidence", "自信")),
        ("empathy", ("empathy", "understand others", "同理心")),
    ),
    "topic": (
        ("dinosaurs", ("dinosaur", "dinosaurs", "恐龙")),
        ("pets", ("pet", "pets", "宠物")),
        ("insects", ("insect", "insects", "bug", "bugs", "昆虫")),
        ("ocean_animals", ("ocean animals", "sea creatures", "海洋动物")),
        ("animals", ("animal", "animals", "wildlife", "动物")),
        ("plants", ("plant", "plants", "garden", "植物")),
        ("nature", ("nature", "natural world", "自然")),
        ("weather", ("weather", "storm", "rainbow", "天气")),
        ("vehicles", ("vehicle", "vehicles", "car", "train", "truck", "交通工具")),
        ("robots", ("robot", "robots", "机器人")),
        ("machines", ("machine", "machines", "机械")),
        ("body", ("human body", "our bodies", "身体")),
        ("health", ("health", "healthy", "wellness", "健康")),
        ("space", ("outer space", "planet", "planets", "astronaut", "太空")),
        ("earth", ("planet earth", "our earth", "地球")),
        ("science", ("science", "scientific", "experiment", "科学")),
        ("math", ("math", "mathematics", "counting", "数学")),
        ("arts_music", ("music", "musical", "art", "artist", "音乐", "艺术")),
        ("food", ("food", "cooking", "recipe", "食物", "烹饪")),
        ("sports", ("sport", "sports", "soccer", "basketball", "运动")),
        ("holidays", ("holiday", "holidays", "christmas", "节日", "圣诞节")),
    ),
    "reading_form": (
        ("repetitive_pattern", ("repetitive pattern", "predictable pattern", "repeated text", "重复句型", "可预测句型")),
        ("rhyme_rhythm", ("rhyming text", "strong rhythm", "rhythmic text", "押韵", "韵律")),
        ("interactive", ("interactive reading", "lift-the-flap", "touch and feel", "互动阅读", "翻翻书")),
        ("wordless", ("wordless", "without words", "无字书", "极少文字")),
        ("cumulative", ("cumulative tale", "cumulative story", "累积式")),
    ),
}


def _description_term_match(text, term):
    if re.fullmatch(r"[a-z0-9 -]+", term):
        pattern = r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b"
        return bool(re.search(pattern, text))
    return term in text


def summarize_description_classification(subject):
    """Fill empty controlled-taxonomy dimensions from a sourced description.

    This is a review-only fallback. It never overwrites explicit classification
    proposals and never writes Catalog rows; the reviewer can still remove any
    proposed category before the final commit.
    """
    description = _objective_fact_value(subject, "description")
    if not isinstance(description, str) or not description.strip():
        raise ReviewDomainError("没有带来源的简介，无法总结分类")

    normalized = unicodedata.normalize("NFKC", description).casefold()
    inferences = dict(subject.ai_inferences_json or {})
    classification = dict(inferences.get("classification") or {})
    generated_codes = {}

    for category_type, rules in DESCRIPTION_CLASSIFICATION_RULES.items():
        existing = [
            dict(row) for row in classification.get(category_type) or []
            if isinstance(row, dict) and row.get("source") != "description_summary"
        ]
        if existing:
            classification[category_type] = existing
            continue

        inferred = []
        valid_codes = set(CatalogCategory.objects.filter(
            category_type=category_type,
            code__in=[code for code, _terms in rules],
        ).values_list("code", flat=True))
        for code, terms in rules:
            matched = next((term for term in terms if _description_term_match(normalized, term)), None)
            if not matched or code not in valid_codes:
                continue
            inferred.append({
                "code": code,
                "confidence": 0.78,
                "reason": f"简介出现“{matched}”，据此归纳；请审核。",
                "source": "description_summary",
            })
        if inferred:
            classification[category_type] = inferred
            generated_codes[category_type] = [row["code"] for row in inferred]
        else:
            classification.pop(category_type, None)

    inferences["classification"] = classification
    inferences["classification_summary"] = {
        "version": "controlled-description-v1",
        "generated_codes": generated_codes,
        "generated_at": timezone.now().isoformat(),
    }
    subject.ai_inferences_json = inferences
    subject.save(update_fields=["ai_inferences_json", "updated_at"])
    _touch_research_items([subject.pk])
    return subject


def _apply_product_capture(subject, capture, actor=None, *, retailer_code, retailer_label):
    """Merge a human-selected retailer product into review-only research facts."""
    if subject.resolved_catalog_entity_id is not None or subject.item_links.filter(review_item__status__in=TERMINAL_ITEM_STATUSES).exists():
        raise ReviewDomainError("Research cannot modify a resolved subject or an already reviewed item")
    source_title = "Amazon 商品页" if retailer_code == "amazon" else f"{retailer_label}商品页"
    source, _ = ResearchSource.objects.get_or_create(
        source_url=capture["source_url"],
        defaults={
            "source_type": f"{retailer_code}_product",
            "source_title": source_title,
            "fetched_at": timezone.now(),
        },
    )
    changed_source_fields = []
    if source.source_title != source_title:
        source.source_title = source_title
        changed_source_fields.append("source_title")
    if source.source_type != f"{retailer_code}_product":
        source.source_type = f"{retailer_code}_product"
        changed_source_fields.append("source_type")
    source.fetched_at = timezone.now()
    changed_source_fields.append("fetched_at")
    source.save(update_fields=changed_source_fields)
    ResearchSubjectSource.objects.get_or_create(research_subject=subject, research_source=source)

    incoming = dict(capture.get("facts") or {})
    if incoming.get("language"):
        incoming["language"] = _normalized_language_code(incoming["language"]) or incoming["language"]
    # Older trial captures stored retailer-only identifiers and full retailer
    # details block.  They are deliberately removed: the review record keeps
    # useful normalized values, source URL/time, and selectable images only.
    legacy_keys = (
        "amazon_title", "asin", "amazon_product_details", "amazon_downloaded_assets",
        "amazon_detail_images", "jd_title", "sku", "jd_product_details", "jd_downloaded_assets",
        "jd_detail_images", "dimensions",
    )
    for legacy_key in legacy_keys:
        incoming.pop(legacy_key, None)
    facts = dict(subject.facts_json or {})
    for legacy_key in legacy_keys:
        facts.pop(legacy_key, None)

    incoming_images = incoming.pop("product_images", [])
    if incoming_images:
        existing_images = _fact_value(facts, "product_images") or []
        retained = [
            image for image in existing_images
            if isinstance(image, dict) and image.get("source_id") not in {None, source.pk}
        ] if isinstance(existing_images, list) else []
        captured = []
        for image in incoming_images:
            if not isinstance(image, dict) or not image.get("source_url"):
                continue
            captured.append({
                "source_url": image["source_url"],
                "local_path": image.get("local_path"),
                "role": "cover" if image.get("role") == "cover" else "detail",
                "selected": image.get("selected") is not False,
                "source_id": source.pk,
            })
        images = retained + captured
        source_ids = sorted({image["source_id"] for image in images if isinstance(image.get("source_id"), int)})
        facts["product_images"] = {"value": images, "source_ids": source_ids}

    for key, value in incoming.items():
        if value in (None, "", [], {}):
            continue
        existing = _fact_entry(facts, key)
        if existing is None or existing.get("value") in (None, "", [], {}):
            facts[key] = {
                "value": value,
                "source_ids": [source.pk],
            }
        elif existing.get("source_ids") == [source.pk]:
            # A second capture of the same retailer page refreshes its staged
            # value instead of manufacturing a conflict with its older value.
            facts[key] = {"value": value, "source_ids": [source.pk]}
        elif existing.get("value") == value:
            ids = list(existing.get("source_ids") or [])
            if source.pk not in ids:
                ids.append(source.pk)
            facts[key] = {**existing, "source_ids": ids}
        else:
            retailer_key = key if key.startswith(f"{retailer_code}_") else f"{retailer_code}_{key}"
            facts[retailer_key] = {
                "value": value,
                "source_ids": [source.pk],
            }

    _stage_retailer_classification(
        subject,
        retailer_code,
        retailer_label,
        incoming.get("retailer_category"),
    )

    _refresh_selected_image_facts(facts)

    subject.facts_json = facts
    if subject.research_status not in {"ready", "partial"}:
        subject.research_status = "partial"
    subject.research_version = f"{retailer_code}-human-guided-v1"
    subject.researched_at = timezone.now()
    note = f"已采集人工选择的{retailer_label}商品；AR、Lexile、点读笔等仍需其他可靠来源。"
    if note not in (subject.manual_note or ""):
        subject.manual_note = "\n".join(filter(None, [subject.manual_note, note]))
    subject.research_fingerprint = research_fingerprint(
        subject.proposed_display_title or "", subject.proposed_entity_type, _isbn_list(subject.facts_json),
    )
    subject.save()
    refresh_catalog_candidates(subject)
    item_ids = list(subject.item_links.values_list("review_item_id", flat=True))
    touched_subject_ids = [subject.pk]
    member_titles = (incoming.get("included_titles") or []) if subject.proposed_entity_type in COLLECTION_ENTITY_TYPES else []
    for position, member_title in enumerate(member_titles, 1):
        title = _plain_title(member_title)
        if not title:
            continue
        fingerprint = research_fingerprint(title, "book")
        member = None
        for relation in subject.member_relations.select_related("member_subject"):
            if normalize_search_text(relation.member_subject.proposed_display_title) == normalize_search_text(title):
                member = relation.member_subject
                break
        if member is None:
            reusable = _find_reusable_subject(fingerprint)
            member = reusable[0] if reusable else ResearchSubject.objects.create(
                proposed_entity_type="book",
                proposed_display_title=title,
                proposed_title_en=title,
                research_fingerprint=fingerprint,
                research_status="partial",
                research_version=f"{retailer_code}-human-guided-v1",
                researched_at=timezone.now(),
                manual_note=f"{retailer_label}套装页确认其为直接收录成员；单本资料仍待补充。",
            )
        for item_id in item_ids:
            ReviewItemSubject.objects.get_or_create(
                review_item_id=item_id,
                research_subject=member,
                defaults={"subject_role": "discovered_member"},
            )
        ResearchSubjectSource.objects.get_or_create(research_subject=member, research_source=source)
        if member.resolved_catalog_entity_id is None:
            member_facts = dict(member.facts_json or {})
            member_facts.setdefault("included_in", {
                "value": subject.proposed_display_title,
                "source_ids": [source.pk],
                "evidence_note": f"{retailer_label}套装标题明确列出",
            })
            member.facts_json = member_facts
            if member.research_status not in {"ready", "partial"}:
                member.research_status = "partial"
            member.researched_at = timezone.now()
            member.save()
            _ensure_subject_language(member, parent_subject=subject, source_id=source.pk)
            refresh_catalog_candidates(member)
        ResearchSubjectRelation.objects.get_or_create(
            parent_subject=subject,
            member_subject=member,
            relation_type="contains",
            defaults={
                "position": position,
                "evidence_type": "source_fact",
                "confidence": Decimal("0.990"),
            },
        )
        touched_subject_ids.append(member.pk)
    for item_id in item_ids:
        ReviewActionLog.objects.create(
            review_item_id=item_id,
            action=f"{retailer_code}_product_captured",
            actor=actor,
            details_json={
                "source_url": capture.get("source_url"),
                "image_count": len(capture.get("downloaded_assets") or []),
            },
        )
    _touch_research_items(touched_subject_ids)
    return subject


def _refresh_selected_image_facts(facts):
    entry = _fact_entry(facts, "product_images")
    images = entry.get("value") if entry else []
    if not isinstance(images, list):
        return
    available = [image for image in images if isinstance(image, dict) and image.get("source_url")]
    if not available:
        for key in ("cover", "cover_local_path", "detail_images"):
            facts.pop(key, None)
        return
    cover = next((image for image in available if image.get("role") == "cover"), available[0])
    cover_source_id = cover.get("source_id")
    if isinstance(cover_source_id, int):
        facts["cover"] = {"value": cover["source_url"], "source_ids": [cover_source_id]}
        if cover.get("local_path"):
            facts["cover_local_path"] = {"value": cover["local_path"], "source_ids": [cover_source_id]}
        else:
            facts.pop("cover_local_path", None)
    selected = [image for image in available if image.get("selected") is not False]
    details = [
        {"source_url": image["source_url"], "local_path": image.get("local_path")}
        for image in selected
    ]
    if details:
        detail_source_ids = sorted({
            image.get("source_id") for image in selected if isinstance(image.get("source_id"), int)
        })
        facts["detail_images"] = {"value": details, "source_ids": detail_source_ids}
    else:
        facts.pop("detail_images", None)


def update_product_image_selection(subject, selected_source_urls, cover_source_url=None):
    """Update staged detail-image choices and the independent cover choice."""
    if subject.resolved_catalog_entity_id is not None or subject.item_links.filter(review_item__status__in=TERMINAL_ITEM_STATUSES).exists():
        raise ReviewDomainError("Research cannot modify a resolved subject or an already reviewed item")
    selected_urls = {str(value) for value in selected_source_urls}
    facts = dict(subject.facts_json or {})
    entry = _fact_entry(facts, "product_images")
    images = entry.get("value") if entry else None
    if not isinstance(images, list):
        raise ReviewDomainError("当前审核对象没有可选择的商品图片")
    known_urls = {image.get("source_url") for image in images if isinstance(image, dict)}
    if not selected_urls.issubset(known_urls):
        raise ReviewDomainError("图片选择包含未知地址")
    current_cover = next((
        image.get("source_url") for image in images
        if isinstance(image, dict) and image.get("role") == "cover" and image.get("source_url")
    ), None)
    chosen_cover = str(cover_source_url or current_cover or next(iter(known_urls), ""))
    if chosen_cover not in known_urls:
        raise ReviewDomainError("封面选择包含未知地址")
    for image in images:
        if isinstance(image, dict):
            image["selected"] = image.get("source_url") in selected_urls
            image["role"] = "cover" if image.get("source_url") == chosen_cover else "detail"
    entry["value"] = images
    facts["product_images"] = entry
    _refresh_selected_image_facts(facts)
    subject.facts_json = facts
    subject.save(update_fields=["facts_json"])
    _touch_research_items([subject.pk])
    return subject


def _relation_reaches(start_id, target_id):
    pending, seen = [start_id], set()
    while pending:
        current = pending.pop()
        if current == target_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        pending.extend(ResearchSubjectRelation.objects.filter(
            parent_subject_id=current, relation_type="contains",
        ).exclude(review_status="rejected").values_list("member_subject_id", flat=True))
    return False


def create_research_relation(values):
    parent_id, member_id = values["parent_subject_id"], values["member_subject_id"]
    if parent_id == member_id:
        raise ReviewDomainError("A research subject cannot contain itself")
    if ResearchSubject.objects.filter(pk__in=[parent_id, member_id]).count() != 2:
        raise ReviewDomainError("Research subject not found")
    relation_type = values.get("relation_type", "contains")
    if relation_type == "contains" and _relation_reaches(member_id, parent_id):
        raise ReviewDomainError("Research relation would create a cycle")
    defaults = {key: value for key, value in values.items() if key not in {"parent_subject_id", "member_subject_id", "relation_type"}}
    relation, _ = ResearchSubjectRelation.objects.update_or_create(
        parent_subject_id=parent_id, member_subject_id=member_id, relation_type=relation_type, defaults=defaults,
    )
    _touch_research_items([parent_id, member_id])
    return relation


def delete_research_relation(relation):
    subject_ids = [relation.parent_subject_id, relation.member_subject_id]
    if ReviewItemSubject.objects.filter(
        research_subject_id__in=subject_ids,
        review_item__status__in=TERMINAL_ITEM_STATUSES,
    ).exists():
        raise ReviewDomainError("Cannot change structure for an already reviewed item")
    relation.delete()
    _touch_research_items(subject_ids)


def _primary_subject(item_id):
    links = list(ReviewItemSubject.objects.filter(review_item_id=item_id, subject_role="primary"))
    if len(links) != 1:
        raise ReviewDomainError("Review item must have exactly one primary subject")
    return ResearchSubject.objects.select_for_update().get(pk=links[0].research_subject_id)


def _json_value(value):
    return float(value) if isinstance(value, Decimal) else value


def _record_conflict(item, subject, entity, field, existing, proposed):
    ReviewDataConflict.objects.get_or_create(
        review_item=item, research_subject=subject, catalog_entity=entity, field_path=field, status="pending",
        defaults={"existing_value": _json_value(existing), "proposed_value": _json_value(proposed)},
    )


def _set_or_conflict(item, subject, entity, target, attribute, field_path, proposed):
    if proposed is None:
        return
    # Field conversion rejects malformed research facts instead of corrupting official data.
    field = target._meta.get_field(attribute)
    try:
        proposed = field.clean(proposed, target)
    except (ValidationError, TypeError, ValueError, OverflowError) as error:
        raise ReviewDomainError(f"Invalid sourced value for {field_path}") from error
    existing = getattr(target, attribute)
    if existing is None:
        setattr(target, attribute, proposed)
    elif existing != proposed:
        _record_conflict(item, subject, entity, field_path, existing, proposed)


def _apply_objective_facts(item, subject, entity):
    _set_or_conflict(item, subject, entity, entity, "description", "catalog.description", _objective_fact_value(subject, "description"))
    _set_or_conflict(item, subject, entity, entity, "cover_url", "catalog.cover_url", _objective_fact_value(subject, "cover"))
    _set_or_conflict(item, subject, entity, entity, "cover_local_path", "catalog.cover_local_path", _objective_fact_value(subject, "cover_local_path"))
    _set_or_conflict(item, subject, entity, entity, "extra_info", "catalog.extra_info", _objective_fact_value(subject, "extra_info"))
    _set_or_conflict(item, subject, entity, entity, "detail_images", "catalog.detail_images", _objective_fact_value(subject, "detail_images"))
    work = getattr(entity, "work", None)
    if work:
        for key, attr in {
            "author": "author_text", "illustrator": "illustrator_text", "language": "language_code", "page_count": "page_count",
            "word_count": "word_count", "headwords": "headword_count", "ar": "ar_level", "lexile": "lexile_code",
        }.items():
            _set_or_conflict(item, subject, entity, work, attr, f"work.{attr}", _objective_fact_value(subject, key))
        work.save()
    collection = getattr(entity, "collection", None)
    if collection:
        for key, attr in {
            "volume_count": "volume_count", "lexile_min": "lexile_min", "lexile_max": "lexile_max",
        }.items():
            _set_or_conflict(item, subject, entity, collection, attr, f"collection.{attr}", _objective_fact_value(subject, key))
        collection.save()
    entity.save()
    pen_names = _objective_fact_value(subject, "reading_pens") or []
    if isinstance(pen_names, str):
        pen_names = [pen_names]
    if not isinstance(pen_names, list):
        raise ReviewDomainError("reading_pens must be a string or a list")
    for name in pen_names:
        normalized = normalize_search_text(str(name))
        if normalized:
            pen, _ = ReadingPenModel.objects.get_or_create(normalized_name=normalized, defaults={"name": str(name)})
            CatalogEntityReadingPen.objects.get_or_create(catalog_entity=entity, reading_pen_model=pen)
    isbn_values = _objective_fact_value(subject, "isbns") or _objective_fact_value(subject, "isbn") or []
    if isinstance(isbn_values, str):
        isbn_values = [isbn_values]
    if not isinstance(isbn_values, list):
        raise ReviewDomainError("isbns must be a string or a list")
    for isbn in isbn_values:
        if not work:
            _record_conflict(item, subject, entity, "work.isbn", None, isbn)
        else:
            try:
                with transaction.atomic():
                    add_isbn(entity.pk, str(isbn))
            except CatalogDomainError:
                _record_conflict(item, subject, entity, "work.isbn", None, isbn)


def _create_entity_from_subject(item, subject, bookshelf_visible=False):
    title = _plain_title(subject.proposed_display_title)
    if subject.proposed_entity_type not in ALLOWED_ENTITY_TYPES or not title:
        raise ReviewDomainError("A title and valid Entity Type are required before creating Catalog data")
    entity = create_catalog_entity(
        entity_type=subject.proposed_entity_type, display_title=title,
        title_zh=subject.proposed_title_zh, title_en=subject.proposed_title_en, aliases=subject.proposed_aliases,
        bookshelf_visible=bookshelf_visible,
    )
    _apply_objective_facts(item, subject, entity)
    _bind_subject(subject, entity, "created")
    return entity


def _bind_subject(subject, entity, status):
    if subject.resolved_catalog_entity_id is not None and subject.resolved_catalog_entity_id != entity.pk:
        raise ReviewDomainError("This research subject has a different prior human resolution")
    subject.resolution_status = status
    subject.resolved_catalog_entity = entity
    subject.save()


def _resolve_structure(item, selected_ids, decisions, bookshelf_visibility):
    primary_id = item.subject_links.get(subject_role="primary").research_subject_id
    relation_rows = list(ResearchSubjectRelation.objects.filter(
        parent_subject_id__in=selected_ids, member_subject_id__in=selected_ids, relation_type="contains",
    ).exclude(review_status="rejected"))
    adjacent = {subject_id: set() for subject_id in selected_ids}
    for relation in relation_rows:
        adjacent[relation.parent_subject_id].add(relation.member_subject_id)
        adjacent[relation.member_subject_id].add(relation.parent_subject_id)
    reachable, pending = set(), [primary_id]
    while pending:
        current = pending.pop()
        if current in reachable:
            continue
        reachable.add(current)
        pending.extend(adjacent.get(current, ()))
    if reachable != selected_ids:
        raise ReviewDomainError("Selected structure must form a connected direct-relation chain to the primary subject")

    subjects = list(ResearchSubject.objects.select_for_update().filter(pk__in=selected_ids).order_by("pk"))
    refreshed_candidates = {
        subject.pk: refresh_catalog_candidates(subject)
        for subject in subjects if not subject.resolved_catalog_entity_id
    }
    resolved = {}
    for subject in subjects:
        if subject.resolved_catalog_entity_id:
            entity = CatalogEntity.objects.select_for_update().get(pk=subject.resolved_catalog_entity_id)
        else:
            choice = decisions.get(subject.pk)
            if not choice:
                raise ReviewDomainError("Choose match_existing or create_new for each selected structure subject")
            if choice["decision"] == "match_existing":
                if not any(row.catalog_entity_id == choice.get("catalog_entity_id") for row in refreshed_candidates[subject.pk]):
                    raise StaleReviewError("Catalog candidate changed; review the structure node again")
                entity = CatalogEntity.objects.select_for_update().filter(pk=choice.get("catalog_entity_id")).first()
                if not entity or entity.entity_type != subject.proposed_entity_type:
                    raise ReviewDomainError("Selected structure Catalog entity is missing or has a different type")
                _bind_subject(subject, entity, "matched")
                _apply_objective_facts(item, subject, entity)
            elif choice["decision"] == "create_new":
                strong = [row for row in refreshed_candidates[subject.pk] if row.match_score >= STRONG_MATCH_SCORE]
                if strong:
                    raise DuplicateCandidateError(strong)
                entity = _create_entity_from_subject(item, subject, bookshelf_visibility.get(subject.pk, False))
            else:
                raise ReviewDomainError("Invalid structure decision")
        entity.bookshelf_visible = bookshelf_visibility.get(subject.pk, False)
        entity.save(update_fields=["bookshelf_visible"])
        resolved[subject.pk] = entity
    if set(resolved) != selected_ids:
        raise ReviewDomainError("One or more structure subjects do not exist")
    for relation in relation_rows:
        add_collection_item(resolved[relation.parent_subject_id].pk, resolved[relation.member_subject_id].pk, relation.position)
        relation.review_status = "accepted"
        relation.save()
    return resolved


def _commit_source_relation(item, entity):
    if item.committed_reading_list_item_id is not None:
        return
    batch = item.batch
    if batch.source_type != "reading_list" or batch.target_reading_list_id is None:
        return
    if not ReadingList.objects.filter(pk=batch.target_reading_list_id).exists():
        raise ReviewDomainError("Target reading list no longer exists")
    extracted = effective_review_payload(item)
    fields = {
        key: extracted.get(key) for key in (
            "recommended_age_min_months", "recommended_age_max_months", "is_strong_recommendation",
            "recommendation_emphasis_text", "comment", "note",
        )
    }
    raw_extracted = item.raw_payload.get("extracted", {}) if isinstance(item.raw_payload, dict) else {}
    raw_other = raw_extracted.get("other_info", {}) if isinstance(raw_extracted, dict) else {}
    source_stage = raw_other.get("stage", {}) if isinstance(raw_other, dict) else {}
    fields["stage_label"] = str(source_stage.get("title"))[:255] if isinstance(source_stage, dict) and source_stage.get("title") else None
    fields["note"] = clean_source_note(fields["note"])
    for key in ("source_ar_text", "source_lexile_text", "source_level_text"):
        fields[key] = str(extracted[key]) if extracted.get(key) is not None else None
    relation = ReadingListItem(
        reading_list_id=batch.target_reading_list_id, catalog_entity=entity, position=item.position, **fields,
    )
    relation.full_clean()
    relation.save()
    item.committed_reading_list_item = relation


def _recount_batch(batch):
    batch.resolved_items = batch.items.filter(status__in=TERMINAL_ITEM_STATUSES).count()
    batch.status = ("completed" if batch.total_items and batch.resolved_items >= batch.total_items
                    else "reviewing" if batch.resolved_items
                    else "researching" if batch.items.filter(status__in=["pending", "researching"]).exists()
                    else "ready")
    batch.save()


def resolve_review_item(item_id, values):
    item = ReviewItem.objects.select_for_update().filter(pk=item_id).first()
    if not item:
        raise ReviewDomainError("Review item not found")
    decision = values["decision"]
    if decision not in {"ignore", "match_existing", "create_new"}:
        raise ReviewDomainError("Invalid review decision")
    if item.status in TERMINAL_ITEM_STATUSES:
        if item.decision == decision and (decision != "match_existing" or item.resolved_catalog_entity_id == values.get("catalog_entity_id")):
            return item
        raise StaleReviewError("Review item is already resolved")
    if item.lock_version != values["expected_version"]:
        raise StaleReviewError("Review item changed; reload before submitting")
    # Lock the batch too so concurrent decisions cannot overwrite its completion count.
    batch = ReviewBatch.objects.select_for_update().get(pk=item.batch_id)
    subject = _primary_subject(item.pk)
    bookshelf_rows = values.get("bookshelf_visibility") or []
    bookshelf_visibility = {row["subject_id"]: row["visible"] for row in bookshelf_rows}
    if len(bookshelf_visibility) != len(bookshelf_rows):
        raise ReviewDomainError("Bookshelf visibility subjects must be unique")
    entity = None
    if decision == "ignore":
        item.status = "ignored"
    elif decision == "match_existing":
        refreshed_primary = refresh_catalog_candidates(subject)
        if not any(row.catalog_entity_id == values.get("catalog_entity_id") for row in refreshed_primary):
            raise StaleReviewError("Catalog candidate changed; review the recommended entity again")
        entity = CatalogEntity.objects.select_for_update().filter(pk=values.get("catalog_entity_id")).first()
        if not entity:
            raise ReviewDomainError("Catalog entity not found")
        _bind_subject(subject, entity, "matched")
        _apply_objective_facts(item, subject, entity)
        entity.bookshelf_visible = bookshelf_visibility.get(subject.pk, False)
        entity.save(update_fields=["bookshelf_visible"])
        item.status = "resolved"
    else:
        strong = [row for row in refresh_catalog_candidates(subject) if row.match_score >= STRONG_MATCH_SCORE]
        if strong:
            raise DuplicateCandidateError(strong)
        entity = _create_entity_from_subject(item, subject, bookshelf_visibility.get(subject.pk, False))
        item.status = "resolved"
    if entity is not None:
        item.resolved_catalog_entity = entity
        selected = set(values.get("include_structure_subject_ids") or []) | {subject.pk}
        allowed = set(item.subject_links.values_list("research_subject_id", flat=True))
        if not selected.issubset(allowed):
            raise ReviewDomainError("Structure subjects must belong to this review item")
        if not set(bookshelf_visibility).issubset(selected):
            raise ReviewDomainError("Bookshelf visibility can only target selected structure subjects")
        if len(selected) > 1:
            choices = values.get("structure_decisions") or []
            decisions = {row["subject_id"]: row for row in choices}
            if len(decisions) != len(choices) or not set(decisions).issubset(selected):
                raise ReviewDomainError("Structure decisions must be unique and selected")
            _resolve_structure(item, selected, decisions, bookshelf_visibility)
        entity.bookshelf_visible = bookshelf_visibility.get(subject.pk, False)
        entity.save(update_fields=["bookshelf_visible"])
        assign_entity_categories(entity, values.get("category_decisions") or [])
        _commit_source_relation(item, entity)
    item.decision = decision
    item.manual_note = values.get("manual_note")
    item.lock_version += 1
    item.resolved_at = timezone.now()
    item.save()
    ReviewActionLog.objects.create(
        review_item=item, action=decision, actor=values.get("actor"),
        details_json={
            "catalog_entity_id": entity.pk if entity else None,
            "included_structure_subject_ids": values.get("include_structure_subject_ids") or [],
            "bookshelf_visible_subject_ids": sorted(subject_id for subject_id, visible in bookshelf_visibility.items() if visible),
        },
    )
    _recount_batch(batch)
    return item


def resolve_conflict(conflict, status, actor, note):
    if conflict.status != "pending":
        raise StaleReviewError("Conflict is already resolved")
    if status not in {"keep_existing", "use_proposed", "ignored"}:
        raise ReviewDomainError("Invalid conflict resolution")
    if status == "use_proposed":
        entity = CatalogEntity.objects.select_for_update().get(pk=conflict.catalog_entity_id)
        work = getattr(entity, "work", None)
        targets = {
            "catalog.description": (entity, "description"), "catalog.cover_url": (entity, "cover_url"),
            "catalog.cover_local_path": (entity, "cover_local_path"), "catalog.extra_info": (entity, "extra_info"),
            "catalog.detail_images": (entity, "detail_images"),
        }
        targets.update({f"work.{attr}": (work, attr) for attr in (
            "author_text", "illustrator_text", "language_code", "page_count", "word_count", "headword_count", "ar_level", "lexile_code",
        )})
        target = targets.get(conflict.field_path)
        if not target or target[0] is None:
            raise ReviewDomainError("This conflict field cannot be applied automatically")
        value = target[0]._meta.get_field(target[1]).clean(conflict.proposed_value, target[0])
        setattr(target[0], target[1], value)
        target[0].save()
    conflict.status = status
    conflict.manual_note = note
    conflict.save()
    if conflict.review_item_id:
        ReviewActionLog.objects.create(
            review_item_id=conflict.review_item_id, action=f"conflict_{status}", actor=actor,
            details_json={"conflict_id": conflict.pk, "field_path": conflict.field_path},
        )
    return conflict


def update_review_item_source_copy(item, values, actor=None):
    """Update the reviewable recommendation copy without mutating raw provenance."""
    if item.status in TERMINAL_ITEM_STATUSES:
        raise ReviewDomainError("Cannot edit source copy on an already reviewed item")
    if item.lock_version != values["expected_version"]:
        raise StaleReviewError("Review item changed; reload before editing source copy")

    extracted = dict(item.extracted_payload) if isinstance(item.extracted_payload, dict) else {}
    changed_fields = []
    for field in ("is_strong_recommendation", "recommendation_emphasis_text", "comment", "note"):
        if field not in values:
            continue
        raw_value = values[field]
        value = bool(raw_value) if field == "is_strong_recommendation" else None if raw_value is None else str(raw_value).strip() or None
        if field == "note":
            value = clean_source_note(value)
        if extracted.get(field) != value:
            extracted[field] = value
            changed_fields.append(field)

    if extracted.get("is_strong_recommendation") is False and extracted.get("recommendation_emphasis_text") is not None:
        extracted["recommendation_emphasis_text"] = None
        if "recommendation_emphasis_text" not in changed_fields:
            changed_fields.append("recommendation_emphasis_text")

    if not changed_fields:
        return item
    item.extracted_payload = extracted
    item.lock_version += 1
    item.save(update_fields=["extracted_payload", "lock_version", "updated_at"])
    ReviewActionLog.objects.create(
        review_item=item,
        action="source_copy_edited",
        actor=actor,
        details_json={"fields": changed_fields},
    )
    return item


def effective_review_payload(item):
    """Return source copy with recommendation emphasis derived for legacy rows.

    Recommendation strength was added after some review batches had already
    been imported.  Those rows still contain explicit wording such as
    ``强烈推荐`` in their original note, but their stored review payload has no
    strength keys.  Derive only when both keys are absent: once a reviewer has
    explicitly set or cleared either field, that human decision wins.
    """
    extracted = dict(item.extracted_payload) if isinstance(item.extracted_payload, dict) else {}
    if "is_strong_recommendation" in extracted:
        return extracted

    if extracted.get("recommendation_strength") is not None:
        strong, text = _recommendation_emphasis_fields(extracted, {})
        extracted["is_strong_recommendation"] = strong
        extracted["recommendation_emphasis_text"] = text
        return extracted

    raw_payload = item.raw_payload if isinstance(item.raw_payload, dict) else {}
    raw_extracted = dict(raw_payload.get("extracted") or {})
    for field in ("comment", "note"):
        if field in extracted:
            raw_extracted[field] = extracted[field]
    other = raw_extracted.get("other_info") if isinstance(raw_extracted.get("other_info"), dict) else {}
    raw_import = other.get("raw_import") if isinstance(other.get("raw_import"), dict) else {}
    strong, text = _recommendation_emphasis_fields(raw_extracted, raw_import)
    extracted["is_strong_recommendation"] = strong
    extracted["recommendation_emphasis_text"] = text
    return extracted


def subject_to_dict(subject):
    result = {key: getattr(subject, key) for key in (
        "id", "proposed_entity_type", "proposed_display_title", "proposed_title_zh", "proposed_title_en",
        "proposed_aliases", "facts_json", "ai_inferences_json", "research_status", "resolution_status",
        "resolved_catalog_entity_id", "manual_note", "research_version", "researched_at",
    )}
    result["sources"] = [
        {key: getattr(link.research_source, key) for key in ("id", "source_type", "source_url", "source_title", "fetched_at")}
        for link in subject.source_links.select_related("research_source").order_by("pk")
    ]
    result["resolved_bookshelf_visible"] = (
        subject.resolved_catalog_entity.bookshelf_visible if subject.resolved_catalog_entity_id else None
    )
    result["candidates"] = [
        {"id": row.pk, "catalog_entity_id": row.catalog_entity_id, "display_title": row.catalog_entity.display_title,
          "entity_type": row.catalog_entity.entity_type, "match_score": float(row.match_score) if row.match_score is not None else None,
          "match_reasons": row.match_reasons, "rank_no": row.rank_no,
          "bookshelf_visible": row.catalog_entity.bookshelf_visible}
        for row in subject.candidates.select_related("catalog_entity").order_by("rank_no")
    ]
    result["relations"] = [
        {"id": row.pk, "parent_subject_id": row.parent_subject_id, "parent_title": row.parent_subject.proposed_display_title,
         "member_subject_id": row.member_subject_id, "member_title": row.member_subject.proposed_display_title,
         "relation_type": row.relation_type, "position": row.position, "evidence_type": row.evidence_type,
         "confidence": float(row.confidence) if row.confidence is not None else None, "review_status": row.review_status}
        for row in ResearchSubjectRelation.objects.filter(Q(parent_subject=subject) | Q(member_subject=subject))
            .select_related("parent_subject", "member_subject").order_by("pk")
    ]
    pending_conflicts = subject.reviewdataconflict_set.filter(status="pending").order_by("pk")
    result["pending_conflicts"] = [
        {
            "id": conflict.pk,
            "field_path": conflict.field_path,
            "existing_value": conflict.existing_value,
            "proposed_value": conflict.proposed_value,
        }
        for conflict in pending_conflicts
    ]
    result["pending_conflict_count"] = len(result["pending_conflicts"])
    return result


def review_item_to_dict(item):
    result = {key: getattr(item, key) for key in (
        "id", "batch_id", "source_item_key", "position", "raw_payload", "extracted_payload", "status", "decision",
        "resolved_catalog_entity_id", "committed_reading_list_item_id", "manual_note", "lock_version", "resolved_at",
    )}
    result["extracted_payload"] = effective_review_payload(item)
    result["subjects"] = []
    for link in sorted(item.subject_links.select_related("research_subject"), key=lambda row: (row.subject_role != "primary", row.research_subject_id)):
        result["subjects"].append({**subject_to_dict(link.research_subject), "subject_role": link.subject_role})
    return result
