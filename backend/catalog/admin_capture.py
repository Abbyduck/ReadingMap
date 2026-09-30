"""Human-confirmed Catalog maintenance using the shared source extractors.

The signed candidate is short lived and contains no ReviewItem state. Capture
never writes Catalog truth; confirm applies only explicitly selected fields.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.core import signing
from django.db import transaction

from reviews.amazon_assist import AmazonAssistError, capture_amazon_product, open_amazon_search
from reviews.jd_assist import JdAssistError, capture_jd_product, open_jd_search
from reviews.official_assist import OfficialAssistError, capture_current_official, open_official_search
from reviews.models import ResearchSource

from .models import BookEdition, CatalogEntity, CatalogIsbn, CollectionItem
from .services import CatalogDomainError, add_collection_item, normalize_isbn


ENTITY_FACTS = {"description": "description", "extra_info": "extra_info", "fiction_type": "fiction_type"}
WORK_FACTS = {
    "author": "author_text", "illustrator": "illustrator_text", "translator": "translator_text",
    "language": "language_code", "word_count": "word_count", "headwords": "headword_count",
    "ar": "ar_level", "lexile": "lexile_code",
}
EDITION_FACTS = {"publisher", "format", "page_count", "publication_date", "dimensions"}


def search(provider: str, query: str):
    try:
        if provider == "amazon":
            return open_amazon_search(query)
        if provider == "jd":
            return open_jd_search(query)
        if provider == "official":
            return open_official_search(query)
    except (AmazonAssistError, JdAssistError, OfficialAssistError) as error:
        raise CatalogDomainError(str(error)) from error
    raise CatalogDomainError("Unknown source provider")


def _capture(entity: CatalogEntity, provider: str):
    query = entity.title_en or entity.display_title
    alternates = [entity.display_title, entity.title_zh, *(entity.aliases or [])]
    if provider == "amazon":
        return capture_amazon_product(query)
    if provider == "jd":
        return capture_jd_product(query, alternates)
    if provider == "official":
        subject = SimpleNamespace(proposed_entity_type=entity.entity_type, proposed_display_title=entity.display_title)
        return capture_current_official(subject, query, alternates)
    raise CatalogDomainError("Unknown source provider")


def _adopt_official_cover(url: str, source_url: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.hostname.casefold() in {"localhost", "127.0.0.1"}:
        return None
    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": source_url})
        with urlopen(request, timeout=15) as response:
            content_type = response.headers.get_content_type()
            content = response.read(10 * 1024 * 1024 + 1)
        if not content_type.startswith("image/") or not content or len(content) > 10 * 1024 * 1024:
            return None
        extension = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(content_type, ".jpg")
        directory = Path(settings.BASE_DIR).parent / "research_data" / "official"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (hashlib.sha256(content).hexdigest() + extension)
        if not path.exists():
            path.write_bytes(content)
        return path.relative_to(Path(settings.BASE_DIR).parent).as_posix()
    except Exception:
        return None


def capture_candidate(entity: CatalogEntity, provider: str, scope: str):
    if scope not in {"page", "edition", "structure"}:
        raise CatalogDomainError("Unknown capture scope")
    try:
        capture = _capture(entity, provider)
    except (AmazonAssistError, JdAssistError, OfficialAssistError) as error:
        raise CatalogDomainError(str(error)) from error
    facts = capture.get("facts") or {}
    values = {}
    if scope == "page":
        for source, target in ENTITY_FACTS.items():
            if facts.get(source) not in (None, "", [], {}):
                values[f"entity.{target}"] = facts[source]
        if entity.entity_type == "book":
            for source, target in WORK_FACTS.items():
                if facts.get(source) not in (None, "", [], {}):
                    values[f"work.{target}"] = facts[source]
            details = [row.get("local_path") for row in facts.get("product_images") or []
                       if isinstance(row, dict) and row.get("role") != "cover" and row.get("local_path")]
            if details:
                values["work.detail_images"] = details
    elif scope == "edition":
        if entity.entity_type != "book":
            raise CatalogDomainError("Edition Capture requires a Book")
        for field in EDITION_FACTS:
            if facts.get(field) not in (None, "", [], {}):
                values[field] = facts[field]
        images = facts.get("product_images") or capture.get("downloaded_assets") or []
        cover = next((row for row in images if isinstance(row, dict) and row.get("role") == "cover"), None)
        cover_path = cover.get("local_path") if cover else None
        if not cover_path and provider == "official" and facts.get("cover"):
            cover_path = _adopt_official_cover(facts["cover"], capture.get("source_url") or "")
        if cover_path:
            values["cover_local_path"] = cover_path
        isbns = facts.get("isbns") or []
        values["isbns"] = [normalized for raw in isbns if (normalized := normalize_isbn(str(raw))[1])]
    else:
        if entity.entity_type not in {"reading_system", "level", "series", "set", "franchise"}:
            raise CatalogDomainError("Structure Capture requires a Collection")
        rows = capture.get("members") or [] if provider == "official" else []
        if provider != "official":
            rows = [{"display_title": title, "entity_type": "book"} for title in facts.get("included_titles") or []]
        values["members"] = [{"display_title": row.get("display_title") or row.get("title"),
                              "entity_type": row.get("entity_type") or "book", "position": row.get("position")}
                             for row in rows if isinstance(row, dict) and (row.get("display_title") or row.get("title"))]
    current = {}
    for key in values:
        if key.startswith("entity."):
            current[key] = getattr(entity, key.removeprefix("entity."))
        elif key.startswith("work."):
            current[key] = getattr(entity.work, key.removeprefix("work."))
        elif scope == "edition":
            current[key] = None
        else:
            current[key] = [{"id": row.member_entity_id, "display_title": row.member_entity.display_title}
                            for row in entity.collection.items.select_related("member_entity")]
    payload = {"entity_id": entity.pk, "provider": provider, "scope": scope, "source_url": capture.get("source_url"), "values": values}
    matched_edition_id = None
    if scope == "edition" and values.get("isbns"):
        match = CatalogIsbn.objects.filter(isbn_val__in=values["isbns"], edition__work_id=entity.pk).first()
        matched_edition_id = match.edition_id if match else None
    return {"token": signing.dumps(payload, salt="catalog-admin-capture"), "values": values,
            "current": current, "source_url": capture.get("source_url"), "matched_edition_id": matched_edition_id}


@transaction.atomic
def confirm_candidate(entity: CatalogEntity, token: str, selected_fields: list[str], edition_id=None, members=None, guide_markdown=None):
    try:
        payload = signing.loads(token, salt="catalog-admin-capture", max_age=3600)
    except signing.BadSignature as error:
        raise CatalogDomainError("Capture candidate expired or changed") from error
    if payload.get("entity_id") != entity.pk:
        raise CatalogDomainError("Capture candidate belongs to another Entity")
    values = payload["values"]
    if not set(selected_fields).issubset(values):
        raise CatalogDomainError("Unknown selected capture field")
    scope = payload["scope"]
    if scope == "guide":
        if "entity.guide_markdown" in selected_fields:
            entity.guide_markdown = guide_markdown if guide_markdown is not None else values["entity.guide_markdown"]
            entity.save(update_fields=["guide_markdown"])
    elif scope == "page":
        for key in selected_fields:
            target, field = key.split(".", 1)
            obj = entity if target == "entity" else entity.work
            setattr(obj, field, values[key])
        entity.full_clean()
        entity.save()
        if entity.entity_type == "book":
            entity.work.full_clean()
            entity.work.save()
    elif scope == "edition":
        if not selected_fields:
            return entity
        edition = BookEdition.objects.filter(pk=edition_id, work_id=entity.pk).first() if edition_id else BookEdition(work_id=entity.pk)
        if edition is None:
            raise CatalogDomainError("Edition belongs to another Work")
        for key in selected_fields:
            if key != "isbns":
                setattr(edition, key, values[key])
        edition.full_clean()
        edition.save()
        if "isbns" in selected_fields:
            for raw in values["isbns"]:
                kind, normalized = normalize_isbn(raw)
                existing = CatalogIsbn.objects.filter(isbn_type=kind, isbn_val=normalized).first()
                if existing and existing.edition_id != edition.pk:
                    raise CatalogDomainError("ISBN already belongs to another Edition")
                if not existing:
                    CatalogIsbn.objects.create(edition=edition, isbn_type=kind, isbn_val=normalized)
    else:
        if "members" not in selected_fields:
            return entity
        proposed = values["members"]
        for row in members or []:
            index = row.get("index")
            if not isinstance(index, int) or index < 0 or index >= len(proposed):
                raise CatalogDomainError("Unknown structure candidate")
            candidate = proposed[index]
            member_id = row.get("catalog_entity_id")
            if member_id:
                member = CatalogEntity.objects.filter(pk=member_id).first()
                if member is None:
                    raise CatalogDomainError("Structure member not found")
            elif row.get("create_new"):
                member = CatalogEntity.objects.create(entity_type=candidate["entity_type"], display_title=candidate["display_title"])
            else:
                continue
            add_collection_item(entity.pk, member.pk, candidate.get("position"))
    return entity


def add_guide_material(entity: CatalogEntity, raw_content: str, source_title=""):
    ResearchSource.objects.create(source_type="manual_guide", source_url=f"manual://catalog/{entity.pk}/{hashlib.sha256(raw_content.encode()).hexdigest()}",
                                  source_title=source_title or "手工资料", raw_content=raw_content)
    markdown = "\n\n".join(line.strip() for line in raw_content.splitlines() if line.strip())
    payload = {"entity_id": entity.pk, "scope": "guide", "values": {"entity.guide_markdown": markdown}}
    return {"token": signing.dumps(payload, salt="catalog-admin-capture"), "draft": markdown,
            "current": entity.guide_markdown}
