---
name: catalog-research-worker
description: Research Reading Map source JSON into the pre-review database with cited objective facts, AI inferences, Catalog candidates, and optional collection structure. Use after wild reading-list JSON exists and before a human makes MATCH EXISTING, CREATE NEW, or IGNORE decisions; never use it to approve or write final Catalog entities.
---

# Catalog Research Worker

Turn a stable source JSON reading list into a research-complete review batch. Preserve the boundary between source facts, externally verified facts, and AI inference.

## Required contract

Before writing research, read [references/research-contract.md](references/research-contract.md). Also read the selected source JSON completely. Do not edit that JSON during Research; it is immutable provenance produced by the earlier extraction workflow.

Use the deterministic database helper at `backend/research_worker.py` from the repository root, with `backend/.venv/Scripts/python.exe`. The helper creates or reuses the JSON's creator and one reading-list shell, imports a review batch, resolves source keys to database IDs, refreshes Catalog candidates, records audit events, and verifies that no formal Catalog or recommendation relationship was written.

## Workflow

1. Confirm the configured Django database has the `catalog` and `reviews` migrations (`backend/manage.py showmigrations`). Do not run the legacy SQLAlchemy/Alembic scripts. If the user requests restoring the five existing creators, preview `backend/research_worker.py restore-creators`, then use `restore-creators --apply`; this restores profiles only, not all their lists. Database schema upgrades require the authority provided by the current user task; otherwise stop and report the required migration.
2. Prepare exactly one JSON with `backend/research_worker.py prepare --source-file <source_data-relative-path>`. Reuse the returned batch on repeat runs.
3. Read the queue with `backend/research_worker.py queue --batch-id <id>` and load the current controlled classification vocabulary with `backend/research_worker.py taxonomy`. Research every distinct primary subject in that batch unless the user asks for a smaller sample.
4. Search the web for identity and objective metadata. Prefer the author/series site and publisher; use the official Lexile or Accelerated Reader source for those measurements. A retailer or library catalog can corroborate edition facts but should not silently define the work's identity.
5. Correct the proposed Entity Type when evidence contradicts extraction analysis. Use exactly `book`, `animation`, `reading_system`, `series`, `level`, or `set`. A title with sequels is not automatically a series: the named object may still be one `book`.
6. Write one manifest per primary subject, following the Research contract. IDs must come from the current database queue, never an old database's manifest. Temporary manifests are replay inputs; the database is the research archive. Put sourced facts in `facts`; put classifications, Syntax/Cognitive judgments, ambiguity, and recommendations in `ai_inferences`. Classification may only use codes returned by `taxonomy`, may select multiple codes in a dimension, and must use `null` or an empty list when evidence is insufficient. Never invent a formal category code. A synopsis, source-list description, series/level identity, official category, or a small amount of interior-page evidence can support classification; full text is not required. Without adequate text or a calibrated rubric, leave numeric scores unknown and provide qualitative reasoning. Use `partial` when important identity ambiguity remains. Conflicting credible measures belong in review-only evidence, not a canonical field that would auto-fill on commit.
7. Add immediate collection members only when an authoritative source enumerates them and the structure materially helps this review. Do not explode a long franchise into every edition, translation, box set, or adaptation. Members discovered from Research receive no creator recommendation relationship.
8. Apply manifests with `backend/research_worker.py apply-dir --batch-id <id> --input-dir <dir>`, then run `backend/research_worker.py verify --batch-id <id>`.
9. Stop with all review items unresolved. Report the batch ID, reading-list ID, ready/partial/failed counts, source coverage, remaining ambiguity, and where the user can review. Never choose MATCH EXISTING, CREATE NEW, IGNORE, conflict resolution, or structure inclusion on the user's behalf.

## Evidence discipline

- Every objective fact must cite one or more manifest `source_keys`. The helper rejects uncited facts and converts keys to linked database `source_ids`.
- Describe only what the linked page supports. Do not use search snippets as evidence when the underlying page cannot be inspected.
- Keep edition-specific ISBN, page count, cover, and publication facts separate from work/series-level facts. If the source list does not identify an edition, record edition examples in inference notes instead of asserting them as the entity's canonical facts.
- Preserve conflicting credible values rather than averaging them. Explain the conflict in `ai_inferences` and mark the subject `partial` when it affects identity.
- Derived age suitability, category, language/syntax/cognitive scores, and “good for” judgments are AI inference even when informed by sources.
- Category confidence and reasoning remain in `ai_inferences_json`; human-approved Catalog links never inherit confidence or source weights.
- Record a concise reason for `book`, `animation`, `reading_system`, `series`, `level`, or `set`. Use the title's referred scope, not the format of a seller's product page.
- Use `animation` for an animated screen work or animated program identity. It is not a Collection type and does not receive `collection_items` merely because it has episodes or seasons.
- Use `reading_system` for a publisher product line organized chiefly by reading age, stage, ability, or difficulty, especially when it spans authors, characters, and multiple independent Series. Use `series` when the books still form one natural body of work after age, difficulty, and publisher leveling are removed because they share characters, a world, a creative identity, or an explicit series brand.
- Treat publisher terms such as line, reader line, reading program, reading scheme, leveled reader program, and product line as naming variants, not new Entity Types. Treat Level, Stage, Step, and Band as `level`.
- Observe explicit official-page structure signals such as Series, Part of, From the ... line, An ... Book, Back to, Explore, Imprint, Collection, Level, breadcrumbs, URL paths, section titles, return links, and cover badges. When the current official page already states a direct parent relationship, record it without a redundant site-restricted search.
- When Official Research discovers a new parent Collection, do only one lightweight background lookup sufficient for a Collection Brief: publisher, positioning, approximate audience/age, and a short paraphrased description. Do not enumerate every sibling, hunt for catalogs or leveling PDFs, or recursively explore the whole product line during item review; that belongs to the user-facing “系列探索” flow.

## Safety boundary

Research may create review subjects, sources, candidates, and proposed structure. It must not create Catalog entities, add `reading_list_items`, overwrite existing Catalog fields, resolve conflicts, or mark review decisions. Only the later human-review action may cross that boundary.
