from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import CatalogEntity, normalize_search_text


def resolve_existing_entity(db: Session, raw_title: str) -> tuple[CatalogEntity | None, str | None]:
    """Resolve only an unambiguous existing entity; never creates catalog data."""
    normalized = normalize_search_text(raw_title)
    candidates = list(db.scalars(select(CatalogEntity).where(CatalogEntity.search_text.contains(normalized))).all())
    exact = [entity for entity in candidates if normalized in (entity.search_text or "").splitlines()]
    if len(exact) == 1:
        return exact[0], None
    if len(exact) > 1:
        return None, "multiple catalog candidates"
    return None, "no catalog candidate"


def resolve_migration_rows(db: Session, rows: list[dict], unresolved_path: Path) -> dict[str, int]:
    unresolved: list[dict] = []
    resolved = 0
    for row in rows:
        entity, reason = resolve_existing_entity(db, str(row.get("raw_title") or ""))
        if entity:
            row["catalog_entity_id"] = entity.id
            resolved += 1
        else:
            unresolved.append({"source": row.get("source"), "raw_title": row.get("raw_title"), "reason": reason})
    unresolved_path.write_text(json.dumps(unresolved, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"resolved": resolved, "unresolved": len(unresolved), "catalog_entities": db.scalar(select(func.count(CatalogEntity.id))) or 0}
