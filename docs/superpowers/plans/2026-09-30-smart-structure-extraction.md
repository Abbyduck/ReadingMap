# Smart Structure Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace brittle publisher-specific Structure extraction with a generic structured-data/DOM pipeline, add diagnostics and human-assisted inputs (DOM region, HTML, URL list, image), and keep member enrichment separate from Structure recognition.

**Architecture:** Introduce a testable `reviews.structure_extractors` package that consumes page snapshots or manual inputs and returns one normalized preview model. Browser/Selenium code only produces snapshots/selected DOM; Review services stage a human-confirmed preview into existing `ResearchSubject`/`ResearchSubjectRelation` rows. All inputs share the same staging path; site-specific knowledge is limited to small hints. Image input gets the same candidate contract via an adapter interface, without blocking the rest of the feature on a heavyweight vision dependency.

**Tech Stack:** Python 3.12, Django 5.2, DRF, Selenium 4.49, BeautifulSoup4 (new pure-Python parsing dependency), React 19 + TypeScript + Vite.

**Spec:** `docs/superpowers/specs/2026-09-30-smart-structure-extraction-design.md`

## Global Constraints

- Structure Capture may write only Review-side Structure Draft/candidates until the reviewer confirms them.
- Structure recognition must not mutate Work Draft, Edition Draft, Work detail images, Classification, or unrelated Catalog facts.
- Do not create a full parser per publisher; use generic extraction plus thin `SiteHints` only where proven necessary.
- `Collection.volume_count` is declared/known total size, not entered/recognized member count.
- Automatic Structure recognition and later member metadata enrichment are separate actions.
- No automatic Catalog commit from webpage, HTML, URL-list, DOM-region, or image inputs.
- Keep the existing monitored Chrome session; do not create a second browser subsystem.
- Existing local Review/Catalog changes must be preserved. Before implementation, work from the user's actual current branch/commit, not an older `main` snapshot.

## Review Focus

- A page contains a correct series grid plus a larger `You Might Also Like` grid: the real direct-member group must win and the recommendation grid must be excluded.
- A source declares 36 titles but only 28 are recognized: proposed `volume_count` remains 36 while 28 members are staged.
- Two member cards share very similar titles but distinct URLs: conservative dedupe must keep both.
- Manual HTML/URL/image input fails partway through: previously recognized Structure candidates remain intact and Work/Edition facts remain unchanged.
- A browser page is unsupported or ambiguous: diagnostics explain the failure and expose manual fallbacks instead of guessing a provider or silently returning zero.

---

## File Structure

### New backend files

- `backend/reviews/structure_extractors/__init__.py` — public extraction interfaces.
- `backend/reviews/structure_extractors/types.py` — snapshot/candidate/result dataclasses and serialization helpers.
- `backend/reviews/structure_extractors/structured_data.py` — JSON-LD `ItemList`/`BookSeries`/`CollectionPage` extraction.
- `backend/reviews/structure_extractors/dom_groups.py` — generic repeated-DOM-group discovery/scoring.
- `backend/reviews/structure_extractors/site_hints.py` — intentionally small host/URL/ignore-label hints.
- `backend/reviews/structure_extractors/parser.py` — orchestrates structured-data, DOM, HTML fragment, and URL-list parsing.
- `backend/reviews/structure_extractors/image.py` — image-recognition adapter protocol + default unavailable implementation + normalization contract.
- `backend/reviews/browser_structure.py` — create page snapshots from monitored Chrome; start/poll DOM-region picker.
- `backend/reviews/fixtures/structure/flubby-prh.html` — deterministic Penguin-like regression fixture.
- `backend/reviews/fixtures/structure/scholastic-series.html` — deterministic fixture for current supported pattern.
- `backend/reviews/fixtures/structure/generic-cards.html` — class-name-independent repeated-card fixture.
- `backend/reviews/fixtures/structure/itemlist-only.html` — structured-data-only fixture.

### New frontend file

- `frontend/src/components/review/StructureInputPanel.tsx` — Structure input/preview/fallback UI; keeps new complexity out of giant `App.tsx`.

### Modified backend files

- `backend/requirements.txt` — add `beautifulsoup4`.
- `backend/reviews/official_assist.py` — stop owning direct-member DOM parsing; keep official single-page metadata capture and delegate Structure parsing.
- `backend/reviews/services.py` — extract reusable Structure staging service from current `apply_official_capture` member/parent loop.
- `backend/reviews/serializers.py` — serializers for Structure preview/stage/manual inputs.
- `backend/reviews/views.py` — Structure preview, region-picker, image-preview, stage endpoints.
- `backend/reviews/urls.py` — route new Structure endpoints.
- `backend/reviews/tests.py` — service/API/capture-boundary tests.

### Modified frontend files

- `frontend/src/api/client.ts` — Structure preview/stage/region/image types and API methods.
- `frontend/src/App.tsx` — mount `StructureInputPanel`, keep existing tree/review state integration, and relabel existing member research as enrichment.
- `frontend/src/styles.css` — preview/diagnostics/fallback layout only.

### Modified documentation

- `.codex/skills/reading-map-domain-model/SKILL.md` — document Structure input modes, generic-extractor principle, human-assisted fallback, and separation from member enrichment.

---

### Task 1: Normalized Structure extraction core

**Files:**
- Create: `backend/reviews/structure_extractors/__init__.py`
- Create: `backend/reviews/structure_extractors/types.py`
- Create: `backend/reviews/structure_extractors/structured_data.py`
- Create: `backend/reviews/structure_extractors/dom_groups.py`
- Create: `backend/reviews/structure_extractors/site_hints.py`
- Create: `backend/reviews/structure_extractors/parser.py`
- Create: `backend/reviews/fixtures/structure/flubby-prh.html`
- Create: `backend/reviews/fixtures/structure/scholastic-series.html`
- Create: `backend/reviews/fixtures/structure/generic-cards.html`
- Create: `backend/reviews/fixtures/structure/itemlist-only.html`
- Modify: `backend/requirements.txt`
- Test: `backend/reviews/tests.py`

**Interfaces:**
- Produces: `PageSnapshot`, `StructureMemberCandidate`, `StructureGroupCandidate`, `StructureDiagnostics`, `StructureExtractionResult`.
- Produces: `extract_structure(snapshot: PageSnapshot, *, html_fragment: str | None = None, url_list: list[str] | None = None) -> StructureExtractionResult`.
- Later tasks consume the serialized result; no Django model dependency belongs in this package.

- [ ] **Step 1: Write failing fixture tests for structured-data, Flubby, Scholastic, and class-name-independent cards**

Add tests with assertions equivalent to:

```python
result = extract_structure(PageSnapshot.from_html(url, html))
self.assertEqual(result.declared_count, 6)
self.assertEqual([m.title for m in result.members], EXPECTED_FLUBBY_TITLES)
self.assertEqual(len(result.members), 6)
self.assertFalse(any("Other Series" in m.title for m in result.members))
```

Also pin:
- `ItemList` extraction without useful DOM classes;
- source order preservation;
- distinct URLs prevent over-deduping similar titles;
- declared count can exceed member count.

- [ ] **Step 2: Run the focused tests and confirm they fail because the extraction package does not exist**

Run:
```powershell
backend\.venv\Scripts\python.exe backend\manage.py test reviews.tests.StructureExtractorTests -v 2
```
Expected: FAIL/import error or missing extractor assertions.

- [ ] **Step 3: Add `beautifulsoup4` and define extraction dataclasses**

`types.py` must define exact public fields:

```python
@dataclass(frozen=True)
class PageSnapshot:
    url: str
    title: str
    html: str
    json_ld: tuple[dict, ...] = ()

@dataclass(frozen=True)
class StructureMemberCandidate:
    title: str
    url: str | None
    image: str | None
    position: int | None
    confidence: float
    source_kind: str
    source_context: dict

@dataclass(frozen=True)
class StructureGroupCandidate:
    title: str | None
    declared_count: int | None
    confidence: float
    members: tuple[StructureMemberCandidate, ...]
    evidence: dict

@dataclass(frozen=True)
class StructureDiagnostics:
    strategy: str
    candidate_group_count: int
    candidate_link_count: int
    accepted_member_count: int
    rejected_member_count: int
    confidence: float
    messages: tuple[str, ...]

@dataclass(frozen=True)
class StructureExtractionResult:
    group: StructureGroupCandidate | None
    members: tuple[StructureMemberCandidate, ...]
    declared_count: int | None
    diagnostics: StructureDiagnostics
```

Add `to_dict()` helpers used by DRF views.

- [ ] **Step 4: Implement structured-data extraction**

Support `ItemList`, `itemListElement`, `numberOfItems`, `BookSeries`, `CollectionPage`, and `hasPart` where the source actually supplies usable title/URL data. Prefer explicit `position`; otherwise preserve source order without inventing a semantic sort.

- [ ] **Step 5: Implement generic DOM group scoring**

Use BeautifulSoup's parsed DOM. Candidate groups are repeated sibling/container blocks; score on repeated shape, distinct URLs, images, short title-like text, same-host/detail-like URLs, nearby collection heading, and declared-count agreement. Penalize `nav`, `footer`, breadcrumb/social blocks, and headings such as `You Might Also Like`, `Related`, or equivalent recommendation sections.

`site_hints.py` may contain only small host-specific hints such as detail URL patterns and ignored labels; no site-specific end-to-end extractor functions.

- [ ] **Step 6: Implement the orchestration function and conservative dedupe**

Priority:
1. coherent structured data;
2. highest-confidence DOM group;
3. low-confidence/empty result with diagnostics.

Dedupe by canonical URL first; title-only dedupe is allowed only when normalized titles match exactly and no distinct URL evidence exists.

- [ ] **Step 7: Run focused tests**

Run:
```powershell
backend\.venv\Scripts\python.exe backend\manage.py test reviews.tests.StructureExtractorTests -v 2
```
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/requirements.txt backend/reviews/structure_extractors backend/reviews/fixtures/structure backend/reviews/tests.py
git commit -m "feat: add generic structure extractor"
```

---

### Task 2: Browser snapshot and automatic Structure preview

**Files:**
- Create: `backend/reviews/browser_structure.py`
- Modify: `backend/reviews/official_assist.py`
- Modify: `backend/reviews/tests.py`

**Interfaces:**
- Consumes: `PageSnapshot` and `extract_structure(...)` from Task 1.
- Produces: `capture_current_structure_snapshot(subject_titles: list[str]) -> tuple[PageSnapshot, dict]`.
- Produces: `preview_current_browser_structure(subject_titles: list[str]) -> StructureExtractionResult`.

- [ ] **Step 1: Write failing browser-adapter tests**

Mock DevTools/Selenium so tests prove:
- current eligible page becomes a `PageSnapshot`;
- Google/search/local admin tabs are ignored;
- page URL/title/html/JSON-LD reach the parser unchanged;
- ambiguous/no eligible target returns visible diagnostic error rather than picking a stale unrelated tab.

- [ ] **Step 2: Run focused tests and verify failure**

Run:
```powershell
backend\.venv\Scripts\python.exe backend\manage.py test reviews.tests.StructureBrowserTests -v 2
```
Expected: FAIL because adapter functions do not exist.

- [ ] **Step 3: Implement browser snapshot creation**

Reuse the existing debug Chrome session primitives from `amazon_assist.py`. Keep browser targeting separate from extraction. The adapter gathers rendered `outerHTML`, page URL/title, and JSON-LD into `PageSnapshot`.

- [ ] **Step 4: Remove direct-member parsing responsibility from `official_assist.py`**

Keep official Work/Entity metadata capture intact. Replace the current Scholastic `.bookDetails` member loop with delegation to the generic Structure path where Structure capture calls it. Do not make ordinary `Capture Current Page` start staging Structure as a side effect.

Existing Scholastic behavior is protected by Task 1 fixtures rather than by a hard-coded full extractor.

- [ ] **Step 5: Run browser + official regression tests**

Run:
```powershell
backend\.venv\Scripts\python.exe backend\manage.py test reviews.tests.OfficialSearchTests reviews.tests.StructureBrowserTests reviews.tests.StructureExtractorTests -v 2
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/reviews/browser_structure.py backend/reviews/official_assist.py backend/reviews/tests.py
git commit -m "refactor: separate browser snapshots from structure parsing"
```

---

### Task 3: Preview/stage API and one shared Structure staging service

**Files:**
- Modify: `backend/reviews/services.py`
- Modify: `backend/reviews/serializers.py`
- Modify: `backend/reviews/views.py`
- Modify: `backend/reviews/urls.py`
- Modify: `backend/reviews/tests.py`

**Interfaces:**
- Produces: `stage_structure_candidates(item: ReviewItem, parent_subject: ResearchSubject, candidates: list[dict], *, group: dict | None, actor: str) -> tuple[list[int], list[int]]`.
- HTTP: `POST /api/review/items/<item_id>/structure/preview`.
- HTTP: `POST /api/review/items/<item_id>/structure/stage`.
- Preview response: `{ members, group, declared_count, diagnostics }`.
- Stage request: reviewer-edited normalized members plus optional group decision; stage returns refreshed `ReviewItem` and created/reused relation IDs.

- [ ] **Step 1: Write failing API/service tests**

Pin:
- browser preview returns candidates but creates zero new `ResearchSubjectRelation` rows;
- stage creates/reuses Review-side subjects + direct relations only after POST stage;
- reviewer-edited title/order is respected;
- declared count is preserved as a Research candidate/fact for the collection without replacing it with staged member count;
- repeated stage calls dedupe equivalent direct relations;
- Work/Edition facts on primary subject are byte-for-byte unchanged after Structure preview/stage.

- [ ] **Step 2: Run tests and verify failure**

Run:
```powershell
backend\.venv\Scripts\python.exe backend\manage.py test reviews.tests.StructurePreviewApiTests -v 2
```
Expected: FAIL because endpoints/service do not exist.

- [ ] **Step 3: Extract Structure staging from `apply_official_capture` into `stage_structure_candidates`**

Move only the subject/relation staging responsibility. Ordinary official Work capture must no longer implicitly stage direct members. Reuse current candidate refresh/dedupe behavior where correct.

- [ ] **Step 4: Add serializers**

Define:
- `StructurePreviewSerializer` with `input_kind="browser"|"html"|"url_list"`, optional `html`, optional `urls`;
- `StructureMemberCandidateSerializer` for editable title/url/image/position/confidence/source context;
- `StructureStageSerializer` with `members`, optional group title/entity-type decision, optional declared count.

Reject unsupported input combinations; never accept arbitrary Catalog-write fields here.

- [ ] **Step 5: Add preview/stage views and routes**

`browser` preview calls Task 2. `html`/`url_list` call Task 1 directly. Stage calls only `stage_structure_candidates` inside `review_write_transaction()`.

- [ ] **Step 6: Run tests**

Run:
```powershell
backend\.venv\Scripts\python.exe backend\manage.py test reviews.tests.StructurePreviewApiTests -v 2
```
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/reviews/services.py backend/reviews/serializers.py backend/reviews/views.py backend/reviews/urls.py backend/reviews/tests.py
git commit -m "feat: add structure preview and staging API"
```

---

### Task 4: Manual HTML and URL-list fallback

**Files:**
- Modify: `backend/reviews/structure_extractors/parser.py`
- Modify: `backend/reviews/tests.py`

**Interfaces:**
- Consumes the Task 3 preview endpoint.
- `extract_structure(..., html_fragment=<fragment>)` parses only the fragment but resolves relative links using snapshot/source URL when provided.
- `extract_structure(..., url_list=[...])` produces ordered member candidates without performing full member Research.

- [ ] **Step 1: Add failing tests for pasted HTML and URL list**

Assert:
- copied Flubby-like containing DIV yields the same six members;
- relative links become absolute against source URL;
- one URL per line preserves order;
- malformed/blank lines are reported in diagnostics without crashing;
- URL list does not trigger network calls or Work/Edition mutation.

- [ ] **Step 2: Run tests and verify failure**

Run:
```powershell
backend\.venv\Scripts\python.exe backend\manage.py test reviews.tests.StructureManualInputTests -v 2
```
Expected: FAIL.

- [ ] **Step 3: Implement HTML fragment and URL-list normalization**

Reuse the same candidate types/dedupe/diagnostics from Task 1; do not create a second manual parsing model.

- [ ] **Step 4: Run tests**

Expected: PASS for `StructureManualInputTests`.

- [ ] **Step 5: Commit**

```bash
git add backend/reviews/structure_extractors/parser.py backend/reviews/tests.py
git commit -m "feat: support manual structure html and urls"
```

---

### Task 5: Browser DOM-region picker fallback

**Files:**
- Modify: `backend/reviews/browser_structure.py`
- Modify: `backend/reviews/views.py`
- Modify: `backend/reviews/urls.py`
- Modify: `backend/reviews/tests.py`

**Interfaces:**
- HTTP: `POST /api/review/items/<item_id>/structure/region-select/start`.
- HTTP: `GET /api/review/items/<item_id>/structure/region-select/status`.
- Start injects a temporary picker overlay into the current monitored page.
- Status returns `pending | selected | cancelled | failed`; when selected, it parses returned `outerHTML` through the same Task 1 parser and returns the normal Structure preview shape.

- [ ] **Step 1: Write failing tests around picker state and cleanup**

Mock the browser driver. Assert injected script:
- highlights hovered elements without modifying page navigation;
- stores selected `outerHTML` and source URL;
- supports Escape/cancel;
- removes its event listeners/styles after select/cancel;
- status uses the generic parser rather than bespoke DOM parsing.

- [ ] **Step 2: Run tests and verify failure**

Run:
```powershell
backend\.venv\Scripts\python.exe backend\manage.py test reviews.tests.StructureRegionPickerTests -v 2
```
Expected: FAIL.

- [ ] **Step 3: Implement start/status picker flow**

Do not keep one long HTTP request waiting for the click. Start injects; frontend polls status. Keep picker state scoped to the current debug-browser page and review item.

- [ ] **Step 4: Run tests**

Expected: PASS for `StructureRegionPickerTests`.

- [ ] **Step 5: Commit**

```bash
git add backend/reviews/browser_structure.py backend/reviews/views.py backend/reviews/urls.py backend/reviews/tests.py
git commit -m "feat: add browser region structure picker"
```

---

### Task 6: Image Structure input contract and API

**Files:**
- Create: `backend/reviews/structure_extractors/image.py`
- Modify: `backend/reviews/serializers.py`
- Modify: `backend/reviews/views.py`
- Modify: `backend/reviews/urls.py`
- Modify: `backend/reviews/tests.py`

**Interfaces:**
- Produces protocol: `ImageStructureRecognizer.recognize(image_bytes: bytes, *, filename: str, context: dict) -> StructureExtractionResult`.
- Default implementation: `UnavailableImageStructureRecognizer` returns explicit diagnostics, never fake titles.
- HTTP: `POST /api/review/items/<item_id>/structure/image-preview` as multipart form with one image.
- Image-preview response uses exactly the same `{members, group, declared_count, diagnostics}` contract as webpage/manual preview.

- [ ] **Step 1: Write failing adapter/API tests using a deterministic fake recognizer**

Fake recognition should model the Oxford Tree example:
- visible group label `1+ 阶拓展阅读`;
- `declared_count = 36`;
- a small deterministic set of cover/title candidates with image-crop references/confidences.

Assert:
- API normalizes fake recognition into standard Structure preview;
- declared count can exceed recognized members;
- image preview creates no formal relation until stage;
- no Work/Edition image is written from the uploaded source image/crop.

- [ ] **Step 2: Run tests and verify failure**

Run:
```powershell
backend\.venv\Scripts\python.exe backend\manage.py test reviews.tests.StructureImageInputTests -v 2
```
Expected: FAIL.

- [ ] **Step 3: Implement the recognizer protocol and explicit default-unavailable adapter**

Do not add a heavyweight OCR/vision runtime in this task unless the current repo already has a configured model provider. The unavailable adapter must produce a user-facing diagnostic such as `图片已接收，但当前未配置自动视觉识别器；可手动修正/录入成员，后续识别器可无缝接入同一候选协议。`

- [ ] **Step 4: Implement multipart image-preview endpoint with size/type validation**

Accept common image MIME types only; impose a conservative upload-size limit. Keep the uploaded image as temporary input/evidence for preview, not Catalog media.

- [ ] **Step 5: Run tests**

Expected: PASS for `StructureImageInputTests`.

- [ ] **Step 6: Commit**

```bash
git add backend/reviews/structure_extractors/image.py backend/reviews/serializers.py backend/reviews/views.py backend/reviews/urls.py backend/reviews/tests.py
git commit -m "feat: add image structure input contract"
```

---

### Task 7: Review UI for automatic and human-assisted Structure input

**Files:**
- Create: `frontend/src/components/review/StructureInputPanel.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes Task 3/5/6 HTTP endpoints.
- Produces UI preview state independent of committed/staged `ReviewItem` state until reviewer presses `确认成员`.
- Existing `api.researchSelectedStructure(...)` remains the later optional member-enrichment action and should be presented as such.

- [ ] **Step 1: Add TypeScript API types/methods**

Define `StructureMemberCandidate`, `StructurePreview`, `StructureDiagnostics`, and methods:

```ts
previewStructure(itemId, payload)
stageStructure(itemId, payload)
startStructureRegionSelection(itemId)
structureRegionSelectionStatus(itemId)
previewStructureImage(itemId, file)
```

Add a multipart request helper that preserves the existing CSRF/session behavior.

- [ ] **Step 2: Create `StructureInputPanel` with four input paths**

Primary action:
- `采集结构` → browser auto preview.

Fallback actions visible when preview is empty/low-confidence, and also reachable manually:
- `在网页中选择成员区域`
- `粘贴 HTML`
- `粘贴 URL 列表`
- `上传 / 粘贴图片`

Support clipboard image paste when the Structure input panel is focused/open.

- [ ] **Step 3: Implement preview editing before staging**

Show:
- group title + declared count;
- diagnostics summary/confidence;
- member image/crop where available;
- editable title;
- URL;
- position/order;
- remove checkbox/action for false positives.

`确认成员` posts only the reviewer-approved/edited candidates to stage.

- [ ] **Step 4: Integrate with the existing Structure section in `App.tsx`**

After stage succeeds:
- replace the local `ReviewItem` with refreshed response;
- existing Structure tree/selection logic continues to operate;
- do not change Catalog Draft, Source Image, Classification, or decision flow.

Relabel current `获取并汇总所选官网资料` behavior as optional member enrichment, e.g. `批量补全成员资料`, making clear it runs after members are recognized/staged.

- [ ] **Step 5: Add region-picker polling and image/file error states**

Stop polling on selected/cancelled/failed/unmount. Display backend diagnostics rather than generic `0 members` text.

- [ ] **Step 6: Build frontend**

Run:
```powershell
cd frontend
npm run build
```
Expected: TypeScript and Vite build PASS.

- [ ] **Step 7: Manually validate Review behavior at desktop size**

Verify:
- Flubby auto preview shows six direct members on the fixture/dev path;
- failure exposes four fallback options;
- HTML and URL list preview before stage;
- staging refreshes Structure tree;
- image upload/paste reaches image-preview contract and shows explicit recognizer status;
- Catalog Draft/Source Image/Classification are unchanged;
- existing bottom decision bar still works.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/review/StructureInputPanel.tsx frontend/src/api/client.ts frontend/src/App.tsx frontend/src/styles.css
git commit -m "feat: add assisted structure capture UI"
```

---

### Task 8: Update Domain Skill and run whole-feature regressions

**Files:**
- Modify: `.codex/skills/reading-map-domain-model/SKILL.md`
- Test: `backend/reviews/tests.py`

**Interfaces:**
- Documentation becomes the durable semantic source; no new runtime interface.

- [ ] **Step 1: Update the Structure/Capture sections of the Domain Skill**

Add durable rules:
- Structure accepts webpage auto-detection, selected DOM/HTML, URL list, and image/screenshot inputs;
- all inputs normalize to the same Review-side Structure candidates;
- generic structured-data/DOM extraction is preferred over full per-site extractors;
- thin site hints are allowed when needed;
- human-assisted input narrows/provides evidence but does not bypass Review confirmation;
- image group labels are clues, not proof of official Level/Series identity;
- Structure recognition and optional per-member Research/enrichment are separate operations;
- `volume_count` may come from an explicit source declaration even when not all members are recognized.

Do not document implementation details such as BeautifulSoup, endpoint paths, or CSS layout in the Domain Skill.

- [ ] **Step 2: Run all Review tests**

Run:
```powershell
backend\.venv\Scripts\python.exe backend\manage.py test reviews -v 2
```
Expected: PASS.

- [ ] **Step 3: Run frontend build again**

Run:
```powershell
cd frontend
npm run build
```
Expected: PASS.

- [ ] **Step 4: Verify Capture-boundary invariants manually in code/test output**

Confirm:
- Current Page capture does not stage Structure;
- Structure preview/stage does not alter Work/Edition facts;
- image source/crops are not adopted as authoritative Catalog media;
- optional member enrichment remains separate;
- repeated Structure stage is idempotent for equivalent direct relationships.

- [ ] **Step 5: Commit**

```bash
git add .codex/skills/reading-map-domain-model/SKILL.md backend/reviews/tests.py
git commit -m "docs: define assisted structure capture semantics"
```

---

## Implementation order and branch safety

Before Task 1, verify the exact branch contains the user's latest local Review/Admin work. Earlier in this project there were substantial uncommitted local changes not present on remote `main`; do not implement this plan against an older snapshot and later force-overwrite the user's work.

Preferred safe execution:

1. user commits/pushes current local Review/Admin work to a branch;
2. create an isolated feature branch/worktree from that exact commit;
3. implement Tasks 1–8 there;
4. review the whole diff;
5. merge/pull only after the user's current work is safely represented in Git.

## Self-review result

- Spec coverage: automatic generic extraction, thin site hints, diagnostics, DOM selection, HTML, URL list, image contract, shared staging, optional enrichment, and Skill update all have owning tasks.
- Interface consistency: every input returns the same Structure preview shape; only `stage_structure_candidates` crosses into Review-side persisted Structure state.
- Review Focus cases are covered in Tasks 1, 3, 4, 6, and 7.
- Image recognition deliberately uses an adapter boundary in the first implementation; the plan does not pretend a high-quality visual model exists in the current dependency stack.
