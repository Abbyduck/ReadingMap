---
name: catalog-research-worker
description: Use when researching Reading Map source JSON into the pre-review database before a human makes Catalog identity and structure decisions.
---

# Catalog Research Worker

Turn a stable source JSON reading list into a research-complete review batch while preserving the boundary between source facts, externally verified facts, AI inference, and final Catalog truth.

**Domain authority:** `.codex/skills/reading-map-domain-model/SKILL.md` defines Reading Map Entity/Work/Edition/Structure semantics. If this operational skill or the current helper disagrees with the Domain Skill, do not coerce data to the older model; stop and report the implementation gap.

## Required contract

Before writing research, read [references/research-contract.md](references/research-contract.md) and the selected source JSON completely. Do not edit the source JSON during Research; it is immutable provenance from the earlier extraction workflow.

Use the deterministic helper at `backend/research_worker.py` from the repository root with `backend/.venv/Scripts/python.exe`. The helper may create/reuse review-side research records, resolve source keys, refresh candidates, and verify that no formal Catalog or creator-recommendation relationship was written.

## Workflow

1. Confirm the configured Django database has the current `catalog` and `reviews` migrations (`backend/manage.py showmigrations`). Do not run the legacy SQLAlchemy/Alembic workflow as current product infrastructure.
2. Prepare one JSON with `backend/research_worker.py prepare --source-file <source_data-relative-path>`. Reuse the returned batch on repeat runs.
3. Read the queue with `backend/research_worker.py queue --batch-id <id>` and the current controlled classification vocabulary with `backend/research_worker.py taxonomy`.
4. Research identity and objective metadata. Prefer author/series/publisher official sources; use official Lexile/Accelerated Reader sources for those measurements. Retailers/libraries can corroborate version facts but must not silently define Work identity.
5. Propose the Entity Type according to the Domain Skill. If the current helper/schema cannot represent a Domain-Skill type (for example a newly introduced type such as `franchise` before implementation catches up), do not mislabel it as another type merely to make the helper accept it; stop/report the gap or leave the proposal unresolved as the current contract permits.
6. Write one manifest per primary subject using the Research contract. IDs come from the current queue, never an old manifest. Put sourced objective facts in `facts`; put classification/ambiguity/derived interpretation in `ai_inferences`. Do not invent category codes or numeric difficulty scores when evidence/rubric is insufficient.
7. Add only immediate/direct structure supported by reliable evidence. Do not materialize transitive ancestry or explode a franchise/system into every descendant during item review. Research-discovered related subjects receive no creator recommendation relationship.
8. Apply manifests with `backend/research_worker.py apply-dir --batch-id <id> --input-dir <dir>`, then run `backend/research_worker.py verify --batch-id <id>`.
9. Stop with review decisions unresolved. Report batch/list IDs, ready/partial/failed counts, evidence coverage, remaining ambiguity, and the review entry point. Never choose MATCH EXISTING, CREATE NEW, IGNORE, conflict resolution, or structure inclusion on the user's behalf.

## Evidence discipline

- Every objective fact cites one or more manifest `source_keys`.
- Describe only what the inspected source supports; search snippets alone are not evidence.
- Keep Edition-specific ISBN/page-count/cover/publication facts separate from Work facts, following the Domain Skill.
- Preserve conflicting credible values; do not average them into false certainty.
- Derived age suitability, classification, or difficulty judgments remain AI inference unless the source explicitly states them.
- Category confidence/reasoning remains review-side inference; approved Catalog links do not inherit source weights.
- Official labels such as line/program/scheme/Stage/Step/Band are clues, not automatic new Entity Types.
- Observe direct structure signals such as Series, Part of, From the…, Level, breadcrumbs, section titles, return links, and cover badges.
- When a parent Collection is discovered, one lightweight background lookup is enough for review context. Do not recursively enumerate the whole product line during item review.

## Safety boundary

Research may create review subjects, sources, candidates, evidence, and proposed direct structure. It must not create final Catalog entities, add creator `reading_list_items`, overwrite human/Catalog truth, resolve conflicts, or mark review decisions. Only the human-reviewed commit may cross that boundary.