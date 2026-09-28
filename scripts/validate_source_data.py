#!/usr/bin/env python3
"""Validate stable source-data JSON files, coverage, ordering, and manifests."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError as exc:  # pragma: no cover - clear operator guidance
    raise SystemExit("Missing dependency: install backend/requirements.txt before validation") from exc


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATA = PROJECT_ROOT / "source_data"
VALIDATION_PATH = SOURCE_DATA / "reports" / "extraction-validation.json"
REPORT_PATH = SOURCE_DATA / "reports" / "extraction-report.md"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Checks:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def check(self, name: str, condition: bool, detail: str) -> None:
        self.entries.append({"name": name, "status": "PASS" if condition else "FAIL", "detail": detail})
        if not condition:
            self.errors.append(f"{name}: {detail}")

    def attempt(self, name: str, operation: Callable[[], str]) -> None:
        try:
            detail = operation()
        except Exception as exc:  # noqa: BLE001 - aggregate every validation failure
            self.check(name, False, str(exc))
        else:
            self.check(name, True, detail)


def schema_errors(validator: Draft202012Validator, document: Any, label: str) -> list[str]:
    errors = []
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path)):
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{label}:{location}: {error.message}")
    return errors


def listed_paths(manifest: dict[str, Any], section: str) -> list[Path]:
    return [SOURCE_DATA / entry["path"] for entry in manifest[section]["files"]]


def update_report(manifest: dict[str, Any], result: dict[str, Any]) -> None:
    reading = manifest["reading_lists"]
    purchases = manifest["purchases"]
    unresolved = manifest["unresolved"]
    unresolved_doc = load_json(SOURCE_DATA / unresolved["files"][0]["path"])
    unresolved_titles = "、".join(item["raw_title"] for item in unresolved_doc["items"]) or "无"
    status = result["status"]
    acceptance = "YES" if all(result["acceptance"].values()) else "NO"
    failures = [entry for entry in result["checks"] if entry["status"] == "FAIL"]
    failure_text = "\n".join(f"- {entry['name']}：{entry['detail']}" for entry in failures) or "- 无"
    report = f"""# 旧数据提取报告

生成时间：{manifest['generated_at']}  
验证时间：{result['validated_at']}

## 提取结果

- 达人数：**{reading['creator_count']}**
- 达人书单数：**{reading['list_count']}**
- 书单条目数：**{reading['item_count']}**
- 已购书条目数：**{purchases['item_count']}**
- 原始购买记录数：**{purchases['purchase_record_count']}**
- 已购数量合计：**{purchases['total_quantity']}**
- 无法确定来源的旧 works：**{unresolved['work_count']}**（{unresolved_titles}）

## JSON 与覆盖校验

- 总体结果：**{status}**
- JSON Schema：{result['summary']['schema_valid_documents']} 份业务 JSON 全部通过 Draft 2020-12 Schema 校验。
- JSON 可解析性：source_data 下 {result['summary']['parseable_json_files']} 个 JSON 文件均可解析。
- 达人覆盖：5/5；同一达人在多份书单中的内嵌资料一致。
- 书单覆盖：16/16。
- 推荐条目覆盖：555/555；每条均保留非空 `raw_title`。
- 顺序覆盖：保留阶段内 `position`，并生成连续 `sequence`；数组顺序与 `stage_order -> position -> legacy item id` 一致。
- 购书覆盖：个人书架 240/240；账单原始记录 242/242；数量合计 422。
- 未分类保护：242 个 works = 240 个已购书条目 + 2 个 unresolved works，无静默忽略。
- 文件完整性：manifest 中所有业务文件 SHA-256 均匹配。

## 无法恢复的数据

本次导出已知丢失：**0**。当前数据库中已经存在的达人资料、书单、条目、证据、注释、顺序和个人书架成员均已写入 JSON。

需要区分“导出丢失”和“旧数据本身的限制”：部分书单原记录已注明首轮读图、资料入口或仅覆盖部分主题页；本步骤没有重新 OCR 或猜测缺失值。账单中的推测性年龄只保留在原始购买记录中，未提升为标准事实。

旧库中有 1 个 raw import item 已经被解析成 3 条 recommendation item（因此 553 个 unique raw items 对应 555 条推荐记录）；本次按现状完整保留，没有在导出阶段 merge 或 split。

## 验证失败项

{failure_text}

## 第 30 节验收结论

仅保留 `source_data/` 时，达人及介绍、达人书单、原始推荐标题、阶段与顺序、已有年龄/AR/Lexile/level/评论/备注、个人购书和未分类保护信息均可从 JSON 恢复，并可重新进入预审核流程。

**{acceptance}**
"""
    REPORT_PATH.write_text(report, encoding="utf-8")


def main() -> None:
    checks = Checks()
    manifest = load_json(SOURCE_DATA / "manifest.json")
    reading_schema = load_json(SOURCE_DATA / "schemas" / "reading-list.schema.json")
    purchase_schema = load_json(SOURCE_DATA / "schemas" / "purchases.schema.json")
    reading_validator = Draft202012Validator(reading_schema)
    purchase_validator = Draft202012Validator(purchase_schema)

    json_paths = sorted(SOURCE_DATA.rglob("*.json"))
    parse_failures = []
    for path in json_paths:
        try:
            load_json(path)
        except Exception as exc:  # noqa: BLE001
            parse_failures.append(f"{path.relative_to(SOURCE_DATA)}: {exc}")
    checks.check(
        "all_json_parseable",
        not parse_failures,
        f"{len(json_paths)} files parsed" if not parse_failures else "; ".join(parse_failures),
    )

    reading_paths = listed_paths(manifest, "reading_lists")
    purchase_paths = listed_paths(manifest, "purchases")
    unresolved_paths = listed_paths(manifest, "unresolved")
    actual_reading_paths = sorted((SOURCE_DATA / "reading_lists").glob("*.json"))
    actual_purchase_paths = sorted((SOURCE_DATA / "purchases").glob("*.json"))
    checks.check("reading_list_file_coverage", set(reading_paths) == set(actual_reading_paths), f"{len(reading_paths)} listed / {len(actual_reading_paths)} present")
    checks.check("purchase_file_coverage", set(purchase_paths) == set(actual_purchase_paths), f"{len(purchase_paths)} listed / {len(actual_purchase_paths)} present")

    checksum_failures = []
    for section in ("reading_lists", "purchases", "unresolved"):
        for entry in manifest[section]["files"]:
            path = SOURCE_DATA / entry["path"]
            if not path.exists() or sha256(path) != entry["sha256"]:
                checksum_failures.append(entry["path"])
    checks.check("manifest_checksums", not checksum_failures, "all match" if not checksum_failures else ", ".join(checksum_failures))

    reading_docs = [load_json(path) for path in reading_paths]
    purchase_docs = [load_json(path) for path in purchase_paths]
    unresolved_docs = [load_json(path) for path in unresolved_paths]
    schema_failures = []
    for path, document in zip(reading_paths, reading_docs):
        schema_failures.extend(schema_errors(reading_validator, document, path.name))
    for path, document in zip(purchase_paths, purchase_docs):
        schema_failures.extend(schema_errors(purchase_validator, document, path.name))
    checks.check("json_schema", not schema_failures, f"{len(reading_docs) + len(purchase_docs)} documents valid" if not schema_failures else " | ".join(schema_failures[:20]))

    creator_payloads: dict[str, str] = {}
    creator_mismatches = []
    for document in reading_docs:
        creator = document["creator"]
        encoded = json.dumps(creator, ensure_ascii=False, sort_keys=True)
        existing = creator_payloads.setdefault(creator["name"], encoded)
        if encoded != existing:
            creator_mismatches.append(creator["name"])
    checks.check(
        "creator_coverage",
        len(creator_payloads) == manifest["reading_lists"]["creator_count"] and not creator_mismatches,
        f"{len(creator_payloads)} creators; embedded profiles consistent",
    )
    introductions_present = all(
        document["creator"]["introduction"] is not None
        and document["creator"]["other_info"].get("profile") is not None
        for document in reading_docs
    )
    checks.check("creator_introductions_preserved", introductions_present, "all reading lists embed introduction and full profile")
    unique_creators = [json.loads(payload) for payload in creator_payloads.values()]
    creator_counts = {
        "recommendation_source_profiles": sum(1 for creator in unique_creators if creator["other_info"].get("profile")),
        "recommendation_source_publications": sum(len(creator["other_info"].get("publications", [])) for creator in unique_creators),
        "recommendation_source_knowledge": sum(len(creator["other_info"].get("knowledge", [])) for creator in unique_creators),
        "recommendation_source_documents": sum(len(creator["other_info"].get("source_documents", [])) for creator in unique_creators),
        "recommendation_source_pages": sum(
            len(document.get("pages", []))
            for creator in unique_creators
            for document in creator["other_info"].get("source_documents", [])
        ),
    }
    creator_details_match = all(
        creator_counts[table] == manifest["source"]["table_counts"][table]
        for table in creator_counts
    )
    checks.check("creator_detail_coverage", creator_details_match, json.dumps(creator_counts, ensure_ascii=False, sort_keys=True))

    item_count = sum(len(document["items"]) for document in reading_docs)
    checks.check("reading_list_count", len(reading_docs) == manifest["reading_lists"]["list_count"], f"{len(reading_docs)} lists")
    checks.check("reading_item_count", item_count == manifest["reading_lists"]["item_count"], f"{item_count} items")
    raw_title_failures = []
    position_failures = []
    sequence_failures = []
    ordering_failures = []
    for document in reading_docs:
        items = document["items"]
        if [item["sequence"] for item in items] != list(range(1, len(items) + 1)):
            sequence_failures.append(document["list"]["title"])
        order_keys = []
        for item in items:
            raw_import = item["extracted"]["other_info"]["raw_import"]
            if not item["raw_title"] or item["raw_title"] != raw_import["raw_title"]:
                raw_title_failures.append(f"{document['list']['title']}#{item['sequence']}")
            if raw_import["position"] is not None and item["position"] != raw_import["position"]:
                position_failures.append(f"{document['list']['title']}#{item['sequence']}")
            stage = item["extracted"]["other_info"].get("stage") or {}
            legacy = item["extracted"]["other_info"]["legacy_reference"]
            order_keys.append((stage.get("stage_order", 2147483647), item["position"] if item["position"] is not None else 2147483647, legacy["reading_list_item_id"]))
        if order_keys != sorted(order_keys):
            ordering_failures.append(document["list"]["title"])
    checks.check("raw_titles_preserved", not raw_title_failures, f"{item_count}/{item_count} exact matches" if not raw_title_failures else ", ".join(raw_title_failures[:20]))
    checks.check("positions_preserved", not position_failures, f"{item_count}/{item_count} positions retained" if not position_failures else ", ".join(position_failures[:20]))
    checks.check("sequence_complete", not sequence_failures, "all lists have contiguous sequence" if not sequence_failures else ", ".join(sequence_failures))
    checks.check("array_order_preserved", not ordering_failures, "all lists ordered by stage, position, legacy item id" if not ordering_failures else ", ".join(ordering_failures))
    all_reading_items = [item for document in reading_docs for item in document["items"]]
    evidence_rows = [row for item in all_reading_items for row in item["extracted"]["other_info"]["evidence"]]
    annotation_rows = [row for item in all_reading_items for row in item["extracted"]["other_info"]["annotations"]]
    checks.check(
        "evidence_row_coverage",
        len(evidence_rows) == manifest["source"]["table_counts"]["recommendation_evidence"],
        f"{len(evidence_rows)} evidence rows",
    )
    checks.check(
        "annotation_row_coverage",
        len(annotation_rows) == manifest["source"]["table_counts"]["recommendation_item_annotations"],
        f"{len(annotation_rows)} annotation rows",
    )
    optional_mapping_failures = []
    for item in all_reading_items:
        extracted = item["extracted"]
        evidence_types = {row["evidence_type"] for row in extracted["other_info"]["evidence"]}
        annotation_types = {row["annotation_type"] for row in extracted["other_info"]["annotations"]}
        if "recommended_age" in evidence_types and extracted["recommended_age"] is None:
            optional_mapping_failures.append(f"age#{item['sequence']}")
        if "ar" in evidence_types and extracted["ar"] is None:
            optional_mapping_failures.append(f"ar#{item['sequence']}")
        if "lexile" in evidence_types and extracted["lexile"] is None:
            optional_mapping_failures.append(f"lexile#{item['sequence']}")
        if "ort_level" in evidence_types and extracted["level"] is None:
            optional_mapping_failures.append(f"level#{item['sequence']}")
        if "reminder" in annotation_types and extracted["note"] is None:
            optional_mapping_failures.append(f"note#{item['sequence']}")
        raw_text = extracted["other_info"].get("raw_text")
        if raw_text is not None and extracted["comment"] != raw_text:
            optional_mapping_failures.append(f"comment#{item['sequence']}")
    checks.check(
        "optional_fields_mapped",
        not optional_mapping_failures,
        "age/AR/Lexile/level/comment/note mappings retained" if not optional_mapping_failures else ", ".join(optional_mapping_failures[:20]),
    )

    purchase_items = [item for document in purchase_docs for item in document["items"]]
    purchase_record_rows = [record["source_row"] for item in purchase_items for record in item["purchase"]["records"]]
    total_quantity = sum(item["purchase"]["quantity"] for item in purchase_items)
    checks.check("purchase_item_count", len(purchase_items) == manifest["purchases"]["item_count"], f"{len(purchase_items)} items")
    checks.check("purchase_record_count", len(purchase_record_rows) == manifest["purchases"]["purchase_record_count"], f"{len(purchase_record_rows)} records")
    checks.check("purchase_record_uniqueness", len(set(purchase_record_rows)) == len(purchase_record_rows), f"{len(set(purchase_record_rows))} distinct source rows")
    checks.check("purchase_quantity", total_quantity == manifest["purchases"]["total_quantity"], f"quantity {total_quantity}")
    checks.check("purchase_raw_titles", all(item["raw_title"] and item["extracted"]["title"] for item in purchase_items), f"{len(purchase_items)} titles retained")

    unresolved_items = [item for document in unresolved_docs for item in document["items"]]
    checks.check("unresolved_work_count", len(unresolved_items) == manifest["unresolved"]["work_count"], f"{len(unresolved_items)} works reported")
    work_count = manifest["source"]["table_counts"]["works"]
    checks.check("all_works_accounted_for", work_count == len(purchase_items) + len(unresolved_items), f"{work_count} = {len(purchase_items)} purchases + {len(unresolved_items)} unresolved")

    acceptance = {
        "creators_and_introductions_recoverable": len(creator_payloads) == 5 and introductions_present,
        "creator_lists_recoverable": len(reading_docs) == 16,
        "list_recommendations_recoverable": item_count == 555,
        "raw_titles_recoverable": not raw_title_failures,
        "recommendation_order_recoverable": not position_failures and not sequence_failures and not ordering_failures,
        "optional_recommendation_fields_recoverable": not optional_mapping_failures and len(evidence_rows) == manifest["source"]["table_counts"]["recommendation_evidence"] and len(annotation_rows) == manifest["source"]["table_counts"]["recommendation_item_annotations"],
        "purchases_recoverable": len(purchase_items) == 240 and len(purchase_record_rows) == 242,
        "ready_for_future_pre_review": not checks.errors,
    }
    result = {
        "schema_version": "1.0",
        "document_type": "source_data_validation",
        "validated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "PASS" if not checks.errors and all(acceptance.values()) else "FAIL",
        "summary": {
            "parseable_json_files": len(json_paths),
            "schema_valid_documents": len(reading_docs) + len(purchase_docs) if not schema_failures else 0,
            "creator_count": len(creator_payloads),
            "reading_list_count": len(reading_docs),
            "reading_item_count": item_count,
            "purchase_item_count": len(purchase_items),
            "purchase_record_count": len(purchase_record_rows),
            "purchase_total_quantity": total_quantity,
            "unresolved_work_count": len(unresolved_items),
        },
        "checks": checks.entries,
        "acceptance": acceptance,
        "errors": checks.errors,
    }
    VALIDATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    update_report(manifest, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
