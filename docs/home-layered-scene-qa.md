# Homepage layered asset refactor verification

Scope: asset architecture only; regenerated final PNG/WebP artwork is pending.
The old full-homepage raster remains on disk as an unused reference. Its runtime
uses, crop offsets, oversized-image styles, and whole-entry hover scaling are gone.

## Checks completed

- Production TypeScript/Vite build passed. Existing large-chunk warning remains.
- Static search found no legacy image URL, SceneCrop, cropStyles, crop CSS,
  whileHover scaling or scale declarations in the homepage/scene implementation.
- No Three.js dependencies added.
- Browser checked at 1598 x 982 desktop and 390 x 844 mobile; temporary viewport
  override reset afterward.
- Desktop outer layer coordinates checked against the previous Plan/Map/Shelf/
  Guides rectangles. Typewriter art canvas includes desk; machine hit rectangle
  still resolves to (1335,497,258,171).
- Keyboard focus changed the calendar paper's rotateX matrix while its outer
  object remained `transform: none`.
- Keyboard focus drew the map route to pathLength 1 while its outer object
  remained `transform: none`.
- Keyboard focus translated/rotated the single shelf book while the shelf's
  outer object remained `transform: none`.
- Typewriter click displayed its status feedback. Click restarts the paper layer
  using a new print version; toast/print timers are cleared on unmount.
- Hover uses the same internal active state as focus; no synthetic mouse-hover
  test was performed with the available browser API.
- Mobile showed five 160px/135px entrance cards, with no horizontal overflow.
  Artwork aspect ratios matched the design ratios within rounding tolerance.
- Calendar link navigated from mobile homepage to `/plan` successfully.
- Browser console returned no errors during these checks.
- Existing destination pages/backend were not edited in this refactor.

## Asset handoff

Final artwork slots intentionally have `src: null`; the page displays structural
SVG placeholders. Missing decorative assets render nothing. This is not final
visual approval and does not assert that placeholders match the former raster's
lighting/detail. There is no hidden fallback to that image.

Asset requirements and installation instructions:
`frontend/public/home/layers/README.md`.

Architecture/build verification: passed. Final generated-artwork review: pending.
