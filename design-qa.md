**Source Visual Truth**
- Initial CoverFlow layout reference: `C:\Users\AYA\AppData\Local\Temp\codex-clipboard-474239b7-ef38-4188-bba2-c14f819e3a3f.png`
- Soft rounded UI palette reference: `C:\Users\AYA\AppData\Local\Temp\codex-clipboard-5aa2e2b1-43ac-4851-a26d-b479b14a7ded.png`
- Apple Music-style CoverFlow reference: `C:\Users\AYA\AppData\Local\Temp\codex-clipboard-ba577a10-2ffd-48b7-9361-9b52d480fc2d.png`
- Macaron map/app style reference: `C:\Users\AYA\AppData\Local\Temp\codex-clipboard-64a71a1d-dc57-4c51-be93-e7599872552e.png`
- All-page UI reference: `C:\Users\AYA\AppData\Local\Temp\codex-clipboard-cfada9b1-833e-4cc6-8560-ec39ef0854b7.png`

**Implementation Evidence**
- URL: `http://127.0.0.1:53180/`
- Shelf screenshot: `E:\Coding\ReadingMap\implementation-shelf-favorite-sidebar-icon.png`
- Filter/sort screenshot: `E:\Coding\ReadingMap\implementation-filter-sort-options.png`
- Map closed-filter screenshot: `E:\Coding\ReadingMap\implementation-map-filter-closed-latest.png`
- Map selected-age screenshot: `E:\Coding\ReadingMap\implementation-map-age-selected-only.png`
- Map expanded/favorites screenshot: `E:\Coding\ReadingMap\implementation-map-expanded-favorites.png`
- Mobile map screenshot: `E:\Coding\ReadingMap\implementation-mobile-map-latest.png`
- Viewports checked: `1280 x 720`, `390 x 780`
- State: English map page, shelf/map modes, filter open/closed, selected age group, expanded age stack, favorite toggled, sort switched.
- Density normalization: visual comparison by responsive composition and component behavior because the implementation combines several references.

**Full-View Comparison Evidence**
- The visible UI continues to follow the soft macaron direction: cyan/lavender gradients, rounded white surfaces, circular controls, and playful iconography.
- The lower-right cartoon reading buddy has been removed from the English map page.
- Shelf mode preserves the CoverFlow layout and title-first detail block.
- Map mode now removes the upper book-count summary and lower book detail block, leaving the age timeline and selected age stack as the primary content.
- The sidebar width is reduced to `76px` on desktop and uses a generated cute reading-map app icon.

**Focused Region Comparison Evidence**
- Site icon: `.brand img[src*="reading-map-icon"]` exists, and `frontend/index.html` points favicon to `reading-map-icon.png`.
- Sidebar: desktop `.sidebar` measured `76px` wide.
- Removed cartoon: browser checks returned `.reading-buddy: false` on desktop and mobile.
- Map mode hidden info: browser checks returned `.stage-summary: false` and `.book-focus-info: false` in map mode.
- Age selection: clicking the second timeline age changed active age from `2-3岁` to `3-4岁`; only one `.age-stack-section` remained visible and its badge matched `3-4岁`.
- Stack preview: `.age-stack-book strong` rendered visible book titles such as `A Tiny and Friends Book`, `Big Steps`, `Biscuit`, `Flubby`, `Funny Face`; subtitles showed recommendation sources.
- Expanded cards: clicking the age stack rendered `18` `.age-book-card` items for that selected age group.
- Favorite buttons: shelf mode rendered one favorite button per visible CoverFlow card; expanded map mode rendered one favorite button per book card. Clicking toggled `.favorited`.
- Sort controls: filter card rendered `9` sorting choices and switching to `推荐次数` updated the checked state.
- Build: `npm run build` completed successfully after the known Vite temp-directory sandbox escalation.

**Findings**
- No P0/P1/P2 findings remain.

**Open Questions**
- None for this pass.

**Comparison History**
- Earlier issue: map page title occupied upper-left space.
- Fix made: removed the title and placed shelf/map mode switch in the upper-left.
- Earlier issue: right-lower character image distracted from the map page.
- Fix made: removed the rendered reading buddy and its styles.
- Earlier issue: map mode repeated shelf-mode book count and selected-book detail.
- Fix made: map mode now hides both areas.
- Earlier issue: clicking timeline ages did not constrain the lower content to that age group.
- Fix made: map mode now keeps one active age group and renders only its stack/books.
- Earlier issue: stack preview cards did not show book information.
- Fix made: preview cards now show icon, title, and source.
- Earlier issue: users could not mark books as collected/owned.
- Fix made: added local favorite state and heart buttons on shelf and map book cards.
- Earlier issue: filtering did not expose sorting.
- Fix made: added a sort section with nine selectable dimensions.
- Latest issue: app icon and sidebar proportions were too generic.
- Fix made: generated a cute reading-map icon and reduced desktop sidebar width to `76px`.

**Implementation Checklist**
- Shelf/map mode switching works.
- Map mode hides book-count summary and selected-book detail.
- Timeline age click changes the single visible age group.
- Age stack click expands that age group's book cards.
- Stack preview cards show corresponding book names and sources.
- Favorite buttons toggle visual ownership/collection state.
- Sort controls are available inside the floating filter card.
- Search and cross-dimensional filters remain functional.
- New favicon and sidebar brand icon are wired into the app.
- Desktop and mobile browser states were captured and checked.

**Follow-Up Polish**
- P3: persist favorites to local storage or backend if ownership should survive refresh.

final result: passed

---

## Continuous Source-List Route and Navigator QA (2026-09-24)

**Source Visual Truth**
- User reference: `C:\Users\AYA\AppData\Local\Temp\codex-clipboard-12f3ef1d-d921-49b1-8d8b-9bdba801a2c2.png` (soft circles of books connected by one gently winding path, with a small viewport overview in the upper-right).
- Content constraint: the ten circles represent the ten groups and 111 book-list entries in the user-selected Banana Mama incremental source; this is not an age-stage interpretation.

**Implementation Evidence**
- URL: `http://127.0.0.1:53180/map`.
- Visual capture: Codex in-app Browser tab `3`, desktop viewport `1734 x 982` (browser capture has no filesystem path).
- Default view showed the first four stage circles with books inside, soft pastel circle boundaries, a single green winding connection between consecutive circles, and a small top-right map overview.
- Source book-list cover art is unavailable for many entries, so existing generated typography covers remain. This is a content limitation, not a substitution for verified real covers.

**Interaction and Data Checks**
- Browser DOM: 10 stage circles, 111 books, 9 connecting edges, 10 visible mini-map stage dots.
- Zoom In changed the main transform from `scale(0.18)` to `scale(0.216)` and simultaneously narrowed the mini-map viewport mask.
- Dragging the canvas changed the main horizontal translation by 290px and moved the mini-map viewport mask in the matching direction.
- Reload restored the initial `0.18×` view; the user-owned tab was left open on `/map`.
- `npm run build`: passed. Vite emitted only its existing large-chunk advisory.

**Comparison and Findings**
- The reference’s large soft circles, sequential curved route, spare white canvas, and overview locator are represented. Ten circles require horizontal exploration rather than forcing 111 books into one screen.
- The implementation is not a pixel-for-pixel copy: book counts vary by source group, and generated covers are used where genuine covers are not available.
- No P0/P1/P2 finding remains for the requested route and position-window behavior.

final result: passed

---

## Review Product Image Selection QA

**Source Visual Truth**
- User-selected review gallery reference: `C:\Users\AYA\AppData\Local\Temp\codex-clipboard-bd63ede6-fc36-412f-8b8f-f00a04087b5a.png` (`1069 x 554`).
- Intended state: every captured image can be selected as the single cover and can independently remain selected as a detail image.

**Implementation Evidence**
- URL: `http://127.0.0.1:53180/admin?batch=2`.
- Screenshot: Codex in-app Browser tab `1` screenshot artifact, captured at `1714 x 982` (the browser API did not expose a filesystem path).
- CSS viewport: `1714 x 982`; browser default device density. The focused gallery region was compared by component geometry because the source is a cropped region and the implementation capture is the full review workspace.
- State: `Frog and Dog`, nine captured product images, first image selected as cover, all nine images retained as details.

**Full-View Comparison Evidence**
- The existing compact gallery grid, image containment, card radius, neutral palette, and review-workspace density are preserved.
- Six cards remain visible in the first row at the current workspace width, with the remaining three wrapping cleanly to the second row.
- Adding the second control row does not overlap the sticky action bar, right source-image panel, or adjacent Difficulty section.

**Focused Region Comparison Evidence**
- All nine visible cards render a radio over the image's upper-left corner and retain one bottom checkbox labeled `保留详情图`; only the selected radio expands to show `封面`.
- Only one radio is selected at a time; the selected cover card receives the existing green semantic accent.
- The second image was selected as cover and remained checked as a detail image after the save/reload cycle; the original first cover was then restored.
- A detail checkbox was toggled and restored independently without changing the cover selection.
- Console errors/warnings: none.

**Required Fidelity Surfaces**
- Fonts and typography: existing review typography, weights, and compact 10px control labels are unchanged and remain legible.
- Spacing and layout rhythm: the cover radio is removed from card flow and overlaid on the image, while the single 29px detail row preserves a more compact gallery rhythm.
- Colors and visual tokens: controls retain the established green accent and neutral card borders; cover selection uses a subtle border/ring rather than a new palette.
- Image quality and asset fidelity: source product images remain uncropped with `object-fit: contain`; no placeholders or replacement assets were introduced.
- Copy and content: the section hint now states that every image can be a cover and can independently remain a detail image; both controls use concise, consistent labels.

**Findings**
- No P0/P1/P2 findings remain.

**Open Questions**
- None for this scoped interaction.

**Comparison History**
- Earlier issue: only the originally captured cover had a radio, while all other images only exposed the detail checkbox.
- Fix made: every card now exposes both controls, and cover selection is persisted independently from detail inclusion.
- Post-fix evidence: switching the second card to cover changed the radio group from card 1 to card 2 while both detail checkboxes stayed selected; restoring card 1 returned the original state.
- Latest refinement: moved every cover radio onto the image's upper-left corner; the selected item displays `◉ 封面`, unselected items display only `○`, and the detail checkbox remains in the original bottom row.

**Implementation Checklist**
- Every image can be selected as cover.
- Every image, including the selected cover, can be independently retained as a detail image.
- Exactly one cover is stored.
- Zero or more detail images are stored.
- Cover and detail selections survive the API save and review-item reload.
- Backend review tests and frontend production build pass.

**Follow-Up Polish**
- No additional polish required for this scoped change.

final result: passed

---

## Interactive Reading Room Homepage QA

**Source Visual Truth**
- Selected homepage reference: `C:\Users\AYA\AppData\Local\Temp\codex-clipboard-efb54d58-cadf-4a4d-81cd-67cf616e7269.png` (`1680 x 944`).
- Implementation image layer: `E:\Coding\ReadingMap\frontend\public\home\reading-room-concept.png`.
- Fidelity strategy: preserve the selected scene as the desktop visual truth, then place independently cropped interactive object layers at matching world positions.

**Implementation Evidence**
- Homepage URL: `http://127.0.0.1:53180/`.
- Desktop visual capture reviewed in the in-app browser at `1280 x 720`.
- Mobile visual capture reviewed in the in-app browser at `390 x 844`.
- Pixel density: browser default device pixel ratio; comparison normalized by viewport composition because the source and desktop implementation share the same `1680 / 944` aspect ratio.
- Desktop baseline visibly preserved the reference composition without clipping: calendar, map, bookshelf, guide wall, typewriter, plants, window, cat, navigation, and desk all remained in place.
- Mobile uses a deliberate responsive launcher rather than shrinking the desktop scene into unusable hotspots.

**States and Interaction Tests**
- Default desktop state: full-room scene fills the viewport and all five interactive objects are independently focusable.
- Calendar hover/focus state: object scales and lifts; focus outline and `打开我的阅读计划` label are visible.
- Calendar activation: navigates to `/plan`; the mock daily plan and weekly progress summary render.
- Reading Map activation: navigates to `/map`; existing continuous semantic-zoom map remains intact.
- Bookshelf activation: navigates to `/bookshelf`; existing shelf, tabs, search, sorting, and cards remain intact.
- Reading Guides activation: navigates to `/guides`; four mock guide cards render responsively.
- Typewriter activation: press/wiggle animation runs and a live-region toast appears with the deferred-label message.
- Keyboard navigation: brand, navigation hotspots, four scene links, and typewriter are reachable in a logical sequence; visible focus state was checked.
- Reduced-motion: `prefers-reduced-motion` styles suppress nonessential transitions.
- Mobile state: hero plus five large launcher cards; no horizontal overflow was observed.

**Console and Build**
- Homepage console: no errors observed.
- One React Flow attribution warning appeared only after opening the pre-existing `/map` page; it is unrelated to this homepage implementation.
- `npm run build`: passed (`tsc --noEmit && vite build`).
- Vite reports the existing large-chunk advisory; it does not block runtime behavior.

**Findings and Comparison History**
- Initial risk: a flat concept image cannot animate its objects independently.
- Fix: added pixel-aligned cropped object replicas above the unchanged background, so each entrance can move without redrawing the whole scene.
- Initial risk: desktop-sized hotspots would be too small and fragile on narrow screens.
- Fix: added a separate mobile information hierarchy with full-width visual cards.
- Initial risk: the typewriter has no destination yet.
- Fix: kept it as a semantic button with immediate motion and status feedback, ready for the future label workflow.
- No P0/P1/P2 design findings remain for this first interactive version.

**Follow-Up Polish**
- P3: replace the flat scene crops with separately generated transparent object assets if stronger parallax, shadows, or physics are wanted later.
- P3: connect `/plan` and `/guides` to real data when those product flows are defined.

final result: passed

---

**Personal Shelf Page QA**
- Source visual references: `C:\Users\AYA\AppData\Local\Temp\codex-clipboard-d21b8ba0-27b8-4836-9250-6f28b42c85d2.png`, `C:\Users\AYA\AppData\Local\Temp\codex-clipboard-02a1d30c-5828-45f7-9884-ab19b35f51ed.png`, `C:\Users\AYA\AppData\Local\Temp\codex-clipboard-4c253988-467c-46ac-8df9-9eefd73b422c.png`.
- Implementation URL: `http://127.0.0.1:53180/#shelf`, sidebar button title `我的书架`.
- Screenshots: `E:\Coding\ReadingMap\implementation-personal-shelf-wall-desktop.png`, `E:\Coding\ReadingMap\implementation-personal-shelf-wall-tooltip.png`, `E:\Coding\ReadingMap\implementation-personal-shelf-wall-mobile.png`.
- Desktop checked at `1406 x 982`: left side is now one continuous vertical shelf wall, not age-split horizontal rails; right detail panel remains visible; default sort remains age ascending.
- Tooltip checked in the continuous shelf: visible yellow source dot rendered and hover showed `香蕉妈妈 · 2 次 · 系列匹配`.
- Mobile checked at `390 x 844`: page collapsed to one column, `bodyOverflow` was `0`, book grid used 3 columns and kept vertical-only page scrolling.
- Direct URL checked: `/#shelf` loaded the shelf without clicking the sidebar; active nav title was `我的书架`.
- Removed old rail selectors: `.shelf-age-row`, `.shelf-rail`, `.shelf-books`, and `.shelf-book-title` no longer appear in `frontend/src`.
- Fresh browser tab checked: 240 `.shelf-book` nodes, 0 old rail nodes, 0 page horizontal overflow, and no console `error`/`warn` entries.
- Data checked through `/api/personal-shelf`: 240 book items, 422 total quantity, 11 current cover assets, 28 items with recommendation-source dots.
- Build checked with `npm run build`: passed after the known Vite temp-directory sandbox escalation.
- Findings: no P0/P1/P2 findings remain.

final result: passed
