---
name: wild-reading-list-to-json
description: Use when converting creator-curated reading lists from screenshots, PDFs, webpages, spreadsheets, documents, or pasted text into stable Reading Map source JSON before pre-review.
---

# Wild Reading List to JSON

Create one durable, database-independent JSON document per logical reading list.

Reading Map domain semantics defer to `.codex/skills/reading-map-domain-model/SKILL.md`. This extraction skill preserves source facts and must not decide final Catalog identity.

## Canonical source contract

Before producing or changing output, read the complete canonical Schema at [`../../../source_data/schemas/reading-list.schema.json`](../../../source_data/schemas/reading-list.schema.json).

Emit the schema version/document type required by that Schema. Do not silently change an existing schema version's meaning; propose a schema change/version change when the source contract must evolve.

Write output under `source_data/reading_lists/` unless the user specifies another location. The filename is operational, not an identifier or source fact.

## Preserve source facts

- Keep creator/list identity exactly enough to identify the supplied source.
- Keep every recommendation occurrence; repeated recommendations in different ages/stages remain separate occurrences.
- `raw_title` preserves what the source actually says, including bundle wording, volume counts, unusual punctuation, or commerce wording.
- Preserve source order. Only populate an explicit position/rank when the source actually provides one.
- Preserve source-provided age, AR, Lexile, level, comment/note, emphasis, category, and other annotations. Do not discard details simply because they lack a dedicated field.
- Preserve page/screenshot/cell/row/URL/text provenance when available.
- Use `null`/empty values for unknowns. Do not search for or guess missing bibliographic/recommendation data in this extraction step.

## Extraction boundaries

Normalization may clean whitespace/punctuation or unmistakable promotional noise without changing the referred scope.

Do not:
- turn a multi-volume title into a Series merely because it looks series-like;
- split one recommendation into several Catalog objects;
- merge separate recommendation occurrences;
- decide final Book/Series/Level/Set/Franchise identity from weak clues;
- write Catalog/Review/database records.

`analysis` is non-authoritative review assistance only. If the current source schema's `possible_entity_type` enum cannot express a newer Domain-Skill type, prefer `unknown` plus a note rather than coercing it into the wrong older type. Schema evolution is a separate explicit change.

## Validate before delivery

Parse every output JSON and validate it against the canonical Schema. Confirm that item count, array order, explicit positions, exact `raw_title` values, creator/list facts, recommendation annotations, and provenance survived extraction.

Ambiguity stays ambiguity; report it rather than resolving it by invention.