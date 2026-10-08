"""Human-confirmed, Review-only staging of structure evidence from any input kind."""
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import uuid4

from django.utils import timezone

from .models import (
    ResearchSource, ResearchSubject, ResearchSubjectRelation,
    ResearchSubjectSource, ReviewItemSubject,
)
from .services import ReviewDomainError, _touch_research_items, refresh_catalog_candidates

_COLLECTION_TYPES = {"reading_system", "level", "series", "set", "franchise"}


def stage_structure_candidates(*, item, parent, members, declared_count=None,
                               group_choice="none", group_title="", group_type="set",
                               actor=""):
    """Called inside review_write_transaction. Never modifies Work/Edition/Classification."""
    if item.status in {"resolved", "ignored"} or not item.subject_links.filter(research_subject=parent).exists():
        raise ReviewDomainError("Cannot stage structure on this review item")
    if len(members) > 500:
        raise ReviewDomainError("一次最多确认 500 个成员")
    if group_choice not in {"none", "create"}:
        raise ReviewDomainError("Invalid group choice")
    if group_choice == "create" and (group_type not in _COLLECTION_TYPES or not group_title.strip()):
        raise ReviewDomainError("创建分组必须选择有效类型与名称")
    if group_choice == "none" and parent.proposed_entity_type not in _COLLECTION_TYPES:
        raise ReviewDomainError("请先将当前对象设为 Collection 类型，或选择创建一个分组")

    container = parent
    if group_choice == "create":
        label = group_title.strip()
        link = next((row for row in parent.member_relations.select_related("member_subject")
                     if row.member_subject.proposed_display_title == label), None)
        if link is not None:
            container = link.member_subject
        else:
            container = ResearchSubject.objects.create(
                proposed_entity_type=group_type, proposed_display_title=label,
                proposed_title_zh=label if any("\u4e00" <= c <= "\u9fff" for c in label) else None,
                proposed_title_en=label if all(ord(c) < 128 for c in label) else None,
                research_status="partial",
            )
            ReviewItemSubject.objects.get_or_create(
                review_item=item, research_subject=container,
                defaults={"subject_role": "discovered_member"})
            ResearchSubjectRelation.objects.get_or_create(
                parent_subject=parent, member_subject=container,
                relation_type="contains", defaults={"review_status": "proposed"})
    source_url = next((row.get("url") for row in members if row.get("url")), None)
    if not source_url:
        source_url = f"manual://structure/{item.pk}/{uuid4().hex}"
    source = ResearchSource.objects.create(
        source_type="structure_input", source_url=source_url,
        source_title=group_title or container.proposed_display_title or "成员结构输入",
        fetched_at=timezone.now())
    ResearchSubjectSource.objects.get_or_create(research_subject=container, research_source=source)

    existing = list(container.member_relations.select_related("member_subject"))
    relation_ids = []
    for row in members:
        title = " ".join(row.get("title", "").split()).strip()
        if not title:
            continue
        candidate_url = row.get("url") or ""
        relation = None
        for known in existing:
            if (known.member_subject.proposed_display_title or "").casefold() != title.casefold():
                continue
            known_urls = set(known.member_subject.source_links.values_list("research_source__source_url", flat=True))
            known_urls = {url for url in known_urls if url.startswith(("https://", "http://"))}
            if not candidate_url or not known_urls or candidate_url in known_urls:
                relation = known
                break
        if relation is None:
            member = ResearchSubject.objects.create(
                proposed_entity_type="book", proposed_display_title=title,
                proposed_title_en=title if all(ord(c) < 128 for c in title) else None,
                research_status="partial",
                ai_inferences_json={"structure_candidate": {
                    "source_url": row.get("url"),
                    "preview_image": row.get("image") if isinstance(row.get("image"), str)
                                     and row["image"].startswith(("https://", "http://")) else None,
                }},
            )
            ReviewItemSubject.objects.get_or_create(
                review_item=item, research_subject=member,
                defaults={"subject_role": "discovered_member"})
            relation = ResearchSubjectRelation.objects.create(
                parent_subject=container, member_subject=member,
                relation_type="contains",
                position=row.get("position"),
                evidence_type="source_fact",
                confidence=Decimal(str(max(0.0, min(1.0, float(row.get("confidence", 0.5)))))),
                review_status="proposed",
            )
            existing.append(relation)
            refresh_catalog_candidates(member)
        ResearchSubjectSource.objects.get_or_create(research_subject=relation.member_subject,
                                                     research_source=source)
        if row.get("url") and urlsplit(row["url"]).scheme in {"http", "https"}:
            member_source = ResearchSource.objects.create(
                source_type="structure_member_url", source_url=row["url"],
                source_title=title, fetched_at=timezone.now())
            ResearchSubjectSource.objects.get_or_create(research_subject=relation.member_subject,
                                                         research_source=member_source)
        relation_ids.append(relation.pk)

    # Explicit total size is a Review fact candidate; never derive it from member count.
    if declared_count is not None:
        facts = dict(container.facts_json or {})
        previous = facts.get("volume_count")
        if previous is None or (isinstance(previous, dict) and previous.get("value") is None):
            facts["volume_count"] = {"value": declared_count, "source_ids": [source.pk]}
            container.facts_json = facts
            container.save(update_fields=["facts_json", "updated_at"])
        elif (previous.get("value") if isinstance(previous, dict) else previous) != declared_count:
            hints = dict(container.ai_inferences_json or {})
            hints["structure_declared_count_conflict"] = {
                "existing": previous, "proposed": declared_count, "source_id": source.pk}
            container.ai_inferences_json = hints
            container.save(update_fields=["ai_inferences_json", "updated_at"])
    _touch_research_items([parent.pk, container.pk])
    return {"relation_ids": relation_ids, "container_subject_id": container.pk}
