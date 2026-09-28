---
name: wild-reading-list-to-json
description: Convert creator-curated reading lists from screenshots, PDFs, webpages, spreadsheets, documents, or pasted text into stable Reading Map source JSON. Use for preserving recommendation facts before pre-review; do not use to write a database or create final Catalog entities.
---

# Wild Reading List to JSON

Create one durable, database-independent JSON document per logical reading list.

## Canonical contract

Before producing or changing output, read the complete canonical Schema at [`../../source_data/schemas/reading-list.schema.json`](../../source_data/schemas/reading-list.schema.json). Emit `schema_version: "1.0"` and `document_type: "reading_list"`. Do not silently change the meaning of version 1.0; propose a new version when the contract must change.

Write output under `source_data/reading_lists/` unless the user specifies another location. Use a filesystem-safe `creator-name__list-name.json` style name; the filename is not an identifier or a source fact.

## Preserve source facts

- Record the creator name and list title exactly enough to identify them. Put a creator introduction and other profile fields in `creator` only when the supplied source contains them; otherwise use `null` and `{}`.
- Keep every recommendation occurrence. Never remove an item because it appears elsewhere or more than once.
- Set `raw_title` to the title text as it appears in the source. Preserve unusual punctuation, bundle wording, volume counts, and commerce wording there.
- Preserve the source order in the JSON array. Set `position` from an explicit rank/order when present, or `null` when the source has no order. Set `sequence` to the 1-based array order. When positions reset within sections, preserve the section/stage and its order in `extracted.other_info`.
- Preserve source-provided recommended age, AR, Lexile, level, comment, note, emphasis, category, and other annotations. Put details without a dedicated field in `extracted.other_info` rather than discarding them.
- Preserve source-page, screenshot, cell, row, URL, or quoted-text provenance in `other_info` when available.
- Use `null` for unknown values. Do not search for or guess missing bibliographic, reading-level, age, creator, or recommendation data.

## Extraction boundaries

`extracted.title` may normalize whitespace, punctuation, or unmistakable promotional noise without changing the referred scope. It must not turn a multi-volume title into a series name, split one recommendation into several books, merge separate entries, or decide whether ambiguous text is a book, series, level, or set.

Treat `analysis` as non-authoritative review assistance:

- `possible_entity_type` must be one of `book`, `animation`, `reading_system`, `series`, `level`, `set`, or `unknown`.
- Use a conservative confidence value and explain the observable clue in `notes`.
- Prefer `unknown` when the source does not support a useful classification.
- Never move an analysis inference into a source-fact field.

Do not create or update works, series, sets, levels, catalog entities, review tables, or any other database record. This skill's final artifact is JSON for a later `source JSON -> pre-review -> human review -> Catalog` workflow.

## Validate before delivery

Parse every output JSON and validate it against the canonical Schema. Confirm that item count, array order, explicit positions, exact `raw_title` values, creator data, list data, and all source-present optional recommendation fields survived extraction. Report source ambiguities as `null` or review notes; do not resolve them by invention.
