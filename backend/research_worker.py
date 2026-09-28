"""Deterministic Research manifest helper; never resolves human review decisions."""
import argparse
import json
import os
from pathlib import Path
from datetime import datetime

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from catalog.models import (
    ALLOWED_CATEGORY_TYPES, ALLOWED_ENTITY_TYPES, CatalogCategory, CatalogEntity,
    ReadingList, ReadingListCreator, ReadingListItem, normalize_search_text,
)
from reviews.models import ResearchSubject, ResearchSubjectSource, ReviewActionLog, ReviewBatch, ReviewItem, ReviewItemSubject
from reviews.services import create_research_relation, create_research_subject, import_source_file, review_item_to_dict, update_research_subject, review_write_transaction

def load_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value

def creator_fields(document):
    creator = document.get("creator") or {}
    other = creator.get("other_info") or {}
    profile = other.get("profile") or {}
    source = str(creator.get("name") or "").strip()
    display = str(other.get("display_name") or source).strip()
    if not source or not display:
        raise ValueError("Source JSON has no creator identity")
    return {source, display}, {"name": display, "tagline": profile.get("positioning"),
        "background": creator.get("introduction"), "signature_focus": profile.get("methodology_summary"),
        "avatar_url": profile.get("avatar_url")}

def ensure_creator(document):
    aliases, values = creator_fields(document)
    normalized = {normalize_search_text(v) for v in aliases}
    matches = [r for r in ReadingListCreator.objects.all() if normalize_search_text(r.name) in normalized]
    if len(matches) > 1:
        raise ValueError(f"Multiple creators match {sorted(aliases)}")
    if not matches:
        return ReadingListCreator.objects.create(**values), True
    row = matches[0]
    for field in ("tagline", "background", "signature_focus", "avatar_url"):
        if getattr(row, field) is None and values.get(field) is not None:
            setattr(row, field, values[field])
    row.save()
    return row, False

def restore_creators(apply=False):
    """Restore source-attributed creator profiles only; never import their lists."""
    documents = {}
    for path in sorted((settings.SOURCE_ROOT / "reading_lists").glob("*.json")):
        document = load_json(path)
        if document.get("document_type") != "reading_list":
            continue
        _, values = creator_fields(document)
        key = normalize_search_text(values["name"])
        documents.setdefault(key, (document, path.name))
    expected = {normalize_search_text(name) for name in ["盖兆泉", "廖彩杏", "庆爸", "香蕉妈妈", "Susan教英语"]}
    if set(documents) != expected:
        raise ValueError("Expected exactly the five agreed source creators; inspect before restoring")
    if not apply:
        return {"dry_run": True, "creators": [
            {"name": creator_fields(doc)[1]["name"], "source": filename}
            for doc, filename in documents.values()]}
    with review_write_transaction():
        before = (ReadingList.objects.count(), ReviewBatch.objects.count(), CatalogEntity.objects.count(), ReadingListItem.objects.count())
        rows = []
        for doc, filename in documents.values():
            row, created = ensure_creator(doc)
            rows.append({"id": row.pk, "name": row.name, "created": created, "source": filename})
        after = (ReadingList.objects.count(), ReviewBatch.objects.count(), CatalogEntity.objects.count(), ReadingListItem.objects.count())
        if before != after:
            raise ValueError("Creator restoration must not change lists, review batches or Catalog")
        return {"dry_run": False, "creators": rows}

def prepare(source_file):
    relative = source_file.replace("\\", "/").removeprefix("source_data/")
    root = settings.SOURCE_ROOT.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() != ".json":
        raise ValueError("source-file must identify a JSON inside source_data")
    document = load_json(path)
    if document.get("document_type") != "reading_list":
        raise ValueError("Research Worker only prepares reading_list documents")
    with review_write_transaction():
        creator, creator_created = ensure_creator(document)
        info = document.get("list") or {}
        title = " ".join(str(info.get("title") or "").split())
        if not title:
            raise ValueError("Source JSON has no reading-list title")
        matches = [r for r in ReadingList.objects.filter(creator=creator) if normalize_search_text(r.title) == normalize_search_text(title)]
        if len(matches) > 1:
            raise ValueError(f"Multiple reading lists match {title}")
        row = matches[0] if matches else ReadingList.objects.create(creator=creator, title=title, description=info.get("description"))
        if row.description is None and info.get("description"):
            row.description = info["description"]
            row.save()
        batch, created = import_source_file(path.relative_to(root).as_posix(), row.pk)
        return {"creator": {"id": creator.pk, "name": creator.name, "created": creator_created},
                "reading_list": {"id": row.pk, "title": row.title, "created": not matches},
                "batch": {"id": batch.pk, "created": created, "total_items": batch.total_items, "status": batch.status}}

def queue(batch_id):
    batch = ReviewBatch.objects.get(pk=batch_id)
    return {"batch": {"id": batch.pk, "source_name": batch.source_name, "source_content_sha256": batch.source_content_sha256, "target_reading_list_id": batch.target_reading_list_id},
            "items": [review_item_to_dict(item) for item in ReviewItem.objects.filter(batch=batch).order_by("position", "id")]}

def identity_values(raw):
    entity_type = raw.get("entity_type")
    title = " ".join(str(raw.get("display_title") or "").split())
    aliases = raw.get("aliases")
    if entity_type not in ALLOWED_ENTITY_TYPES or not title:
        raise ValueError("identity requires valid entity_type and display_title")
    if aliases is not None and (not isinstance(aliases, list) or any(not isinstance(v, str) for v in aliases)):
        raise ValueError("aliases must be an array of strings or null")
    return {"proposed_entity_type": entity_type, "proposed_display_title": title,
            "proposed_title_zh": raw.get("title_zh"), "proposed_title_en": raw.get("title_en"), "proposed_aliases": aliases}

def facts_with_ids(raw, sources):
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("facts must be an object")
    facts = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict) or "value" not in entry or "source_ids" in entry:
            raise ValueError(f"Fact {name} requires value and source_keys, never raw source_ids")
        keys = entry.get("source_keys")
        if not isinstance(keys, list) or not keys or any(not isinstance(key, str) or key not in sources for key in keys):
            raise ValueError(f"Fact {name} has missing or unknown source_keys")
        facts[name] = {k: v for k, v in entry.items() if k != "source_keys"}
        facts[name]["source_ids"] = [sources[key] for key in keys]
    return facts


def validate_ai_inferences(raw):
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("ai_inferences must be an object")
    classification = raw.get("classification")
    if classification is None:
        return raw
    if not isinstance(classification, dict):
        raise ValueError("ai_inferences.classification must be an object")
    unknown_dimensions = set(classification) - ALLOWED_CATEGORY_TYPES
    if unknown_dimensions:
        raise ValueError(f"Unknown classification dimensions: {sorted(unknown_dimensions)}")
    controlled = {
        (category_type, code)
        for category_type, code in CatalogCategory.objects.values_list("category_type", "code")
    }
    for category_type, proposals in classification.items():
        if proposals is None:
            continue
        if not isinstance(proposals, list):
            raise ValueError(f"classification.{category_type} must be an array or null")
        seen = set()
        for proposal in proposals:
            if not isinstance(proposal, dict) or not isinstance(proposal.get("code"), str):
                raise ValueError(f"classification.{category_type} entries require a category code")
            code = proposal["code"]
            if code in seen:
                raise ValueError(f"Duplicate classification code: {category_type}.{code}")
            seen.add(code)
            if (category_type, code) not in controlled:
                raise ValueError(f"Unknown controlled category: {category_type}.{code}")
            confidence = proposal.get("confidence")
            if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1):
                raise ValueError(f"classification confidence must be between 0 and 1: {category_type}.{code}")
    return raw


def taxonomy():
    return {
        "category_types": sorted(ALLOWED_CATEGORY_TYPES),
        "categories": [
            {
                "id": row.pk,
                "category_type": row.category_type,
                "code": row.code,
                "name_zh": row.name_zh,
                "name_en": row.name_en,
                "parent_code": row.parent.code if row.parent_id else None,
            }
            for row in CatalogCategory.objects.select_related("parent").order_by("category_type", "sort_order", "id")
        ],
    }

def apply_subject(subject, manifest):
    identity = identity_values(manifest.get("identity") or {})
    status = manifest.get("research_status")
    if status not in {"ready", "partial", "failed"}:
        raise ValueError("research_status must be ready, partial, or failed")
    if status == "ready" and not manifest.get("sources"):
        raise ValueError("A ready subject requires at least one inspected source")
    values_by_key = {}
    for raw in manifest.get("sources") or []:
        key = str(raw.get("key") or "").strip()
        url = str(raw.get("source_url") or "").strip()
        if not key or not url or key in values_by_key:
            raise ValueError("Each source requires a unique key and source_url")
        fetched = datetime.fromisoformat(raw["fetched_at"].replace("Z", "+00:00")) if raw.get("fetched_at") else None
        if fetched and timezone.is_naive(fetched):
            fetched = timezone.make_aware(fetched)
        values_by_key[key] = {"source_type": raw.get("source_type"), "source_url": url,
                              "source_title": raw.get("source_title"), "fetched_at": fetched}
    if values_by_key:
        update_research_subject(subject, {"sources": list(values_by_key.values())})
    links = list(ResearchSubjectSource.objects.filter(research_subject=subject).select_related("research_source"))
    ids = {}
    for key, values in values_by_key.items():
        matches = [link.research_source_id for link in links if link.research_source.source_url == values["source_url"] and link.research_source.source_title == values["source_title"]]
        if len(matches) != 1:
            raise ValueError(f"Cannot resolve exactly one source for key {key}")
        ids[key] = matches[0]
    return update_research_subject(subject, {**identity, "facts_json": facts_with_ids(manifest.get("facts"), ids),
        "ai_inferences_json": validate_ai_inferences(manifest.get("ai_inferences")), "research_status": status,
        "research_version": manifest.get("research_version") or "codex-research-v1", "manual_note": manifest.get("manual_note"),
        "researched_at": timezone.now()})

def apply_manifest(batch_id, path, actor):
    manifest = load_json(path)
    subject_id = manifest.get("subject_id")
    if type(subject_id) is not int:
        raise ValueError("subject_id must be an integer")
    links = list(ReviewItemSubject.objects.filter(review_item__batch_id=batch_id, research_subject_id=subject_id, subject_role="primary").select_related("review_item", "research_subject"))
    if len(links) != 1:
        raise ValueError(f"Subject {subject_id} must be exactly one primary in batch {batch_id}")
    item, primary = links[0].review_item, links[0].research_subject
    batch = ReviewBatch.objects.get(pk=batch_id)
    if manifest.get("source_item_key") != item.source_item_key or manifest.get("source_content_sha256") != batch.source_content_sha256:
        raise ValueError("Manifest must match the current source row and source content hash; remap old manifests explicitly")
    if item.decision is not None or primary.resolved_catalog_entity_id is not None:
        raise ValueError("Research cannot modify a decided item or resolved subject")
    apply_subject(primary, manifest)
    related_ids, keys = [], set()
    for related in manifest.get("related_subjects") or []:
        key = str(related.get("key") or "").strip()
        if not key or key in keys:
            raise ValueError("Related subjects require unique keys")
        keys.add(key)
        role = related.get("subject_role") or "discovered_member"
        if role not in {"discovered_member", "discovered_parent"}:
            raise ValueError("Related subject cannot become a primary recommendation")
        identity = identity_values(related.get("identity") or {})
        linked = ReviewItemSubject.objects.filter(review_item=item, subject_role=role).select_related("research_subject")
        matches = [r.research_subject for r in linked if r.research_subject.proposed_entity_type == identity["proposed_entity_type"] and normalize_search_text(r.research_subject.proposed_display_title) == normalize_search_text(identity["proposed_display_title"])]
        if len(matches) > 1:
            raise ValueError("Multiple related subjects match")
        subject = matches[0] if matches else create_research_subject({**identity, "research_status": "pending", "review_item_id": item.pk, "subject_role": role})
        if subject.resolved_catalog_entity_id is not None:
            raise ValueError("Research cannot modify resolved related subjects")
        apply_subject(subject, related)
        relation = related.get("relation") or {}
        direction = relation.get("direction")
        if direction not in {"member", "parent"}:
            raise ValueError("relation.direction must be member or parent")
        parent, member = (primary.pk, subject.pk) if direction == "member" else (subject.pk, primary.pk)
        create_research_relation({"parent_subject_id": parent, "member_subject_id": member,
            "relation_type": relation.get("relation_type") or "contains", "position": relation.get("position"),
            "evidence_type": relation.get("evidence_type"), "confidence": relation.get("confidence")})
        related_ids.append(subject.pk)
    ReviewActionLog.objects.create(review_item=item, action="research_update", actor=actor,
        details_json={"subject_id": primary.pk, "related_subject_ids": related_ids, "manifest": Path(path).name})
    return {"manifest": Path(path).name, "review_item_id": item.pk, "subject_id": primary.pk,
            "research_status": primary.research_status, "related_subject_ids": related_ids}

def apply_dir(batch_id, input_dir, actor="catalog-research-worker"):
    paths = sorted(Path(input_dir).resolve().glob("*.json"))
    if not paths:
        raise ValueError("No JSON manifests found")
    with review_write_transaction():
        ReviewBatch.objects.get(pk=batch_id)
        before = (CatalogEntity.objects.count(), ReadingListItem.objects.count())
        results = [apply_manifest(batch_id, path, actor) for path in paths]
        after = (CatalogEntity.objects.count(), ReadingListItem.objects.count())
        if before != after:
            raise ValueError("Research boundary violated: formal data changed")
        return {"batch_id": batch_id, "applied": results}

def verify(batch_id):
    batch = ReviewBatch.objects.get(pk=batch_id)
    items = list(ReviewItem.objects.filter(batch=batch))
    links = ReviewItemSubject.objects.filter(review_item__batch=batch, subject_role="primary").select_related("research_subject")
    subjects = {row.research_subject_id: row.research_subject for row in links}
    statuses = {}
    for subject in subjects.values():
        statuses[subject.research_status] = statuses.get(subject.research_status, 0) + 1
    unresolved = sum(item.decision is None and item.resolved_catalog_entity_id is None for item in items)
    recommendation_count = sum(item.committed_reading_list_item_id is not None for item in items)
    result = {"batch_id": batch.pk, "batch_status": batch.status, "primary_subjects": len(subjects),
              "research_status_counts": statuses, "source_links": ResearchSubjectSource.objects.filter(research_subject_id__in=subjects).count(),
              "unresolved_review_items": unresolved, "formal_reading_list_items": recommendation_count,
              "research_attempts_complete": bool(items) and all(s.research_status in {"ready", "partial", "failed"} for s in subjects.values()),
              "safe_for_human_review": unresolved == len(items) and recommendation_count == 0}
    if not result["safe_for_human_review"]:
        raise ValueError(f"Batch is no longer entirely pre-review: {result}")
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("restore-creators").add_argument("--apply", action="store_true")
    commands.add_parser("taxonomy")
    commands.add_parser("prepare").add_argument("--source-file", required=True)
    for name in ("queue", "verify", "apply-dir"):
        command = commands.add_parser(name)
        command.add_argument("--batch-id", required=True, type=int)
        if name == "apply-dir":
            command.add_argument("--input-dir", required=True)
            command.add_argument("--actor", default="catalog-research-worker")
    args = parser.parse_args()
    if args.command == "restore-creators":
        result = restore_creators(args.apply)
    elif args.command == "taxonomy":
        result = taxonomy()
    elif args.command == "prepare":
        result = prepare(args.source_file)
    elif args.command == "apply-dir":
        result = apply_dir(args.batch_id, args.input_dir, args.actor)
    else:
        result = {"queue": queue, "verify": verify}[args.command](args.batch_id)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
