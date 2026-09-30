# Smart Structure Extraction + Human-Assisted Fallback

Date: 2026-09-30
Status: Design approved in chat; implementation pending written-spec review

## Goal

Make Structure Capture resilient across many publisher/retailer pages without adding a full bespoke extractor for every site, while preserving a reliable human-assisted fallback when automatic extraction cannot confidently identify direct members.

This feature is for Structure only. It must not blur the existing Capture boundaries defined by the Reading Map Domain Skill.

## Current problem

The existing official-page capture already has some generic single-page extraction capability, including metadata and JSON-LD parsing, but direct member extraction is still strongly tied to specific DOM assumptions such as Scholastic `.bookDetails` blocks and site-specific URL checks.

That makes the system brittle: a clearly structured series page such as Penguin Random House's Flubby page can visibly contain all direct members while the current extractor returns none.

The fix is not to create one complete extractor per publisher. Instead, Structure Capture should use a layered generic pipeline, with very small site hints only where necessary.

## Core design

All Structure inputs normalize into the same candidate model:

```text
input
  -> structure parser
  -> normalized member candidates
  -> Structure Draft
  -> human review/confirmation
```

The parser must support four input sources:

1. current rendered webpage;
2. a user-selected DOM region / pasted HTML fragment;
3. a pasted URL list;
4. an uploaded or pasted image/screenshot.

Different inputs only change how candidate member evidence is obtained. They do not create separate Structure business logic.

## 1. Automatic webpage extraction

Automatic Structure Capture should run a layered strategy.

### Layer A — structured data

Inspect page-provided structured data first, including when present:

- `ItemList`
- `BookSeries`
- `CollectionPage`
- `hasPart`
- `isPartOf`
- `itemListElement`
- `numberOfItems`
- `BreadcrumbList`

If this yields a coherent direct-member list with adequate confidence, prefer it over DOM heuristics.

### Layer B — generic DOM group detection

If structured data is missing or incomplete, inspect the rendered DOM generically instead of assuming publisher-specific classes.

The generic detector should:

1. locate semantic headings (`h1`/`h2`/`h3`) that suggest a collection, series, books, titles, level, stage, set, etc.;
2. extract declared counts when explicitly present, e.g. `Flubby Series (6 Titles)`;
3. search nearby ancestors/containers for repeated sibling blocks;
4. score candidate repeated groups using signals such as:
   - repeated DOM shape;
   - one or more distinct links per item;
   - images associated with those links;
   - short title-like text;
   - consistent URL patterns;
   - same-site detail URLs;
   - heading proximity;
   - declared count matching detected item count;
5. penalize likely navigation/footer/social/breadcrumb/recommendation areas;
6. choose the highest-confidence group only when confidence exceeds a conservative threshold.

The parser should normalize each accepted member to at least:

```text
- title
- url (when available)
- image/cover candidate (when available)
- position (only from source order)
```

Do not scrape full book metadata during Structure Capture.

### Layer C — lightweight site hints

A small `SiteHints` layer is allowed for unusual sites, but it must stay thin.

A hint may contain facts such as:

- host pattern;
- detail URL patterns;
- ignored section labels;
- known collection-heading patterns.

It must not become a full publisher-specific parser that duplicates the generic extraction pipeline.

## 2. Structure diagnostics

Structure Capture must not fail with only a generic `0 members` message.

Return diagnostic information that can be shown in the Review UI, such as:

```text
page URL
page kind / detected collection heading
declared count
structured-data candidates
DOM candidate groups found
candidate links seen
members accepted
members rejected
confidence
failure stage / reason
```

This allows both users and developers to see whether the failure happened during page targeting, group detection, normalization, filtering, or staging.

## 3. Human-assisted DOM fallback

When automatic webpage extraction is not confident, provide a human-assisted fallback.

### Preferred fallback: choose a region in the monitored browser

The Review UI offers an action such as `选择成员区域`.

The monitored Chrome page enters a lightweight element-selection mode:

- hover highlights candidate DOM elements;
- click selects a containing region;
- the browser returns the selected element's DOM subtree (`outerHTML`) and the current page URL.

The same generic Structure parser then runs on this smaller DOM subtree.

This is not a new extraction algorithm. Human selection only narrows the search scope.

### HTML paste fallback

Also allow pasting an HTML fragment manually.

The system automatically infers repeated member blocks, titles, links, images, and order from the pasted fragment. Do not require the user to supply CSS selectors.

## 4. URL-list fallback

Allow pasting one URL per line.

The Structure parser should create member candidates from those URLs and preserve pasted order.

At Structure stage, URL-list input should not automatically perform full Work/Edition research. It establishes candidate direct membership first.

After Structure Draft is confirmed, a separate optional action may enrich selected members one by one using their URLs.

## 5. Image / screenshot Structure input

Images are a formal Structure input, not merely an error fallback.

Use cases include:

- creator recommendation screenshots;
- retailer/set inventory images;
- unofficial or counterfeit bundles with no authoritative website;
- physical books laid out in a photo;
- book-list collage images.

### Image analysis pipeline

The intended pipeline is:

```text
image
 -> visual layout/group detection
 -> detect cover/card regions
 -> crop candidate book covers
 -> identify title text / visual book identity per crop
 -> recover visual reading order and grouping
 -> normalized Structure candidates
```

Do not rely on whole-image OCR alone.

Where possible, combine:

- visual cover-region detection;
- OCR/text recognition on individual crops;
- catalog-title matching;
- optional cover-image similarity against existing Catalog editions;
- visible group labels and declared counts.

### Group labels from images

A visible heading such as `1+ 阶拓展阅读 36册` may be proposed as a grouping candidate, but image text is not proof that the group is an official publisher Level/Series.

The UI must let the reviewer decide whether a detected image group should:

- become a `set`/other collection candidate;
- be used only as a temporary visual grouping without creating an Entity;
- be ignored.

### Declared count

If an image visibly declares a total count, e.g. `36册`, that may propose `Collection.volume_count = 36` even if fewer members are successfully recognized.

`volume_count` remains the declared/known total, not the number currently recognized or entered.

## 6. Shared normalized candidate model

All four input paths should produce the same logical candidate shape, for example:

```text
StructureMemberCandidate
- title
- url optional
- image optional
- image_crop optional
- position optional
- source_kind: webpage | selected_dom | html | url_list | image
- source_context
- confidence
- diagnostics/evidence
```

This candidate object is Review-side staging data, not final Catalog truth.

No new formal Catalog relationship is committed until human review confirms Structure.

## 7. Optional member enrichment after Structure recognition

After members are recognized/staged, provide a separate optional action such as `批量补全成员资料`.

This action may iterate selected member candidates and run ordinary Work Research against each member URL/title/cover crop.

It is explicitly separate from Structure Capture:

```text
Structure Capture
 -> identify direct membership

Member enrichment
 -> research member metadata
```

Do not let Structure Capture itself recursively scrape full metadata for every member.

## 8. Browser and page snapshot boundary

Reduce direct coupling between extraction logic and Selenium by introducing a snapshot/input boundary where practical.

A page snapshot should contain enough stable data for extraction/testing, e.g.:

```text
url
title
rendered HTML
JSON-LD blocks
```

The browser adapter is responsible for obtaining the snapshot or selected DOM subtree.

Structure parsing should operate on the snapshot/fragment so it can be tested without launching Chrome.

## 9. Review UI

The Structure area remains the home of all Structure actions.

Recommended interaction:

```text
[采集结构]

if automatic extraction is low-confidence or empty:
  [在网页中选择成员区域]
  [粘贴 HTML]
  [粘贴 URL 列表]
  [上传 / 粘贴图片]
```

Image input should support normal upload and clipboard paste when practical.

After parsing, show a preview before formal review staging, including:

- detected groups;
- declared total count;
- member cover crop/image;
- detected title;
- URL if present;
- confidence;
- low-confidence rows that require manual correction.

The user must be able to edit a title/remove a false member before accepting the parsed candidates.

## 10. Capture-boundary invariants

This feature must preserve the Domain Skill's Capture semantics.

Structure Capture may write only Structure Draft / Research structure candidates.

It must not mutate:

- Work Draft metadata;
- Edition Draft;
- Work detail images;
- Classification;
- unrelated Catalog facts.

Image crops and source images are evidence/input for recognition; they do not automatically become authoritative Work or Edition images.

## 11. Error handling

- Low confidence is not silent failure: show diagnostics and fallback actions.
- Unrecognized URLs must be preserved as candidates for human inspection rather than guessed into wrong identities.
- Duplicate candidate members should be deduplicated conservatively using normalized URL/title evidence while preserving distinct books that happen to have similar titles.
- Failed optional enrichment must not delete already-recognized Structure candidates.
- Manual HTML/image/URL input must remain review-side evidence until human confirmation.

## 12. Testing strategy

Add fixture-based tests independent of live websites.

Minimum cases:

1. Penguin Random House Flubby series page:
   - detect collection heading;
   - declared count = 6;
   - detect exactly 6 direct members;
   - preserve order;
   - exclude unrelated series/navigation links.
2. Existing Scholastic-like page fixture:
   - current supported structure behavior remains working after genericization.
3. Structured-data-only page using `ItemList` or equivalent.
4. Generic repeated-card page with no useful CSS class names.
5. Page with an unrelated `You Might Also Like` group that must not win.
6. Selected DOM / pasted HTML fragment using the same generic parser.
7. URL-list input preserving order.
8. Image parsing service contract and Review staging tests using deterministic mocked recognition results.
9. Declared count greater than recognized member count keeps `volume_count` semantics intact.
10. Capture-boundary regression test proving Structure input does not mutate Work/Edition fields.

Live-site tests, if kept at all, should be supplemental rather than the only coverage.

## 13. Scope for first implementation

Implement the architecture incrementally rather than building a heavyweight visual-AI platform immediately.

First implementation should include:

- generic structured-data + DOM Structure parser;
- thin SiteHints support;
- diagnostics;
- manual HTML input;
- manual URL-list input;
- browser DOM-region selection if feasible with the existing debug-browser session;
- image-input API/UI and normalized candidate contract;
- deterministic image-recognition adapter interface so visual recognition can improve independently;
- fixture/regression tests;
- Domain Skill update documenting Structure input modes and the separation between Structure recognition and optional member enrichment.

If high-quality automated visual book recognition requires an external model not already available in the current stack, do not block the rest of the feature. Keep the adapter boundary and make image input usable with the best available recognition path plus manual correction.

## Non-goals

- No automatic Catalog commit from any input.
- No recursive crawl of every discovered book during Structure Capture.
- No new global recommendation behavior.
- No provider-specific full extractor per publisher unless a future real case proves the generic parser + thin hints insufficient.
- No requirement that unofficial image groups be promoted to official Reading System/Level/Series entities.
