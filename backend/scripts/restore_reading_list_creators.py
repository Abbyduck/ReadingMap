from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import select


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
SOURCE_ROOT = PROJECT_ROOT / "source_data" / "reading_lists"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal
from app.models.catalog import ReadingListCreator, normalize_search_text


def _creator_values(document: dict) -> tuple[set[str], dict]:
    creator = document.get("creator") or {}
    other = creator.get("other_info") or {}
    profile = other.get("profile") or {}
    source_name = str(creator.get("name") or "").strip()
    display_name = str(other.get("display_name") or source_name).strip()
    if not source_name or not display_name:
        raise ValueError("Reading-list JSON has no creator name")
    aliases = {source_name, display_name}
    values = {
        "name": display_name,
        "tagline": profile.get("positioning"),
        "background": creator.get("introduction"),
        "signature_focus": profile.get("methodology_summary"),
        "avatar_url": profile.get("avatar_url"),
    }
    return aliases, values


def load_creator_profiles() -> list[tuple[set[str], dict]]:
    profiles: dict[str, tuple[set[str], dict]] = {}
    for path in sorted(SOURCE_ROOT.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8-sig"))
        aliases, values = _creator_values(document)
        identity = normalize_search_text(next(iter(sorted(aliases, key=len))))
        existing = profiles.get(identity)
        if existing is None:
            profiles[identity] = (aliases, values)
            continue
        existing_aliases, existing_values = existing
        if existing_values != values:
            raise ValueError(f"Conflicting creator profiles in source JSON: {values['name']}")
        existing_aliases.update(aliases)
    return sorted(profiles.values(), key=lambda row: row[1]["name"].casefold())


def restore(*, apply: bool) -> dict:
    profiles = load_creator_profiles()
    created: list[dict] = []
    reused: list[dict] = []
    filled: list[dict] = []
    with SessionLocal() as db:
        existing_rows = list(db.scalars(select(ReadingListCreator).order_by(ReadingListCreator.id)).all())
        for aliases, values in profiles:
            normalized_aliases = {normalize_search_text(value) for value in aliases}
            matches = [row for row in existing_rows if normalize_search_text(row.name) in normalized_aliases]
            if len(matches) > 1:
                raise ValueError(f"Multiple creator rows match {sorted(aliases)}")
            if matches:
                row = matches[0]
                changed_fields: list[str] = []
                for field in ("tagline", "background", "signature_focus", "avatar_url"):
                    if getattr(row, field) is None and values.get(field) is not None:
                        setattr(row, field, values[field])
                        changed_fields.append(field)
                reused.append({"id": row.id, "name": row.name})
                if changed_fields:
                    filled.append({"id": row.id, "name": row.name, "fields": changed_fields})
                continue
            row = ReadingListCreator(**values)
            if apply:
                db.add(row)
                db.flush()
                existing_rows.append(row)
            created.append({"id": row.id if apply else None, "name": row.name})
        if apply:
            db.commit()
        else:
            db.rollback()
    return {
        "mode": "apply" if apply else "dry-run",
        "source_profile_count": len(profiles),
        "created": created,
        "reused": reused,
        "filled_missing_fields": filled,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Idempotently restore reading-list creators from stable source JSON.")
    parser.add_argument("--apply", action="store_true", help="Commit inserts and safe null-field fills")
    args = parser.parse_args()
    print(json.dumps(restore(apply=args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
