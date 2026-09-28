import type { CSSProperties } from "react";

export const SCENE_SIZE = { width: 1680, height: 944 };
export type SceneId = "plan" | "map" | "bookshelf" | "guides" | "typewriter";
export type Rect = { x: number; y: number; width: number; height: number };
type RasterPath = `/home/layers/${string}.png` | `/home/layers/${string}.webp`;
export type AssetSlot = { src: RasterPath | null; target: RasterPath };
// Set src only after installing a freshly generated asset. Never fall back to a screenshot.
const slot = (name: string, src: RasterPath | null = null): AssetSlot => ({ src, target: `/home/layers/${name}.webp` });
export const sceneAssets = {
  background: slot("room-background"),
  plan: { base: slot("plan-base"), page: slot("plan-page") },
  map: { base: slot("reading-map-base"), pin: slot("reading-map-pin") },
  bookshelf: { base: slot("bookshelf-base"), book: slot("bookshelf-book") },
  guides: { base: slot("guides-base"), photos: [slot("guides-photo-1"), slot("guides-photo-2"), slot("guides-photo-3"), slot("guides-photo-4")] },
  typewriter: { desk: slot("typewriter-desk"), paper: slot("typewriter-paper"), machine: slot("typewriter-machine") },
  decorations: { cat: slot("cat"), plants: slot("plants") }
};
export type SceneObject = { id: SceneId; title: string; label: string; description: string; href?: string; bounds: Rect; hitBounds?: Rect };
export const sceneObjects: SceneObject[] = [
  { id: "plan", title: "Plan →", label: "打开我的阅读计划", description: "安排今天的阅读", href: "/plan", bounds: { x: 350, y: 105, width: 292, height: 336 } },
  { id: "map", title: "Reading Map →", label: "进入 Reading Map", description: "沿路线发现下一本书", href: "/map", bounds: { x: 668, y: 116, width: 815, height: 391 } },
  { id: "bookshelf", title: "Bookshelf →", label: "打开我的书架", description: "查看想读、在读与读过", href: "/bookshelf", bounds: { x: 318, y: 442, width: 328, height: 405 } },
  { id: "guides", title: "Reading Guides →", label: "查看阅读达人", description: "看看达人怎么选书", href: "/guides", bounds: { x: 695, y: 521, width: 570, height: 249 } },
  // Extend the art canvas for the desk while retaining the original machine hit region.
  { id: "typewriter", title: "标签打字机", label: "启动标签打字机", description: "记录阅读里的小事", bounds: { x: 1285, y: 497, width: 395, height: 433 }, hitBounds: { x: 50 / 395 * 100, y: 0, width: 258 / 395 * 100, height: 171 / 433 * 100 } }
];
export const decorativeLayers = [
  { id: "plants", asset: sceneAssets.decorations.plants, bounds: { x: 10, y: 460, width: 300, height: 370 } },
  { id: "cat", asset: sceneAssets.decorations.cat, bounds: { x: 185, y: 780, width: 255, height: 110 } }
];
export function percentRect(rect: Rect, space = SCENE_SIZE): CSSProperties {
  return { left: `${rect.x / space.width * 100}%`, top: `${rect.y / space.height * 100}%`, width: `${rect.width / space.width * 100}%`, height: `${rect.height / space.height * 100}%` };
}
