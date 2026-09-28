#!/usr/bin/env python3
"""Read the legacy database and emit database-independent source JSON assets.

The script only executes SELECT statements against the configured database. It does
not create, update, or delete database rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import text


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import engine  # noqa: E402


SCHEMA_VERSION = "1.0"
SOURCE_DATA = PROJECT_ROOT / "source_data"
READING_LIST_DIR = SOURCE_DATA / "reading_lists"
PURCHASE_DIR = SOURCE_DATA / "purchases"
UNRESOLVED_DIR = SOURCE_DATA / "unresolved"
REPORT_DIR = SOURCE_DATA / "reports"


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


def parse_json(value: Any) -> Any:
    if value is None or isinstance(value, (dict, list, int, float, bool)):
        return json_value(value)
    try:
        return json.loads(str(value))
    except (json.JSONDecodeError, TypeError):
        return str(value)


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_value(data), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_rows(connection: Any, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(text(sql), params or {}).mappings()]


def safe_filename(value: str, limit: int = 82) -> str:
    value = "".join(character for character in value if unicodedata.category(character) != "So")
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", "-", value.strip())
    value = re.sub(r"[-_]{2,}", "-", value).strip(" .-_")
    return (value[:limit].rstrip(" .-_") or "untitled")


def light_title(raw_title: str) -> str:
    """Only normalize whitespace; never merge, split, or reinterpret a title."""
    return re.sub(r"\s+", " ", raw_title).strip()


def first_nonempty(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def creator_assets(connection: Any) -> dict[int, dict[str, Any]]:
    creator_rows = select_rows(
        connection,
        """
        SELECT rs.id AS source_id, rs.name, rs.source_type, rs.platform,
               rs.profile_url, rs.notes, rs.created_at AS source_created_at,
               p.display_name, p.avatar_url, p.photo_credit_url, p.short_bio,
               p.positioning, p.methodology_summary, p.route_summary,
               p.suitable_for, p.cautions, p.source_note,
               p.created_at AS profile_created_at, p.updated_at AS profile_updated_at
        FROM recommendation_sources rs
        LEFT JOIN recommendation_source_profiles p ON p.source_id = rs.id
        ORDER BY rs.id
        """,
    )
    publications = defaultdict(list)
    for row in select_rows(connection, "SELECT * FROM recommendation_source_publications ORDER BY source_id, id"):
        source_id = row.pop("source_id")
        legacy_id = row.pop("id")
        row["legacy_reference"] = {"publication_id": legacy_id}
        publications[source_id].append(json_value(row))

    knowledge = defaultdict(list)
    for row in select_rows(connection, "SELECT * FROM recommendation_source_knowledge ORDER BY source_id, id"):
        source_id = row.pop("source_id")
        legacy_id = row.pop("id")
        row["legacy_reference"] = {
            "knowledge_id": legacy_id,
            "source_document_id": row.pop("source_document_id"),
            "source_page_id": row.pop("source_page_id"),
        }
        knowledge[source_id].append(json_value(row))

    page_rows = select_rows(connection, "SELECT * FROM recommendation_source_pages ORDER BY document_id, page_order, id")
    pages = defaultdict(list)
    for row in page_rows:
        document_id = row.pop("document_id")
        legacy_id = row.pop("id")
        row["legacy_reference"] = {"source_page_id": legacy_id}
        pages[document_id].append(json_value(row))

    documents = defaultdict(list)
    for row in select_rows(connection, "SELECT * FROM recommendation_source_documents ORDER BY source_id, id"):
        source_id = row.pop("source_id")
        document_id = row.pop("id")
        row["pages"] = pages[document_id]
        row["legacy_reference"] = {"source_document_id": document_id}
        documents[source_id].append(json_value(row))

    result: dict[int, dict[str, Any]] = {}
    for row in creator_rows:
        source_id = row.pop("source_id")
        introduction = row.pop("short_bio")
        name = row.pop("name")
        result[source_id] = {
            "name": name,
            "introduction": introduction,
            "other_info": {
                "display_name": row.pop("display_name"),
                "source_type": row.pop("source_type"),
                "platform": row.pop("platform"),
                "profile_url": row.pop("profile_url"),
                "notes": row.pop("notes"),
                "source_created_at": json_value(row.pop("source_created_at")),
                "profile": json_value(row),
                "publications": publications[source_id],
                "knowledge": knowledge[source_id],
                "source_documents": documents[source_id],
                "legacy_reference": {"recommendation_source_id": source_id},
            },
        }
    return result


def evidence_metric(evidence: list[dict[str, Any]], kind: str, scalar: Any = None) -> Any:
    matches = [row for row in evidence if row["evidence_type"] == kind]
    if not matches and scalar is None:
        return None
    first = matches[0] if matches else {}
    value = first_nonempty(first.get("value_number"), scalar)
    return {
        "raw": first.get("value_text"),
        "value": json_value(value),
        "min": json_value(first.get("min_value")),
        "max": json_value(first.get("max_value")),
    }


def recommended_age(item: dict[str, Any], evidence: list[dict[str, Any]]) -> Any:
    age_evidence = next((row for row in evidence if row["evidence_type"] == "recommended_age"), None)
    minimum = item.get("recommended_age_min")
    maximum = item.get("recommended_age_max")
    raw = first_nonempty(age_evidence.get("value_text") if age_evidence else None, item.get("raw_age_range"))
    if raw is None and minimum is None and maximum is None:
        return None
    return {"raw": raw, "min": json_value(minimum), "max": json_value(maximum), "unit": "years"}


def note_from_annotations(annotations: list[dict[str, Any]]) -> Any:
    reminders = [row["value_text"] for row in annotations if row["annotation_type"] == "reminder"]
    if not reminders:
        return None
    return reminders[0] if len(reminders) == 1 else reminders


def reading_list_assets(connection: Any, creators: dict[int, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[Path]]:
    list_rows = select_rows(connection, "SELECT * FROM reading_lists ORDER BY id")
    stage_rows = select_rows(connection, "SELECT * FROM recommendation_stages ORDER BY recommendation_list_id, stage_order, id")
    import_rows = select_rows(connection, "SELECT * FROM import_sources WHERE reading_list_id IS NOT NULL ORDER BY reading_list_id, id")
    item_rows = select_rows(
        connection,
        """
        SELECT i.*,
               s.stage_order, s.title AS stage_title, s.description AS stage_description,
               s.recommended_age_min_months AS stage_age_min_months,
               s.recommended_age_max_months AS stage_age_max_months,
               s.level_system AS stage_level_system,
               s.level_value_min AS stage_level_min,
               s.level_value_max AS stage_level_max,
               r.raw_title AS import_raw_title, r.raw_author AS import_raw_author,
               r.raw_isbn, r.raw_age_range, r.raw_ar, r.raw_lexile, r.raw_level,
               r.raw_metadata, r.position AS import_position,
               r.resolve_status, r.resolve_confidence, r.resolve_source,
               r.manual_note, r.id AS legacy_raw_import_item_id,
               ce.entity_type AS legacy_entity_type,
               ce.display_title AS legacy_entity_title,
               sp.page_order AS source_page_order, sp.file_path AS source_page_path,
               sp.file_name AS source_page_name, sp.mime_type AS source_page_mime_type,
               sp.checksum AS source_page_checksum, sp.width AS source_page_width,
               sp.height AS source_page_height
        FROM reading_list_items i
        LEFT JOIN recommendation_stages s ON s.id = i.stage_id
        LEFT JOIN raw_import_items r ON r.id = i.raw_import_item_id
        LEFT JOIN catalog_entities ce ON ce.id = i.catalog_entity_id
        LEFT JOIN recommendation_source_pages sp ON sp.id = i.source_page_id
        ORDER BY i.recommendation_list_id,
                 CASE WHEN s.stage_order IS NULL THEN 2147483647 ELSE s.stage_order END,
                 CASE WHEN i.position IS NULL THEN 2147483647 ELSE i.position END,
                 i.id
        """,
    )
    evidence_by_item = defaultdict(list)
    for row in select_rows(connection, "SELECT * FROM recommendation_evidence ORDER BY recommendation_item_id, id"):
        item_id = row.pop("recommendation_item_id")
        legacy_id = row.pop("id")
        row["legacy_reference"] = {"evidence_id": legacy_id}
        evidence_by_item[item_id].append(json_value(row))
    annotations_by_item = defaultdict(list)
    for row in select_rows(connection, "SELECT * FROM recommendation_item_annotations ORDER BY recommendation_item_id, id"):
        item_id = row.pop("recommendation_item_id")
        legacy_id = row.pop("id")
        row["legacy_reference"] = {"annotation_id": legacy_id}
        annotations_by_item[item_id].append(json_value(row))

    stages_by_list = defaultdict(list)
    stage_lookup: dict[int, dict[str, Any]] = {}
    for row in stage_rows:
        list_id = row.pop("recommendation_list_id")
        stage_id = row.pop("id")
        stage = json_value({**row, "legacy_reference": {"stage_id": stage_id}})
        stages_by_list[list_id].append(stage)
        stage_lookup[stage_id] = stage
    imports_by_list = defaultdict(list)
    for row in import_rows:
        list_id = row.pop("reading_list_id")
        source_id = row.pop("id")
        row["legacy_reference"] = {"import_source_id": source_id}
        imports_by_list[list_id].append(json_value(row))
    items_by_list = defaultdict(list)
    for row in item_rows:
        items_by_list[row["recommendation_list_id"]].append(row)

    manifests: list[dict[str, Any]] = []
    paths: list[Path] = []
    for list_row in list_rows:
        list_id = list_row.pop("id")
        source_id = list_row.pop("source_id")
        creator = creators[source_id]
        output_items = []
        for sequence, item in enumerate(items_by_list[list_id], start=1):
            item_id = item["id"]
            evidence = evidence_by_item[item_id]
            annotations = annotations_by_item[item_id]
            level = first_nonempty(
                item.get("raw_level"),
                next((row.get("value_text") for row in evidence if row["evidence_type"] in {"level", "ort_level"}), None),
            )
            entity_type = item.get("legacy_entity_type")
            possible_type = entity_type if entity_type in {"book", "series", "level", "set"} else (
                item["item_type"] if item["item_type"] in {"book", "series", "level", "set"} else "unknown"
            )
            confidence = float(item.get("resolve_confidence") or 0)
            analysis_notes = ["旧库解析结果仅用于预审核，不是未来 Catalog 的正式事实。"] if possible_type != "unknown" else []
            source_page = None
            if item.get("source_page_id") is not None:
                source_page = {
                    "page_order": item.get("source_page_order"),
                    "file_path": item.get("source_page_path"),
                    "file_name": item.get("source_page_name"),
                    "mime_type": item.get("source_page_mime_type"),
                    "checksum": item.get("source_page_checksum"),
                    "width": item.get("source_page_width"),
                    "height": item.get("source_page_height"),
                    "region": parse_json(item.get("source_region_json")),
                }
            raw_metadata = parse_json(item.get("raw_metadata"))
            output_items.append(
                {
                    "sequence": sequence,
                    "position": item.get("position"),
                    "raw_title": item["raw_title"],
                    "extracted": {
                        "title": light_title(item["raw_title"]),
                        "recommended_age": recommended_age(item, evidence),
                        "ar": evidence_metric(evidence, "ar", item.get("recommended_ar")),
                        "lexile": evidence_metric(evidence, "lexile", item.get("recommended_lexile")),
                        "level": level,
                        "comment": item.get("comment"),
                        "note": note_from_annotations(annotations),
                        "other_info": {
                            "raw_author": item.get("raw_author"),
                            "raw_text": item.get("raw_text"),
                            "legacy_item_type": item.get("item_type"),
                            "stage": stage_lookup.get(item.get("stage_id")),
                            "source_evidence": source_page,
                            "evidence": evidence,
                            "annotations": annotations,
                            "raw_import": {
                                "raw_title": item.get("import_raw_title"),
                                "raw_author": item.get("import_raw_author"),
                                "raw_isbn": item.get("raw_isbn"),
                                "raw_age_range": item.get("raw_age_range"),
                                "raw_ar": item.get("raw_ar"),
                                "raw_lexile": item.get("raw_lexile"),
                                "raw_level": item.get("raw_level"),
                                "raw_metadata": raw_metadata,
                                "position": item.get("import_position"),
                                "manual_note": item.get("manual_note"),
                            },
                            "legacy_reference": {
                                "reading_list_item_id": item_id,
                                "raw_import_item_id": item.get("legacy_raw_import_item_id"),
                                "stage_id": item.get("stage_id"),
                                "source_page_id": item.get("source_page_id"),
                            },
                        },
                    },
                    "analysis": {
                        "possible_entity_type": possible_type,
                        "confidence": confidence,
                        "notes": analysis_notes,
                        "other_info": {
                            "legacy_resolve_status": item.get("resolve_status"),
                            "legacy_resolve_source": item.get("resolve_source"),
                            "legacy_catalog_title": item.get("legacy_entity_title"),
                            "legacy_catalog_type": item.get("legacy_entity_type"),
                        },
                    },
                }
            )

        document = {
            "schema_version": SCHEMA_VERSION,
            "document_type": "reading_list",
            "creator": creator,
            "list": {
                "title": list_row.pop("title"),
                "description": list_row.pop("description"),
                "other_info": {
                    **json_value(list_row),
                    "stages": stages_by_list[list_id],
                    "import_sources": imports_by_list[list_id],
                    "position_scope": "stage",
                    "legacy_reference": {"reading_list_id": list_id},
                },
            },
            "items": output_items,
        }
        filename = f"{safe_filename(creator['name'])}__{list_id:03d}__{safe_filename(document['list']['title'])}.json"
        path = READING_LIST_DIR / filename
        dump_json(path, document)
        paths.append(path)
        manifests.append(
            {
                "path": path.relative_to(SOURCE_DATA).as_posix(),
                "creator": creator["name"],
                "title": document["list"]["title"],
                "item_count": len(output_items),
                "sha256": sha256(path),
            }
        )
    return manifests, paths


def bill_records(path: Path) -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        return {}, {"available": False, "path": path.relative_to(PROJECT_ROOT).as_posix()}
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = {int(row["row_number"]): row for row in payload.get("rows", [])}
    return records, {
        "available": True,
        "path": path.relative_to(PROJECT_ROOT).as_posix(),
        "summary": payload.get("summary", {}),
    }


def source_rows_from_description(description: str | None) -> list[int]:
    match = re.search(r"账单行：([^。]+)。", description or "")
    return [int(value) for value in re.findall(r"\d+", match.group(1))] if match else []


def integer_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def amount_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(re.sub(r"[^0-9.\-]", "", str(value)))
    except InvalidOperation:
        return None


def purchase_assets(connection: Any, bill_path: Path) -> tuple[dict[str, Any], Path, set[int]]:
    bill_by_row, bill_info = bill_records(bill_path)
    applied_path = PROJECT_ROOT / "tmp" / "bookshelf_import_applied.json"
    applied_by_work: dict[int, list[int]] = {}
    if applied_path.exists():
        applied = json.loads(applied_path.read_text(encoding="utf-8"))
        applied_by_work = {int(row["work_id"]): [int(value) for value in row.get("source_rows", [])] for row in applied.get("items", [])}

    shelves = select_rows(
        connection,
        """
        SELECT id, title, collection_type, description
        FROM collections
        WHERE collection_type = 'personal_shelf' OR title = '我的书架'
        ORDER BY CASE WHEN collection_type = 'personal_shelf' THEN 0 ELSE 1 END, id
        LIMIT 1
        """,
    )
    if not shelves:
        raise RuntimeError("Personal shelf not found; refusing to infer purchases from all works")
    shelf = shelves[0]
    purchase_rows = select_rows(
        connection,
        """
        SELECT ci.id AS shelf_item_id, ci.position, ci.quantity, ci.work_id,
               ci.content_variant_id, ci.edition_id,
               w.canonical_title, w.original_title, w.original_language,
               w.description AS work_description, w.page_count, w.word_count,
               w.ar, w.lexile, w.catalog_entity_id,
               ce.entity_type AS legacy_entity_type, ce.display_title AS legacy_entity_title,
               cv.language AS variant_language, cv.variant_type, cv.title AS variant_title,
               e.isbn10, e.isbn13, e.publisher, e.publish_date, e.format,
               e.pages AS edition_pages, e.word_count AS edition_word_count,
               e.cover_url,
               (SELECT GROUP_CONCAT(a.name ORDER BY wa.position SEPARATOR ' | ')
                  FROM work_authors wa JOIN authors a ON a.id = wa.author_id
                 WHERE wa.work_id = w.id) AS authors
        FROM collection_items ci
        JOIN works w ON w.id = ci.work_id
        LEFT JOIN catalog_entities ce ON ce.id = w.catalog_entity_id
        LEFT JOIN content_variants cv ON cv.id = ci.content_variant_id
        LEFT JOIN editions e ON e.id = ci.edition_id
        WHERE ci.collection_id = :shelf_id
        ORDER BY CASE WHEN ci.position IS NULL THEN 2147483647 ELSE ci.position END, ci.id
        """,
        {"shelf_id": shelf["id"]},
    )
    identifiers = defaultdict(list)
    for row in select_rows(connection, "SELECT catalog_entity_id, identifier_type, identifier_value FROM catalog_identifiers ORDER BY catalog_entity_id, id"):
        identifiers[row.pop("catalog_entity_id")].append(json_value(row))

    output_items = []
    used_bill_rows: set[int] = set()
    for row in purchase_rows:
        work_id = int(row["work_id"])
        source_rows = applied_by_work.get(work_id) or source_rows_from_description(row.get("work_description"))
        records = []
        total_paid = Decimal("0")
        has_paid = False
        for source_row in source_rows:
            source = bill_by_row.get(source_row)
            if not source:
                continue
            used_bill_rows.add(source_row)
            paid = amount_or_none(source.get("paid_amount"))
            if paid is not None:
                total_paid += paid
                has_paid = True
            records.append(
                {
                    "source_row": source_row,
                    "raw_title": source.get("title") or row["canonical_title"],
                    "quantity": integer_or_none(source.get("quantity")),
                    "paid_amount": source.get("paid_amount"),
                    "platform": source.get("platform") or None,
                    "purchased_at": source.get("purchase_date") or None,
                    "stated_age": source.get("age") or None,
                    "screenshot": source.get("screenshot") or None,
                    "raw_order_text": source.get("order_info") or None,
                    "other_info": {
                        "language": source.get("language") or None,
                        "item_type": source.get("item_type") or None,
                    },
                }
            )
        output_items.append(
            {
                "position": row.get("position"),
                "raw_title": row["canonical_title"],
                "extracted": {"title": light_title(row["canonical_title"])},
                "purchase": {
                    "quantity": int(row["quantity"]),
                    "currency": "CNY" if records else None,
                    "total_paid_amount": float(total_paid) if has_paid else None,
                    "records": records,
                },
                "analysis": {
                    "possible_entity_type": "unknown",
                    "confidence": 0.0,
                    "notes": ["旧 works 的 book 类型不提升为未来 Catalog 事实；需在预审核中判断 book/series/level/set。"],
                },
                "other_info": {
                    "original_title": row.get("original_title"),
                    "language": first_nonempty(row.get("original_language"), row.get("variant_language")),
                    "authors": row["authors"].split(" | ") if row.get("authors") else [],
                    "page_count": row.get("page_count"),
                    "word_count": row.get("word_count"),
                    "ar": json_value(row.get("ar")),
                    "lexile": row.get("lexile"),
                    "edition": {
                        "isbn10": row.get("isbn10"),
                        "isbn13": row.get("isbn13"),
                        "publisher": row.get("publisher"),
                        "publish_date": json_value(row.get("publish_date")),
                        "format": row.get("format"),
                        "pages": row.get("edition_pages"),
                        "word_count": row.get("edition_word_count"),
                        "cover_url": row.get("cover_url"),
                    },
                    "identifiers": identifiers[row["catalog_entity_id"]],
                    "legacy_work_description": row.get("work_description"),
                    "source_rows": source_rows,
                    "legacy_catalog": {
                        "title": row.get("legacy_entity_title"),
                        "type": row.get("legacy_entity_type"),
                    },
                    "legacy_reference": {
                        "personal_shelf_id": shelf["id"],
                        "shelf_item_id": row["shelf_item_id"],
                        "work_id": work_id,
                        "content_variant_id": row.get("content_variant_id"),
                        "edition_id": row.get("edition_id"),
                    },
                },
            }
        )

    document = {
        "schema_version": SCHEMA_VERSION,
        "document_type": "purchases",
        "source": {
            "name": shelf["title"],
            "type": shelf["collection_type"],
            "description": shelf.get("description"),
            "other_info": {
                "source_workbook": "👪恩恩的账簿 副本.xlsx",
                "database_item_count": len(output_items),
                "database_total_quantity": sum(item["purchase"]["quantity"] for item in output_items),
                "bill_source": bill_info,
                "legacy_reference": {"personal_shelf_id": shelf["id"]},
            },
        },
        "items": output_items,
    }
    path = PURCHASE_DIR / "personal-shelf__bill-purchases.json"
    dump_json(path, document)
    manifest = {
        "path": path.relative_to(SOURCE_DATA).as_posix(),
        "item_count": len(output_items),
        "purchase_record_count": sum(len(item["purchase"]["records"]) for item in output_items),
        "total_quantity": sum(item["purchase"]["quantity"] for item in output_items),
        "sha256": sha256(path),
    }
    return manifest, path, used_bill_rows


def unresolved_assets(connection: Any) -> tuple[dict[str, Any], Path]:
    rows = select_rows(
        connection,
        """
        SELECT w.*, ce.entity_type AS legacy_entity_type,
               ce.display_title AS legacy_entity_title,
               ce.original_title AS legacy_entity_original_title,
               ce.cover_url AS legacy_cover_url,
               ce.cover_local_path AS legacy_cover_local_path
        FROM works w
        JOIN catalog_entities ce ON ce.id = w.catalog_entity_id
        LEFT JOIN collection_items shelf_item
               ON shelf_item.work_id = w.id
              AND shelf_item.collection_id = (
                    SELECT id FROM collections
                    WHERE collection_type = 'personal_shelf' OR title = '我的书架'
                    ORDER BY CASE WHEN collection_type = 'personal_shelf' THEN 0 ELSE 1 END, id
                    LIMIT 1
              )
        WHERE shelf_item.id IS NULL
          AND NOT EXISTS (
                SELECT 1 FROM reading_list_items i
                WHERE i.work_id = w.id OR i.catalog_entity_id = w.catalog_entity_id
          )
        ORDER BY w.id
        """,
    )
    items = []
    for row in rows:
        work_id = row.pop("id")
        catalog_entity_id = row.pop("catalog_entity_id")
        items.append(
            {
                "raw_title": row.get("canonical_title"),
                "reason": "Not linked to any reading-list item and not a member of the personal shelf.",
                "legacy_data": json_value(row),
                "legacy_reference": {"work_id": work_id, "catalog_entity_id": catalog_entity_id},
            }
        )
    document = {
        "schema_version": SCHEMA_VERSION,
        "document_type": "unresolved_legacy_works",
        "items": items,
    }
    path = UNRESOLVED_DIR / "legacy-works-unresolved.json"
    dump_json(path, document)
    return {
        "path": path.relative_to(SOURCE_DATA).as_posix(),
        "work_count": len(items),
        "sha256": sha256(path),
    }, path


def write_preliminary_report(manifest: dict[str, Any]) -> None:
    counts = manifest["reading_lists"]
    purchases = manifest["purchases"]
    unresolved = manifest["unresolved"]
    report = f"""# 旧数据提取报告

生成时间：{manifest['generated_at']}

## 提取结果

- 达人数：{counts['creator_count']}
- 达人书单数：{counts['list_count']}
- 书单条目数：{counts['item_count']}
- 已购书条目数：{purchases['item_count']}
- 原始购买记录数：{purchases['purchase_record_count']}
- 已购数量合计：{purchases['total_quantity']}
- unresolved works：{unresolved['work_count']}

## 校验状态

提取已完成。请运行 `backend/.venv/Scripts/python.exe scripts/validate_source_data.py` 生成正式 Schema 与覆盖校验结果；验证脚本会更新本报告。
"""
    path = REPORT_DIR / "extraction-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


def run(bill_path: Path) -> dict[str, Any]:
    for directory in (READING_LIST_DIR, PURCHASE_DIR, UNRESOLVED_DIR, REPORT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    with engine.connect() as connection:
        creators = creator_assets(connection)
        reading_lists, _ = reading_list_assets(connection, creators)
        purchases, _, used_bill_rows = purchase_assets(connection, bill_path)
        unresolved, _ = unresolved_assets(connection)
        table_counts = {
            table: connection.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar_one()
            for table in (
                "recommendation_sources",
                "recommendation_source_profiles",
                "recommendation_source_publications",
                "recommendation_source_knowledge",
                "recommendation_source_documents",
                "recommendation_source_pages",
                "reading_lists",
                "recommendation_stages",
                "reading_list_items",
                "recommendation_evidence",
                "recommendation_item_annotations",
                "raw_import_items",
                "works",
                "collections",
                "collection_items",
            )
        }

    creator_names = sorted({entry["creator"] for entry in reading_lists})
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "document_type": "source_data_manifest",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": {
            "kind": "legacy_database_read_only_export",
            "alembic_version": "20260902_0006",
            "table_counts": table_counts,
            "bill_rows_matched": len(used_bill_rows),
        },
        "reading_lists": {
            "creator_count": len(creator_names),
            "creators": creator_names,
            "list_count": len(reading_lists),
            "item_count": sum(entry["item_count"] for entry in reading_lists),
            "files": reading_lists,
        },
        "purchases": {
            "item_count": purchases["item_count"],
            "purchase_record_count": purchases["purchase_record_count"],
            "total_quantity": purchases["total_quantity"],
            "files": [purchases],
        },
        "unresolved": {
            "work_count": unresolved["work_count"],
            "files": [unresolved],
        },
    }
    dump_json(SOURCE_DATA / "manifest.json", manifest)
    write_preliminary_report(manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bill-json",
        type=Path,
        default=PROJECT_ROOT / "tmp" / "bill_books.json",
        help="Optional original bill extraction used to retain dates, amounts, and raw OCR text.",
    )
    args = parser.parse_args()
    manifest = run(args.bill_json.resolve())
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
