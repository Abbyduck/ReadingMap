---
name: reading-map-domain-model
description: Use when a Reading Map task can change Catalog, Entity/Work/Edition identity, Review/Research, Structure, ReadingList, Classification, Guide, Bookshelf, Plan, reading logs, or recommendation semantics.
---

# Reading Map Domain Model

This is the canonical domain/business-semantics reference for Reading Map.

## 1. Product boundary

Reading Map structures trusted creators' reading routes into a reusable Catalog, then later combines Catalog facts with a child's owned/read history, reading mode, classifications, and feedback to produce practical reading suggestions.

Current implementation priority: **build a high-quality Catalog through the admin Review/Research workflow**. Public frontend, Plan, reading check-ins/photo recognition, and the personalized recommendation engine are later phases unless explicitly requested.

Catalog may be incomplete. Unknown data is valid; never invent completeness.

## 2. Authority and reasoning

When sources conflict:

1. user's current explicit requirement;
2. this Domain Model Skill;
3. the current task's explicit implementation requirements;
4. current code and regression tests;
5. reference/source material.

Old plans, deleted docs, stale handoffs, QA diaries, and Git history are **not fallback requirements**. Read them only when the user explicitly asks for historical investigation.

If code conflicts with this skill, treat code as implementation that may need to change.

### Model Before Workaround

When a requirement is awkward, first question whether the current model assumption should change. Prefer a simpler model correction over UI/technical workarounds created only to preserve an old abstraction.

Distinguish:
- **hard invariants**: violations cause identity/data corruption or expensive migration;
- **soft semantics**: useful conventions with legitimate gray areas.

Do not repeatedly tighten a soft definition unless a real data case fails to fit.

## 3. Catalog / Research / Review / ReadingList

- **Catalog**: standardized current truth used by the product; incomplete is valid.
- **Research**: evidence, candidates, source-derived facts, AI inferences, unresolved possibilities.
- **Review**: human gate deciding what becomes Catalog truth. Research is optional enrichment, never a prerequisite.
- **ReadingList / ReadingListItem**: creator-specific route/recommendation context such as order, source age range, source AR/Lexile/level text, comments, emphasis, and creator-recommended Edition.

Do not move creator-specific recommendation facts into Catalog truth.

## 4. CatalogEntity types

Target types:

- `book`
- `animation`
- `reading_system`
- `level`
- `series`
- `set`
- `franchise` — UI may label this `IP`

### book
Independent reading work. A Book CatalogEntity has a 1:1 Work extension.

### animation
Watchable animation unit. It is not Collection-capable by default.

### reading_system
Reading/learning system mainly organized by ability, age, stage, difficulty, teaching, or publishing scheme, e.g. Oxford Reading Tree, I Can Read, Little Fox. Nested systems are allowed when meaningful.

### level
A stage/level such as ORT Level 5 or I Can Read My First. It may be recommended directly and may contain other Entities.

### series
A stable series/subseries/product grouping. Do not impose unnecessary purity rules such as “must be single-medium” in schema.

### franchise
Higher-level IP/franchise such as Pete the Cat or Peppa Pig. It may connect book series, animation series, and other relevant subgroups.

### set
A deliberately flexible reusable combination:

> A member combination with enough independent meaning to be referenced, recommended, or reused as a unit.

It may come from a creator and may not exist on an official website. Do not over-constrain it to official retail bundles.

There is no PersonalSet in the current design. Add one only if a real future use case requires private reusable grouping.

## 5. Structure / Collection

Collection-capable target types:
`reading_system`, `level`, `series`, `set`, `franchise`.

Structure is a **DAG**, not a tree.

Rules:
- multiple parents are allowed;
- store only **direct** membership edges;
- never materialize transitive ancestry as duplicate CollectionItems;
- empty Collection Entities are valid;
- `CollectionItem.position` is optional and only for explicit/meaningful sequence;
- never infer persisted order from AR, Lexile, title, popularity, etc.;
- repeated Structure capture merges/deduplicates rather than requiring a complete tree in one pass;
- Catalog structure stores current truth; Research may retain evidence/provenance.

## 6. Book identity: Entity + Work + Edition

### Book Entity / Work

For books, CatalogEntity is the content identity and Work is its 1:1 book-specific extension. They are not two independent product identities.

Same Book Entity / Work generally includes:
- cover or publisher changes;
- paperback/hardcover/board-book form when core reading content is unchanged;
- different ISBN;
- modest layout/front-matter/page-count differences;
- point-reading extras when core content is unchanged.

Create a new Book Entity / Work for:
- substantive text differences;
- different translation;
- bilingual/adapted/abridged/rewrite versions;
- substantially shortened text;
- substantially different interior illustrations, especially for picture books.

Cover difference alone does not define a new Work.

Work-level content facts include author, illustrator, translator, language, word/headword count, AR, Lexile, reliable content/difficulty facts, and interior `detail_images`.

### Edition

Edition is **not** a CatalogEntity. It is lightweight version/physical-recognition context under one Work.

Edition may be sparse. Typical optional facts:
- cover local path;
- publisher;
- format;
- page count;
- publication date;
- dimensions.

A visibly distinct formal/official cover is enough to create a lightweight Edition even when ISBN is unknown. ISBN/format metadata can also justify a sparse Edition before cover is known.

Do not create a new Edition for crop, resolution, perspective, retailer-photo, or promo-wrap differences.

Same ISBN + different cover: default to the same Edition candidate first and let the human choose; do not auto-split.

Different ISBN is a signal, not an automatic Edition split.

### ISBN

ISBN belongs to Edition, not directly to Work.

One Edition may have zero, one, or multiple ISBN records. ISBN-10 and ISBN-13 representations of the same physical version do not imply separate Editions. Never infer Edition count from ISBN count.

## 7. Semantic field contracts

Document field semantics here only when misunderstanding the field would change business behavior.

| Field | Business meaning | Must NOT mean |
|---|---|---|
| `Collection.volume_count` | Known/declared complete size of the Collection | Current entered member count |
| `CollectionItem.position` | Explicit meaningful order inside that Collection | Difficulty/title-derived sort |
| `ReadingListItem.position` | Creator/source-list order | Collection member order |
| `ReadingListItem.recommended_edition_id` | Edition selected for this specific creator recommendation | Global default/recommended Edition |
| `Work.detail_images` | Work-level interior previews | Edition/retailer product gallery |
| `Edition.cover` | Cover for that Edition/version context | Global CatalogEntity cover truth |
| `CatalogEntity.guide_markdown` | Curated explanatory/practical content for that Entity | Raw Research paste or purchase-only note |
| `fiction_type` | `fiction` / `nonfiction` / `mixed` / `unknown` | Genre score or recommendation result |

Example: official Series total = 12, currently entered members = 5 → `volume_count = 12`; never auto-sync it to 5.

## 8. Images and display cover

Authoritative cover belongs to Edition.

Amazon/JD/official URLs are Research inputs. Once an image is adopted into Catalog, save it to self-controlled storage and reference the self-hosted path.

`Work.detail_images` are interior previews shared across Editions of the same Work.

Do not introduce a heavy ImageAsset CMS until a real need appears.

Display APIs may flatten cover resolution for convenience, but must not duplicate cover ownership:
- Map → current ReadingListItem's recommended Edition;
- My Bookshelf → owned Edition;
- public/fallback → configured default public creator/list's recommended Edition.

## 9. ReadingList recommendation facts

A `ReadingListItem` means the creator/source recommended that Entity in that list/stage.

- Research-discovered parents/siblings/members do not inherit the recommendation.
- Do not use a numeric weak/normal/strong scale as formal recommendation truth.
- `is_strong_recommendation` is true only when the source explicitly communicates strong emphasis or the human reviewer confirms it.
- `recommendation_emphasis_text` may preserve source wording.
- ranking, rating, occurrence count, or visual prominence must not fabricate strong recommendation.
- `recommended_edition_id` belongs to the recommendation relationship; there is no global `Edition.is_recommended`.

## 10. Classification

Classification must be human-readable and useful even without any recommendation algorithm.

Controlled dimensions:
- `material_type`
- `genre`
- `theme`
- `topic`
- `reading_form`

Do not build dynamic inheritance/synchronization.

When a new Series is created from a current Book context, the Book's Classification may be copied into the Series Draft as editable initial values. After creation they are independent. Do not auto-copy a Book's classification into broad entities such as reading_system, level, franchise, or set.

### Fiction / nonfiction

Keep `fiction_type` as a dedicated filterable attribute:
`fiction`, `nonfiction`, `mixed`, `unknown`.

Do not bury this only inside genre; it supports later filtering and reading-balance statistics.

## 11. Search identity

Book search should include:
- title / aliases;
- author;
- illustrator;
- translator.

Do not create Edition title/alias complexity until a real use case appears.

## 12. Guide

`CatalogEntity.guide_markdown` is optional Markdown containing that Entity's curated/practical explanatory content. It is broader than a purchase guide.

It may contain version comparison, how to understand/use the Entity, reading suggestions, practical warnings, point-reading notes, and purchase/use advice.

It is distinct from:
- `description`: what the Entity is;
- `extra_info`: extra factual information;
- raw Research input.

Manual material flow:
`raw Research material -> AI-organized Guide Draft -> human edit/confirm -> guide_markdown`.

In Structure UI, the currently selected node is the target Entity for right-side Entity editing, including Guide input. Do not add a redundant target selector.

## 13. Research / Review invariants

### Optional enrichment

Amazon/JD/official Research, Structure, and Classification are optional enrichment. None is a gate for creating Catalog, reusing an existing Entity, or committing a ReviewItem.

### Human Draft precedence

Research never silently overwrites human Draft or existing Catalog truth.

- empty Draft + reliable candidate may prefill;
- reliable sources that agree may prefill;
- same value is a no-op;
- conflicts preserve the human/Catalog value and surface candidates for human choice.

Do not define a global source priority such as official > Amazon > JD.

### Draft safety

Human edits such as Catalog Draft, recommendation notes/emphasis, image choices, Edition choices, and Guide Draft must not disappear during refresh/Research/capture.

Before Search or any Capture, autosave dirty Draft state. If save fails, stop the action and show a visible error. Do not disable Search/Capture merely because Draft is dirty.

### Catalog Match

A match is a candidate, not an identity decision.

Before confirmation, do not prefill the current new-object Draft from the matched Entity.

Candidate detail should be read-only and show enough Work identity information plus existing Edition covers where useful.

After human decision:
- same → reuse Entity and resolve Edition as needed;
- not same → clean new Book Entity / Work path with no leaked values.

Reusing an Entity never forces Research.

### Search sources vs. Capture purposes

Search source and Capture purpose are two different dimensions.

#### Search sources

The main Research toolbar provides direct source-specific search actions:

- Search Amazon
- Search JD
- Search Official

They all open/use the same monitored helper-browser session.

Do not require a provider tab switch before searching. The reviewer chooses the source directly by clicking the corresponding Search button.

Search only decides where to look. It does not decide the business write target.

### Three Capture purposes

There are three distinct capture purposes:

1. **Current Page / Research** → Entity/Work Research candidates, content identity facts, and Work detail images.
2. **Current Edition** → Edition Draft only: cover, ISBN, publisher, format, page count, publication date, dimensions.
3. **Structure** → Structure Draft only: Collection identity, direct parent/member relationships, and explicit sequence when truly present.

These are business destinations, not provider choices.

Amazon / JD / Official are source providers.
Current Page / Edition / Structure are capture purposes.

Never multiply capture purposes by source provider.

Edition capture must not mutate/re-run Work Draft or Work detail images. Structure capture must not mutate Work, Edition, images, Classification, or generic Work facts.

#### Capture Current Page

The main Research toolbar has exactly one shared Current Page capture action.

Amazon, JD, and Official do **not** have separate Current Page Capture buttons.

When the reviewer clicks Capture:

1. inspect the current target page in the monitored browser;
2. determine the provider from the current URL/host;
3. dispatch to the appropriate provider extractor;
4. write only Entity/Work Research candidates allowed by Current Page capture.

Examples:
- `amazon.*` → Amazon extractor;
- `jd.com` → JD extractor;
- recognized publisher/official site → Official extractor.

The reviewer must not need to tell the system again which provider is open. The current browser URL is the source of truth.

If the URL cannot be recognized safely, fail visibly and ask the reviewer to navigate to a supported target page. Do not guess a provider.

Flow:

provider-specific Search
→ reviewer navigates/chooses the intended page
→ one shared Current Page Capture
→ provider inferred from current URL
→ provider-specific extractor
→ normalized Entity/Work Research candidates

Official pages never auto-capture.

#### Current Edition placement

Capture Current Edition belongs to the Edition review/edit area because its result is Edition Draft.

It does not belong in the main Entity/Work Research toolbar.

If the Review page does not yet have an Edition section, do not add a temporary top-level Edition capture button merely to expose the action. Leave the action unexposed until the Edition area is implemented.

#### Structure capture placement

Capture Structure belongs to the Structure area.

It may inspect the current page in the same monitored browser and choose a site adapter from the URL, but its output remains Structure Draft only.

The single Capture button in the main Research toolbar means Current Page Research; it does not replace the Structure area's explicit structure capture.

The browser flow should track the current search/target/child tab instead of blindly using stale unrelated tabs. Capture failures must be visible.

### Source image

The original source screenshot/current recommendation image is read-only review context. It is not Catalog data, not an Edition candidate by itself, and must not automatically become cover/detail images.

### Structure review

Left structure node selection defines the right-side Inspector/Edit target. Do not add a second target-selection mechanism.

Names/labels are Research clues, not proof of a relation. Formal structure needs reliable evidence or human confirmation.

### Commit integrity

Catalog/structure commit is transactional. A failed critical step must not leave half-written Entity, Edition, ReadingList, or Structure state.

### Preserve useful review capability

Do not remove candidate comparison, conflicts, image selection, evidence, human Drafts, source-image context, or other useful Review helpers merely to simplify architecture. Understand the user-facing purpose first.

## 14. Catalog Admin Detail/Edit

Current phase is admin-only.

Catalog Admin maintains current Catalog truth after commit and should support, where applicable:
- Entity fields;
- Work;
- Editions + ISBNs;
- Structure;
- Classification;
- Guide.

It may reuse the same Research/browser/extractor engine as Review.

> Research engine is shared; Review state is not.

Catalog Admin capture should create candidate/diff state for human confirmation and then update Catalog truth; do not force ordinary Catalog maintenance through ReviewItem.

## 15. Future personalized recommendation — principles only

Do not implement the recommendation engine during the current admin/catalog phase unless explicitly requested.

Long-term principles:
- recommendation is `Book × Child × Reading Mode × Context`;
- distinguish `shared_reading` and `independent_reading`;
- creator age ranges remain source evidence;
- AR/Lexile/reading-system levels are guardrails/relative evidence, not direct month conversions;
- classification, especially Topic and some Theme signals, can support child-specific familiarity;
- real reading history/feedback gradually calibrates the child profile;
- algorithm output is dynamic/versioned, never Catalog truth;
- preserve raw facts so algorithms can be replaced without Catalog migration;
- `fiction_type` supports filtering and future reading-balance analysis.

Existing 0–10 difficulty/ability tables are not unquestionable truth. Leave them alone during the current admin refactor unless a required migration touches them.

## 16. Current-phase exclusions

Unless explicitly requested, do not expand the current admin work into:
- ReadingLog/check-in history;
- photo multi-book recognition;
- ISBN check-in UX;
- reading-statistics UI;
- Plan;
- Child recommendation profiles;
- recommendation scoring/ranking UI;
- public product frontend;
- My Bookshelf frontend.

Current work should only ensure Catalog captures the facts those later systems will need.

## 17. Common failure modes

- Research becomes mandatory before commit.
- Edition becomes a CatalogEntity.
- ISBN remains directly on Work after Edition exists.
- CatalogEntity keeps an authoritative cover.
- transitive Collection memberships are persisted.
- `volume_count` is replaced by entered-member count.
- classification becomes dynamically inherited.
- `set`/`series` are over-constrained for conceptual purity.
- source screenshot becomes Edition/Catalog image data.
- Edition capture mutates Work.
- Structure capture mutates unrelated fields.
- provider-specific Current Page Capture buttons are duplicated instead of using one shared Capture action.
- Edition capture is exposed in the main Research toolbar before an Edition area exists.
- Review and Catalog Admin get separate Research engines.
- Guide becomes a fixed CMS schema prematurely.
- personalized recommendation output is stored as Catalog truth.
- stale docs/history are used to resurrect old behavior.