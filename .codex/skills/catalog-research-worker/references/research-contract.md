# Reading Map Research Manifest Contract

This is an operational Research manifest contract. Reading Map domain semantics defer to `.codex/skills/reading-map-domain-model/SKILL.md`.

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
      "genre": [],
      "theme": [],
      "topic": [],
      "reading_form": []
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

- `subject_id`: existing primary Research Subject ID from the current queue.
- `source_item_key` + `source_content_sha256`: current source-row key and batch hash; together with `subject_id` they prevent replay against the wrong batch/database state.
- `identity`: required. `entity_type` must follow the canonical Domain Skill. If the current manifest/helper validation has not yet caught up with a Domain-Skill type, do not silently coerce it into another type; leave unresolved or report the implementation gap.
- `sources`: linked evidence sources inspected for this subject.
- `facts`: objective assertions only; every value must cite one or more `source_keys`.
- `ai_inferences`: derived interpretation such as Entity Type reasoning, controlled Classification proposals, ambiguity, or qualitative difficulty reasoning.
- `research_status`: `ready`, `partial`, or `failed`; do not use `ready` when identity remains materially ambiguous.
- `manual_note`: concise reviewer-facing note when useful.
- `related_subjects`: optional directly related structure only.

## Classification

Classification proposals use only the current controlled dimensions:

- `material_type`
- `genre`
- `theme`
- `topic`
- `reading_form`

Codes must come from the current `research_worker.py taxonomy` output. Use `null`/`[]` when evidence is insufficient; do not invent codes.

`fiction_type` is a separate Catalog attribute in the Domain Model rather than a substitute for the full `genre` dimension. Only propose it when the current review/helper contract supports it; otherwise preserve the evidence for human review rather than hiding it inside an unrelated category.

## Fact scope

The review UI may display more facts than the commit path currently understands. Keep scope explicit:

- Work/content facts: title identity, author/illustrator/translator, language, word/headword counts, AR, Lexile, work-level description/detail-image evidence.
- Edition/version facts: cover, ISBN, publisher, format, page count, publication date, dimensions.
- Structure facts: direct parent/member identity and explicit position when supported.

Do not flatten Edition facts into Work merely because an older helper currently has a single fact bucket. Preserve scope in `evidence_note`/review inference until implementation catches up.

Useful review-only objective keys can include official positioning, target readers, member count/list, awards, and other directly sourced facts. Omit unsupported fields.

`description` must be an original concise paraphrase rather than copied marketing text.

## Related structure

Use `related_subjects` only for a direct relationship visible in reliable evidence.

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

`direction: member` means the primary subject directly contains this subject. `direction: parent` means this subject directly contains the primary. Do not add transitive ancestry. Related Research subjects never inherit the creator recommendation.

## Readiness

A primary subject is `ready` when:

- its referred identity/scope is clear enough for human review;
- at least one inspected reliable source is linked;
- objective facts cite evidence;
- material conflicts/ambiguity are disclosed;
- derived inference remains separate from facts.

Use `partial` when useful Research exists but identity, Edition scope, or a material conflict still needs reviewer attention. Use `failed` only when no reliable identification can be made.