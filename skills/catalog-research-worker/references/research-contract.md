# Reading Map Research Manifest Contract

Create one UTF-8 JSON file per primary subject. The filename is operational only; `subject_id` is the database identity.

```json
{
  "subject_id": 12,
  "source_item_key": "row:1",
  "source_content_sha256": "COPY_THE_CURRENT_BATCH_SOURCE_HASH",
  "identity": {
    "entity_type": "book",
    "display_title": "Example Book",
    "title_zh": null,
    "title_en": "Example Book",
    "aliases": []
  },
  "sources": [
    {
      "key": "publisher",
      "source_type": "publisher",
      "source_url": "https://publisher.example/books/example",
      "source_title": "Example Book — Publisher",
      "fetched_at": "2026-09-08T00:00:00+08:00"
    }
  ],
  "facts": {
    "author": {
      "value": "Example Author",
      "source_keys": ["publisher"]
    },
    "description": {
      "value": "A concise paraphrase of the supported description.",
      "source_keys": ["publisher"]
    }
  },
  "ai_inferences": {
    "entity_type": {
      "value": "book",
      "confidence": 0.99,
      "reason": "The source-list title and publisher page identify one work."
    },
    "classification": {
      "material_type": [
        {"code": "early_reader", "confidence": 0.93, "reason": "The publisher identifies a beginning-reader format."}
      ],
      "genre": [
        {"code": "fiction", "confidence": 0.9, "reason": "The synopsis describes a fictional story."}
      ],
      "theme": null,
      "topic": [],
      "reading_form": null
    },
    "ambiguities": []
  },
  "research_status": "ready",
  "research_version": "codex-research-v1",
  "manual_note": null,
  "related_subjects": []
}
```

## Top-level fields

- `subject_id`: required existing primary Research Subject ID from `queue`.
- `source_item_key` and `source_content_sha256`: required current source row key and batch SHA-256 from `queue`. Together with `subject_id`, these prevent silently replaying an old database's numeric IDs.
- `identity`: required. `entity_type` is one of `book`, `animation`, `reading_system`, `series`, `level`, or `set`. Titles and aliases describe the entity, not a particular seller listing unless that listing is the entity.
- `sources`: required non-empty array for a ready result. `key` is unique inside the manifest. `source_type` should be a useful class such as `author_official`, `publisher`, `lexile`, `accelerated_reader`, `library`, or `retailer`.
- `facts`: objective assertions only. Every entry must be `{ "value": ..., "source_keys": [...] }`. Optional `evidence_note` may explain edition scope or a discrepancy. Never write numeric database IDs here.
- `ai_inferences`: free JSON for derived interpretation. Prefer explicit `value`, `confidence`, and `reason` fields where a reviewer must judge the inference.
- `ai_inferences.classification`: optional controlled proposals grouped only by `material_type`, `genre`, `theme`, `topic`, and `reading_form`. Each non-null dimension is an array of `{code, confidence, reason}` objects. Codes must come from the current `research_worker.py taxonomy` output. Use `null` or `[]` when evidence is insufficient; never create a new code in a manifest.
- When emotional comprehension needs a non-category inference, use `cognitive_detail.emotion_comprehension` with only `external`, `mental`, `reflective`, or `null`; do not expand the category taxonomy for hidden emotion, mixed emotion, or character-intention analysis.
- `research_status`: `ready`, `partial`, or `failed`. Do not use `ready` when the named entity remains ambiguous.
- `research_version`: use `codex-research-v1` for this worker version.
- `manual_note`: optional concise reviewer-facing note.
- `related_subjects`: optional immediate structure described below.

## Fact names

The review UI can display any fact. The later Catalog commit currently understands these sourced keys directly:

- `description`, `cover`
- `author`, `language`, `page_count`, `word_count`, `headwords`
- `ar`, `lexile`
- `isbn` or `isbns`
- `reading_pens`

Useful review-only objective keys include `publisher`, `publication_date`, `official_series_name`, `official_positioning`, `target_readers`, `series_creator`, `series_status`, `member_count`, `members`, and `awards`. State scope in `evidence_note` when a value is edition-, territory-, or date-specific.

For Entity Type, always include `ai_inferences.entity_type` with `value`, `confidence`, and a concise `reason`. Use `animation` for an animated screen work or program identity. For print collections, ask: if reading difficulty, age, and publisher leveling were removed, would the books still naturally form one work series? If yes, prefer `series`; if their shared identity mainly comes from reading stage or product positioning, prefer `reading_system`. Official terms such as line, program, scheme, Stage, Step, and Band do not create additional Entity Types.

`description` must be a concise original paraphrase, not copied marketing text. `cover` must be a stable image URL directly supported by its cited source. Omit fields that cannot be verified.

## Related structure

Use `related_subjects` only for a relationship visible in reliable evidence:

```json
{
  "key": "volume-1",
  "subject_role": "discovered_member",
  "identity": {
    "entity_type": "book",
    "display_title": "First Volume",
    "title_zh": null,
    "title_en": "First Volume",
    "aliases": []
  },
  "sources": [],
  "facts": {},
  "ai_inferences": {},
  "research_status": "ready",
  "research_version": "codex-research-v1",
  "relation": {
    "direction": "member",
    "relation_type": "contains",
    "position": 1,
    "evidence_type": "source_fact",
    "confidence": 1.0
  }
}
```

`direction: member` means the primary subject contains this discovered subject. `direction: parent` means this discovered subject contains the primary. Related subjects are proposed Catalog completion only; they do not inherit the creator recommendation.

If related subjects rely on the same source, repeat that source in their `sources` and cite it from their facts. The database de-duplicates matching source records.

## Readiness rules

A primary subject is `ready` when:

- its entity scope and Entity Type are clear;
- at least one inspected reliable source is linked;
- every objective fact has supporting source keys;
- material ambiguity or conflicting evidence is disclosed;
- AI-derived judgments are separate from facts.

Use `partial` when useful Research exists but entity identity, edition scope, or a key conflict still needs reviewer attention. Use `failed` only when no reliable identification could be made; explain why in `manual_note` and leave unsupported `facts` empty.
