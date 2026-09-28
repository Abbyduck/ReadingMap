# Reading Room layer asset contract

This directory is for **newly generated, independent assets**. Do not crop objects
from `reading-room-concept.png` or use the old homepage as a runtime background.
The old file is retained as a reference only and is not loaded by the homepage.

This change prepares the asset system; final raster artwork has not been generated.
Until installed, functional layers use small code-native structural placeholders.
Optional decorative layers remain empty. These are not a new visual design.

## Install an asset

1. Generate/export an independent PNG or WebP into this directory.
2. Open `frontend/src/components/home/sceneAssets.ts` and pass the installed path
   as the slot's second argument, e.g.
   `slot("plan-base", "/home/layers/plan-base.webp")`.
   This sets `src`; `target` records the intended file name while a slot is empty.
3. Keep the specified canvas aspect ratio and transparent margins. All images
   render whole with `object-fit: contain`. There are no sprite/crop offsets.
4. Verify desktop and mobile, hover and keyboard focus. Missing/failed assets
   use the structural fallback; they never trigger a legacy screenshot fallback.

Coordinates use a 1680 x 944 design canvas. `sceneObjects` owns scene placement;
`SceneArtwork` composes parts within each object's normalized 100 x 100 canvas.
Image file pixel dimensions are independent of positioning; use 2x resolution
where practical. Preserve this part geometry when generating assets.

| Slot | Canvas / local bounds (x, y, width, height) | Contents |
| --- | --- | --- |
| room-background | 1680 x 944 | Walls, window, floor and lighting only. No functional objects, text, navigation, cat or plants. |
| plan-base | 292 x 336, whole object | Calendar support/frame with page absent; no functional text. |
| plan-page | 8,29,84,62 within Plan | Calendar page only, top edge is the hinge. |
| reading-map-base | 815 x 391, whole object | Map/frame only; omit route, pins and sign text. |
| reading-map-pin | 6 x 15 within Map | Single pin, reused at (22,32), (51,59), (72,17). |
| bookshelf-base | 328 x 405, whole object | Shelf and static books, leave animated book at (52,15,11,21) absent. |
| bookshelf-book | 52,15,11,21 within Bookshelf | Single book with transparent perimeter. |
| guides-base | 570 x 249, whole object | Board without photos or title text. |
| guides-photo-1..4 | 19 x 61 within Guides | Four independent photos, including their own pin; origins at (8,27), (30,27), (52,27), (74,27). |
| typewriter-desk | 0,34,100,66 within Typewriter | Desk only, no machine or paper. |
| typewriter-paper | 31,5,29,25 within Typewriter | Paper only, allow room above for feed motion. |
| typewriter-machine | 18,18,60,19 within Typewriter | Typewriter only, paper absent. |
| cat | 255 x 110 | Optional transparent cat, scene origin (185,780). |
| plants | 300 x 370 | Optional transparent plants, scene origin (10,460). |

The Typewriter art canvas is 395 x 433 at scene (1285,497), adding the desk.
Its machine hit area remains the old scene rectangle (1335,497,258,171).
Other functional object bounds are unchanged. Signs and navigation are live HTML,
so raster assets must not duplicate their labels. The map route is an SVG path.

## Motion ownership

- Plan: paper rotates around its top edge; support/frame stays still.
- Map: route draws, pins drop in sequence; map/frame stays still.
- Bookshelf: one book slides out; cabinet stays still.
- Guides: individual photos swing from their pins; board stays still.
- Typewriter: paper feeds up on hover/focus and restarts on each click;
  machine and desk stay still. Label creation is still deferred.
- Reduced-motion users receive immediate states without transform animation.

Desktop, mobile cards and mobile scene preview share the same artwork renderer.
Decorations are noninteractive and hidden from accessibility. Hit regions are
separate from art and do not move or scale when animation plays.
